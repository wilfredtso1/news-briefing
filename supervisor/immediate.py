"""
Supervisor — Immediate Mode (Phase 3).

Processes user replies to digest emails in real-time. Classifies the reply,
optionally acknowledges the digest, extracts any proposed config changes,
validates whether they are low-risk or high-risk, applies low-risk changes
immediately, and queues high-risk ones.

Graph structure:
  START → classify_reply → maybe_acknowledge → route_after_acknowledge →
          [extract_change → validate_change → (apply_change | queue_change) → log_feedback_event]
          [extract_command → execute_command]
          → END

Reply types:
  acknowledge — user confirms they read the digest; no config change needed
  feedback    — user proposes a change; extract and validate it
  both        — acknowledgment + feedback; do both
  irrelevant  — unrelated reply; do nothing
  command     — user is requesting a pipeline run on demand (e.g. "send brief", "deep read please")

Risk classification:
  low-risk  — topic_weights, word_budget, cosine_similarity_threshold
               Applied immediately via set_config (tools/db.py).
  high-risk — prompt edits, source changes, unsubscribe requests
               Queued in feedback_events for human review before applying.

Why LangGraph (not LCEL):
  The supervisor branches on reply type (acknowledge/feedback/both/irrelevant)
  and again on risk level (low/high). LCEL is for linear chains.
  LangGraph handles stateful conditional routing. See CLAUDE.md Non-Obvious
  Design Decisions.

Graph design note — no fan-out:
  We use a sequential design (maybe_acknowledge → route_feedback) rather than
  true fan-out. The 'both' reply type passes through maybe_acknowledge (which
  sets the acknowledge flag and marks the digest) then continues to extract_change.
  This avoids LangGraph version-specific fan-out/Send API concerns and is
  easier to test.

Model selection:
  Haiku for classification and extraction (high-volume, structured output).
  Opus reserved for future weekly pattern analysis — overkill for per-reply tasks.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, TypedDict

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from config import settings
from tools.db import (
    insert_feedback_event,
    mark_digest_acknowledged,
    mark_feedback_applied,
    set_config,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM clients
# ---------------------------------------------------------------------------

# Haiku: reply classification + change extraction (high volume, structured output)
_haiku = ChatAnthropic(
    model="claude-haiku-4-5",
    api_key=settings.anthropic_api_key,
    max_tokens=512,
    temperature=0,
)

# ---------------------------------------------------------------------------
# Constants — which config keys are safe to apply immediately
# ---------------------------------------------------------------------------

# Low-risk keys can be updated without human review. Any key not in this set
# is treated as high-risk and queued for approval.
LOW_RISK_CONFIG_KEYS = frozenset({
    "topic_weights",
    "word_budget",
    "cosine_similarity_threshold",
    "synthesis_style_notes",   # new: JSON array of style instruction strings
    "web_search_topics",       # new: JSON array of topic strings to search daily
})

# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass
class SupervisorResult:
    """
    Result returned by run_immediate_supervisor().

    action_taken: human-readable summary of what the supervisor did
    config_delta: {key: new_value} for any config keys immediately updated
    queued_items: list of feedback event IDs created for high-risk items
    reply_type: one of acknowledge | feedback | both | irrelevant | command
    command_triggered: "daily_brief" | "deep_read" | "" (empty if no command was run)
    """
    action_taken: str
    config_delta: dict[str, Any] = field(default_factory=dict)
    queued_items: list[str] = field(default_factory=list)
    reply_type: str = "irrelevant"
    command_triggered: str = ""


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------


class SupervisorState(TypedDict):
    # Inputs
    digest_id: str
    raw_reply: str
    thread_id: str

    # Intermediate
    reply_type: str          # acknowledge | feedback | both | irrelevant | command
    proposed_key: str        # agent_config key the user wants to change
    proposed_value: Any      # new value to set
    risk_level: str          # low | high | none
    extraction_reasoning: str
    command_target: str      # daily_brief | deep_read (set by extract_command_node)

    # Outputs accumulated across nodes
    config_delta: dict[str, Any]
    queued_items: list[str]
    action_taken: str
    event_id: str
    command_triggered: str   # pipeline that was triggered on-demand (empty if not a command)


# ---------------------------------------------------------------------------
# Prompt: classify reply
# Haiku is fast and cheap for this structured classification task.
# We ask for one of four literal strings to keep JsonOutputParser reliable.
# ---------------------------------------------------------------------------

# Returns one of: "acknowledge", "feedback", "both", "irrelevant", "command"
_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You classify email replies to an AI news digest.

Return JSON only: {{"reply_type": "<type>"}}

Types:
- "acknowledge" — user confirms they read the digest (e.g. "thanks", "got it", "looks good")
- "feedback" — user requests a change (e.g. "less crypto", "more AI stories", "shorter please")
- "both" — reply contains both an acknowledgment AND a change request
- "command" — user is requesting a pipeline run on demand (e.g. "send brief", "send me a deep read", "morning brief please", "give me the news")
- "code_change_approval" — user is approving a code change proposal (reply contains "approve" or "approved")
- "irrelevant" — unrelated reply (forwarded email, out-of-office, spam)

Be conservative: only use "feedback" or "both" if the user is clearly requesting a change.
Use "command" when the user is explicitly asking for a new digest to be generated — not just acknowledging.""",
    ),
    ("human", "Digest reply:\n{raw_reply}"),
])

_classify_chain = _CLASSIFY_PROMPT | _haiku | JsonOutputParser()


# ---------------------------------------------------------------------------
# Prompt: extract command target
# Determines which pipeline to trigger: daily_brief or deep_read.
# Haiku is sufficient — two-class classification with a strong default.
# We ask for JSON with "pipeline" key so JsonOutputParser is reliable.
# ---------------------------------------------------------------------------

# Returns one of: "daily_brief", "deep_read"
_EXTRACT_COMMAND_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You identify which pipeline the user wants to run based on their email message.

Return JSON only: {{"pipeline": "<type>", "reasoning": "<one sentence>"}}

Types:
- "daily_brief" — user wants their regular news digest (e.g. "send brief", "morning brief", "give me the news", "send it")
- "deep_read" — user wants long-form articles (e.g. "deep read", "long form", "send me something to read", "deep dive")

Default to "daily_brief" if the intent is unclear or ambiguous.""",
    ),
    ("human", "Email message:\n{raw_reply}"),
])

_extract_command_chain = _EXTRACT_COMMAND_PROMPT | _haiku | JsonOutputParser()


# ---------------------------------------------------------------------------
# Prompt: extract proposed change
# Haiku handles structured JSON extraction well — no Opus needed here.
# ---------------------------------------------------------------------------

# The key field must match an agent_config key. We list known keys so the LLM
# can map natural language to the correct structured key.
_EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You extract a proposed config change from a user reply to a news digest.

Known config keys and their structure:
- "topic_weights": object mapping topic name to float weight (e.g. {{"ai": 1.5, "crypto": 0.3}})
- "word_budget": object with budget keys (e.g. {{"daily_brief_total": 2500}})
- "cosine_similarity_threshold": float between 0.0 and 1.0
- "synthesis_style_notes": JSON array of style instruction strings (e.g. ["write shorter stories"])
- "web_search_topics": JSON array of topic strings to search daily (e.g. ["markets", "sports"])
- "source_reclassify": object {{"email": "sender@domain.com", "type": "news_brief|long_form"}} — use when user wants to move a newsletter between daily brief and deep read
- "prompt_edit": free-text instruction to change how stories are written (HIGH RISK)
- "unsubscribe": sender email address to unsubscribe from (HIGH RISK)
- "source_change": instructions about a specific newsletter source (HIGH RISK)

Return JSON only:
{{
  "key": "<config_key>",
  "value": <new_value>,
  "reasoning": "<one sentence why>"
}}

If no clear config change: {{"key": "unknown", "value": null, "reasoning": "could not parse intent"}}""",
    ),
    ("human", "Digest reply:\n{raw_reply}"),
])

_extract_chain = _EXTRACT_PROMPT | _haiku | JsonOutputParser()


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def classify_reply_node(state: SupervisorState) -> dict:
    """
    Classify the reply as acknowledge / feedback / both / irrelevant.
    Uses claude-haiku-4-5 for speed and cost efficiency.
    Defaults to 'irrelevant' on any LLM failure — safe fallback.
    """
    try:
        result = _classify_chain.invoke({"raw_reply": state["raw_reply"]})
        reply_type = result.get("reply_type", "irrelevant")
        if reply_type not in {"acknowledge", "feedback", "both", "irrelevant", "command", "code_change_approval"}:
            log.warning("supervisor_classify_unexpected_type", reply_type=reply_type)
            reply_type = "irrelevant"
    except Exception as e:
        log.warning(
            "supervisor_classify_failed",
            error=str(e),
            action="defaulting to irrelevant",
        )
        reply_type = "irrelevant"

    log.info(
        "supervisor_reply_classified",
        digest_id=state["digest_id"],
        reply_type=reply_type,
    )
    return {**state, "reply_type": reply_type}


def maybe_acknowledge_node(state: SupervisorState) -> dict:
    """
    Mark the digest acknowledged if reply type is 'acknowledge' or 'both'.
    Non-fatal: DB failure is logged as a warning and the graph continues.
    This runs for all reply types so routing is clean — it's a no-op for
    feedback and irrelevant replies.
    """
    reply_type = state["reply_type"]
    if reply_type not in {"acknowledge", "both"}:
        return state

    try:
        mark_digest_acknowledged(state["digest_id"])
        log.info("supervisor_digest_acknowledged", digest_id=state["digest_id"])
    except Exception as e:
        log.warning(
            "supervisor_acknowledge_failed",
            digest_id=state["digest_id"],
            error=str(e),
        )

    current_action = state.get("action_taken", "")
    new_action = f"{current_action}; acknowledged digest" if current_action else "acknowledged digest"
    return {**state, "action_taken": new_action}


def extract_change_node(state: SupervisorState) -> dict:
    """
    Extract the proposed config change from the raw reply.
    Uses claude-haiku-4-5 — extraction is structured, not complex reasoning.
    Defaults to unknown key on failure so the graph can safely continue.
    """
    try:
        result = _extract_chain.invoke({"raw_reply": state["raw_reply"]})
        proposed_key = result.get("key", "unknown")
        proposed_value = result.get("value")
        reasoning = result.get("reasoning", "")
    except Exception as e:
        log.warning(
            "supervisor_extract_failed",
            error=str(e),
            action="treating as unknown change",
        )
        proposed_key = "unknown"
        proposed_value = None
        reasoning = f"extraction failed: {e}"

    log.info(
        "supervisor_change_extracted",
        digest_id=state["digest_id"],
        proposed_key=proposed_key,
        reasoning=reasoning,
    )
    return {
        **state,
        "proposed_key": proposed_key,
        "proposed_value": proposed_value,
        "extraction_reasoning": reasoning,
    }


def validate_change_node(state: SupervisorState) -> dict:
    """
    Classify the proposed change as low-risk, high-risk, or none.

    Low-risk: topic_weights, word_budget, cosine_similarity_threshold
    High-risk: prompt_edit, unsubscribe, source_change, anything else
    None: unknown key — no action taken

    Pure logic — no LLM needed here.
    """
    proposed_key = state.get("proposed_key", "unknown")

    if proposed_key in LOW_RISK_CONFIG_KEYS:
        risk_level = "low"
    elif proposed_key == "source_reclassify":
        risk_level = "source"
    elif proposed_key == "unknown" and len(state.get("raw_reply", "")) > 50:
        risk_level = "code_change"
    elif proposed_key == "unknown":
        risk_level = "none"
    else:
        risk_level = "high"

    log.info(
        "supervisor_change_validated",
        digest_id=state["digest_id"],
        proposed_key=proposed_key,
        risk_level=risk_level,
    )
    return {**state, "risk_level": risk_level}


def apply_change_node(state: SupervisorState) -> dict:
    """
    Apply a low-risk config change immediately via set_config (tools/db.py).
    set_config stores the previous value automatically for rollback support.
    Raises on DB failure — a silent config change failure is worse than a crash.
    """
    key = state["proposed_key"]
    value = state["proposed_value"]

    try:
        set_config(key, value, updated_by="supervisor")
        config_delta = {**state.get("config_delta", {}), key: value}
        current_action = state.get("action_taken", "")
        new_action = (
            f"{current_action}; applied {key}={json.dumps(value)}"
            if current_action
            else f"applied {key}={json.dumps(value)}"
        )
        log.info("supervisor_config_applied", digest_id=state["digest_id"], key=key, value=value)
        return {**state, "config_delta": config_delta, "action_taken": new_action}
    except Exception as e:
        log.error("supervisor_apply_failed", digest_id=state["digest_id"], key=key, error=str(e))
        raise


def queue_change_node(state: SupervisorState) -> dict:
    """
    Log a high-risk proposed change in feedback_events for human review.
    Does NOT apply the change — that requires explicit approval.
    Raises on DB failure — losing a queued change silently is not acceptable.
    """
    try:
        event_id = insert_feedback_event(
            digest_id=state["digest_id"],
            raw_reply=state["raw_reply"],
            supervisor_interpretation=state.get("extraction_reasoning", ""),
            proposed_change=json.dumps({
                "key": state.get("proposed_key"),
                "value": state.get("proposed_value"),
            }),
        )
        queued_items = [*state.get("queued_items", []), event_id]
        current_action = state.get("action_taken", "")
        new_action = (
            f"{current_action}; queued high-risk change: {state.get('proposed_key')}"
            if current_action
            else f"queued high-risk change: {state.get('proposed_key')}"
        )
        log.info(
            "supervisor_change_queued",
            digest_id=state["digest_id"],
            event_id=event_id,
            proposed_key=state.get("proposed_key"),
        )
        return {**state, "queued_items": queued_items, "action_taken": new_action, "event_id": event_id}
    except Exception as e:
        log.error("supervisor_queue_failed", digest_id=state["digest_id"], error=str(e))
        raise


def log_feedback_event_node(state: SupervisorState) -> dict:
    """
    Log an applied low-risk change as a feedback event and mark it applied.
    For high-risk changes: already logged in queue_change_node — skip here.
    Non-fatal: config change already happened; losing the log is a warning, not a crash.
    """
    # Only log for low-risk changes that were successfully applied
    if state.get("risk_level") != "low" or not state.get("config_delta"):
        return state

    try:
        event_id = insert_feedback_event(
            digest_id=state["digest_id"],
            raw_reply=state["raw_reply"],
            supervisor_interpretation=state.get("extraction_reasoning", ""),
            proposed_change=json.dumps({
                "key": state.get("proposed_key"),
                "value": state.get("proposed_value"),
            }),
        )
        mark_feedback_applied(event_id)
        log.info("supervisor_feedback_logged", digest_id=state["digest_id"], event_id=event_id)
        return {**state, "event_id": event_id}
    except Exception as e:
        # Non-fatal: the config change already happened successfully
        log.warning("supervisor_log_event_failed", digest_id=state["digest_id"], error=str(e))
        return state


def no_op_node(state: SupervisorState) -> dict:
    """
    Terminal node for irrelevant replies or unknown change keys.
    Ensures action_taken is always populated for callers.
    """
    current_action = state.get("action_taken", "")
    if not current_action:
        return {**state, "action_taken": f"no action taken for reply_type={state.get('reply_type', 'irrelevant')}"}
    return state


def extract_command_node(state: SupervisorState) -> dict:
    """
    Extract which pipeline the user wants to trigger: daily_brief or deep_read.
    Uses claude-haiku-4-5 — two-class classification, defaults to daily_brief on failure.
    This is a command reply (not an acknowledgment), so the digest is NOT marked acknowledged.
    """
    try:
        result = _extract_command_chain.invoke({"raw_reply": state["raw_reply"]})
        command_target = result.get("pipeline", "daily_brief")
        if command_target not in {"daily_brief", "deep_read"}:
            log.warning("supervisor_extract_command_unexpected", command_target=command_target)
            command_target = "daily_brief"
    except Exception as e:
        log.warning(
            "supervisor_extract_command_failed",
            error=str(e),
            action="defaulting to daily_brief",
        )
        command_target = "daily_brief"

    log.info("supervisor_command_extracted", digest_id=state["digest_id"], command_target=command_target)
    return {**state, "command_target": command_target}


def execute_command_node(state: SupervisorState) -> dict:
    """
    Execute the requested pipeline on demand, bypassing anchor and threshold checks.

    Calls pipeline directly — no anchor wait for daily_brief, no queue threshold
    for deep_read (force=True delivers whatever articles are available, even 1).
    Pipeline failures are logged and captured in action_taken but do not raise,
    so the supervisor returns a result regardless of pipeline outcome.
    """
    # Normalize: empty string (TypedDict default) falls back to daily_brief
    command_target = state.get("command_target") or "daily_brief"
    run_id = str(uuid.uuid4())

    try:
        if command_target == "deep_read":
            from pipeline.deep_read import run_deep_read
            run_deep_read(run_id=run_id, force=True)
        else:
            from pipeline.daily_brief import run as run_daily_brief
            run_daily_brief(run_id=run_id)
        action = f"triggered {command_target} (run_id={run_id})"
        log.info("supervisor_command_executed", digest_id=state["digest_id"], command_target=command_target, run_id=run_id)
    except Exception as e:
        log.error(
            "supervisor_execute_command_failed",
            digest_id=state["digest_id"],
            command_target=command_target,
            run_id=run_id,
            error=str(e),
        )
        action = f"command failed: {command_target} — {e}"

    current_action = state.get("action_taken", "")
    new_action = f"{current_action}; {action}" if current_action else action
    return {**state, "action_taken": new_action, "command_triggered": command_target}


def reclassify_source_node(state: SupervisorState) -> dict:
    """
    Reclassify a newsletter source's type (news_brief or long_form) based on user feedback.
    Validates type before calling DB. Self-logs via insert_feedback_event + mark_feedback_applied.
    Returns to END after completion — no approval needed for source type corrections.
    """
    value = state.get("proposed_value") or {}
    email = value.get("email", "") if isinstance(value, dict) else ""
    stype = value.get("type", "") if isinstance(value, dict) else ""

    if stype not in ("news_brief", "long_form"):
        log.warning(
            "supervisor_reclassify_invalid_type",
            digest_id=state["digest_id"],
            email=email,
            stype=stype,
        )
        return {**state, "action_taken": "reclassify_skipped_invalid_type"}

    from tools.db import update_source_type  # lazy import — Branch A owns this function
    update_source_type(email, stype)

    try:
        event_id = insert_feedback_event(
            digest_id=state["digest_id"],
            raw_reply=state["raw_reply"],
            supervisor_interpretation=f"reclassified {email} as {stype}",
            proposed_change=json.dumps({"email": email, "type": stype}),
        )
        mark_feedback_applied(event_id)
        log.info(
            "supervisor_source_reclassified",
            digest_id=state["digest_id"],
            email=email,
            stype=stype,
            event_id=event_id,
        )
    except Exception as e:
        log.warning("supervisor_reclassify_log_failed", digest_id=state["digest_id"], error=str(e))

    return {**state, "action_taken": f"reclassified {email} as {stype}"}


def trigger_code_change_node(state: SupervisorState) -> dict:
    """
    Spawn a daemon thread to run the CodeChangeAgent for structural/unknown feedback.
    Non-blocking — returns immediately. The agent runs asynchronously in the background.
    Lazy-imports run_code_change_agent so this module loads even before code_change_agent.py exists.
    """
    import threading
    from supervisor.code_change_agent import run_code_change_agent  # lazy import

    run_id = str(uuid.uuid4())
    thread = threading.Thread(
        target=run_code_change_agent,
        args=(state["raw_reply"], state["digest_id"], run_id),
        daemon=True,
    )
    thread.start()
    log.info("supervisor_code_change_triggered", digest_id=state["digest_id"], run_id=run_id)
    return {**state, "action_taken": "triggered code_change_agent"}


def approve_code_change_node(state: SupervisorState) -> dict:
    """
    Execute git push to deploy a previously staged code change.
    Called when the user replies with "approve" or "approved" to a code change proposal email.
    """
    import subprocess
    import os

    cwd = os.getenv("RAILWAY_GIT_REPO_DIR", "/app")
    result = subprocess.run(
        ["git", "push"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )
    if result.returncode == 0:
        log.info("supervisor_code_change_approved", digest_id=state["digest_id"])
        action = "git push succeeded"
    else:
        log.error(
            "supervisor_code_change_push_failed",
            digest_id=state["digest_id"],
            stderr=result.stderr,
        )
        action = f"git push failed: {result.stderr.strip()}"

    return {**state, "action_taken": action}


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------


def route_after_acknowledge(state: SupervisorState) -> str:
    """
    After maybe_acknowledge:
    - feedback or both       → extract_change (process the config request)
    - acknowledge            → END (done — digest acknowledged, no config change)
    - command                → extract_command (determine which pipeline to trigger)
    - code_change_approval   → approve_code_change (run git push)
    - irrelevant             → no_op
    """
    reply_type = state.get("reply_type", "irrelevant")
    if reply_type in {"feedback", "both"}:
        return "extract_change"
    if reply_type == "acknowledge":
        return END
    if reply_type == "command":
        return "extract_command"
    if reply_type == "code_change_approval":
        return "approve_code_change"
    return "no_op"


def route_after_validate(state: SupervisorState) -> str:
    """
    After validation:
    - low risk    → apply_change
    - high risk   → queue_change
    - source      → reclassify_source
    - code_change → trigger_code_change
    - none        → no_op (unknown key, cannot act)
    """
    risk_level = state.get("risk_level", "none")
    if risk_level == "low":
        return "apply_change"
    if risk_level == "high":
        return "queue_change"
    if risk_level == "source":
        return "reclassify_source"
    if risk_level == "code_change":
        return "trigger_code_change"
    return "no_op"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

_builder = StateGraph(SupervisorState)

_builder.add_node("classify_reply", classify_reply_node)
_builder.add_node("maybe_acknowledge", maybe_acknowledge_node)
_builder.add_node("extract_change", extract_change_node)
_builder.add_node("validate_change", validate_change_node)
_builder.add_node("apply_change", apply_change_node)
_builder.add_node("queue_change", queue_change_node)
_builder.add_node("log_feedback_event", log_feedback_event_node)
_builder.add_node("no_op", no_op_node)
_builder.add_node("extract_command", extract_command_node)
_builder.add_node("execute_command", execute_command_node)
_builder.add_node("reclassify_source", reclassify_source_node)
_builder.add_node("trigger_code_change", trigger_code_change_node)
_builder.add_node("approve_code_change", approve_code_change_node)

_builder.add_edge(START, "classify_reply")
_builder.add_edge("classify_reply", "maybe_acknowledge")
_builder.add_conditional_edges("maybe_acknowledge", route_after_acknowledge)
_builder.add_edge("extract_change", "validate_change")
_builder.add_conditional_edges("validate_change", route_after_validate)
_builder.add_edge("apply_change", "log_feedback_event")
_builder.add_edge("queue_change", "log_feedback_event")
_builder.add_edge("log_feedback_event", END)
_builder.add_edge("no_op", END)
_builder.add_edge("extract_command", "execute_command")
_builder.add_edge("execute_command", END)
_builder.add_edge("reclassify_source", END)
_builder.add_edge("trigger_code_change", END)
_builder.add_edge("approve_code_change", END)

_graph = _builder.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_immediate_supervisor(
    digest_id: str,
    raw_reply: str,
    thread_id: str,
) -> SupervisorResult:
    """
    Process a user reply to a digest email through the immediate supervisor graph.

    Classifies the reply, marks the digest acknowledged if appropriate, extracts
    any proposed config change, validates risk level, applies low-risk changes
    immediately, and queues high-risk changes for human review.

    Args:
        digest_id: UUID of the digest this reply was sent in response to.
        raw_reply: Plain text body of the user's reply email.
        thread_id: Gmail thread ID of the digest email.

    Returns:
        SupervisorResult with action taken, config delta, and queued items.

    Raises:
        Exception if DB writes fail for critical paths (apply_change, queue_change).
        Non-critical failures (acknowledge, log_feedback_event) are caught internally.
    """
    log.info(
        "supervisor_immediate_start",
        digest_id=digest_id,
        thread_id=thread_id,
        reply_length=len(raw_reply),
    )

    initial_state: SupervisorState = {
        "digest_id": digest_id,
        "raw_reply": raw_reply,
        "thread_id": thread_id,
        "reply_type": "",
        "proposed_key": "",
        "proposed_value": None,
        "risk_level": "none",
        "extraction_reasoning": "",
        "command_target": "",
        "config_delta": {},
        "queued_items": [],
        "action_taken": "",
        "event_id": "",
        "command_triggered": "",
    }

    final_state = _graph.invoke(initial_state)

    result = SupervisorResult(
        action_taken=final_state.get("action_taken", "no action"),
        config_delta=final_state.get("config_delta", {}),
        queued_items=final_state.get("queued_items", []),
        reply_type=final_state.get("reply_type", "irrelevant"),
        command_triggered=final_state.get("command_triggered", ""),
    )

    log.info(
        "supervisor_immediate_complete",
        digest_id=digest_id,
        reply_type=result.reply_type,
        action_taken=result.action_taken,
        config_keys_changed=list(result.config_delta.keys()),
        queued_count=len(result.queued_items),
        command_triggered=result.command_triggered,
    )

    return result


def classify_command(text: str) -> str:
    """
    Classify free-form text as a pipeline command target.

    Used by main.py to classify self-addressed inbox command emails without
    going through the full supervisor graph (no digest_id context needed).

    Returns "daily_brief" or "deep_read". Defaults to "daily_brief" on any failure.
    """
    try:
        result = _extract_command_chain.invoke({"raw_reply": text})
        target = result.get("pipeline", "daily_brief")
        return target if target in {"daily_brief", "deep_read"} else "daily_brief"
    except Exception as e:
        log.warning("supervisor_classify_command_failed", error=str(e), action="defaulting to daily_brief")
        return "daily_brief"

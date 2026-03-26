"""
Supervisor — Immediate Mode (Phase 3).

Processes user replies to digest emails in real-time. Classifies the reply,
optionally acknowledges the digest, extracts any proposed config changes,
validates whether they are low-risk or high-risk, applies low-risk changes
immediately, and queues high-risk ones.

Graph structure:
  START → classify_reply → maybe_acknowledge → route_feedback →
          [extract_change → validate_change → (apply_change | queue_change) → log_feedback_event]
          → END

Reply types:
  acknowledge — user confirms they read the digest; no config change needed
  feedback    — user proposes a change; extract and validate it
  both        — acknowledgment + feedback; do both
  irrelevant  — unrelated reply; do nothing

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
LOW_RISK_CONFIG_KEYS = frozenset({"topic_weights", "word_budget", "cosine_similarity_threshold"})

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
    reply_type: one of acknowledge | feedback | both | irrelevant
    """
    action_taken: str
    config_delta: dict[str, Any] = field(default_factory=dict)
    queued_items: list[str] = field(default_factory=list)
    reply_type: str = "irrelevant"


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------


class SupervisorState(TypedDict):
    # Inputs
    digest_id: str
    raw_reply: str
    thread_id: str

    # Intermediate
    reply_type: str          # acknowledge | feedback | both | irrelevant
    proposed_key: str        # agent_config key the user wants to change
    proposed_value: Any      # new value to set
    risk_level: str          # low | high | none
    extraction_reasoning: str

    # Outputs accumulated across nodes
    config_delta: dict[str, Any]
    queued_items: list[str]
    action_taken: str
    event_id: str


# ---------------------------------------------------------------------------
# Prompt: classify reply
# Haiku is fast and cheap for this structured classification task.
# We ask for one of four literal strings to keep JsonOutputParser reliable.
# ---------------------------------------------------------------------------

# Returns one of: "acknowledge", "feedback", "both", "irrelevant"
_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You classify email replies to an AI news digest.

Return JSON only: {{"reply_type": "<type>"}}

Types:
- "acknowledge" — user confirms they read the digest (e.g. "thanks", "got it", "looks good")
- "feedback" — user requests a change (e.g. "less crypto", "more AI stories", "shorter please")
- "both" — reply contains both an acknowledgment AND a change request
- "irrelevant" — unrelated reply (forwarded email, out-of-office, spam)

Be conservative: only use "feedback" or "both" if the user is clearly requesting a change.""",
    ),
    ("human", "Digest reply:\n{raw_reply}"),
])

_classify_chain = _CLASSIFY_PROMPT | _haiku | JsonOutputParser()


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
        if reply_type not in {"acknowledge", "feedback", "both", "irrelevant"}:
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


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------


def route_after_acknowledge(state: SupervisorState) -> str:
    """
    After maybe_acknowledge:
    - feedback or both → extract_change (process the config request)
    - acknowledge → END (done — digest acknowledged, no config change)
    - irrelevant → no_op
    """
    reply_type = state.get("reply_type", "irrelevant")
    if reply_type in {"feedback", "both"}:
        return "extract_change"
    if reply_type == "acknowledge":
        return END
    return "no_op"


def route_after_validate(state: SupervisorState) -> str:
    """
    After validation:
    - low risk  → apply_change
    - high risk → queue_change
    - none      → no_op (unknown key, cannot act)
    """
    risk_level = state.get("risk_level", "none")
    if risk_level == "low":
        return "apply_change"
    if risk_level == "high":
        return "queue_change"
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

_builder.add_edge(START, "classify_reply")
_builder.add_edge("classify_reply", "maybe_acknowledge")
_builder.add_conditional_edges("maybe_acknowledge", route_after_acknowledge)
_builder.add_edge("extract_change", "validate_change")
_builder.add_conditional_edges("validate_change", route_after_validate)
_builder.add_edge("apply_change", "log_feedback_event")
_builder.add_edge("queue_change", "log_feedback_event")
_builder.add_edge("log_feedback_event", END)
_builder.add_edge("no_op", END)

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
        "config_delta": {},
        "queued_items": [],
        "action_taken": "",
        "event_id": "",
    }

    final_state = _graph.invoke(initial_state)

    result = SupervisorResult(
        action_taken=final_state.get("action_taken", "no action"),
        config_delta=final_state.get("config_delta", {}),
        queued_items=final_state.get("queued_items", []),
        reply_type=final_state.get("reply_type", "irrelevant"),
    )

    log.info(
        "supervisor_immediate_complete",
        digest_id=digest_id,
        reply_type=result.reply_type,
        action_taken=result.action_taken,
        config_keys_changed=list(result.config_delta.keys()),
        queued_count=len(result.queued_items),
    )

    return result

"""
Supervisor — Weekly Pattern Sweep (Phase 5).

Runs Sunday morning before the weekend catch-up. Analyzes the past week's digest
engagement and feedback, applies low-risk config changes, and sends a weekly review
email summarizing observations and any proposed changes needing user approval.

Graph structure:
  START → gather_data → analyze_patterns → apply_changes → compose_email → send_email → END

Data sources:
  - get_weekly_digest_stats: sent/ack counts and word counts for the week
  - get_recent_feedback: raw replies, supervisor interpretations, applied changes

Risk model (matches immediate supervisor):
  low-risk  — topic_weights, word_budget, cosine_similarity_threshold
               Applied immediately without user approval.
  high-risk — prompt edits, source changes, structural changes
               Listed in the review email; user approves by replying.

Model selection:
  Opus for pattern analysis — this is complex reasoning over a week of data,
  not a structured classification task. Haiku would miss subtle patterns.

Why LangGraph (not LCEL):
  Consistent with immediate.py. Future versions may add conditional branches
  (e.g. skip send_email if no data this week, loop for multi-step approval).
  See CLAUDE.md Non-Obvious Design Decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypedDict

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from config import settings
from tools.db import (
    get_recent_feedback,
    get_weekly_digest_stats,
    insert_feedback_event,
    mark_feedback_applied,
    set_config,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants — shared with immediate supervisor
# ---------------------------------------------------------------------------

LOW_RISK_CONFIG_KEYS = frozenset({"topic_weights", "word_budget", "cosine_similarity_threshold"})

# ---------------------------------------------------------------------------
# LLM client — Opus for pattern analysis (complex reasoning, not classification)
# ---------------------------------------------------------------------------

_opus = ChatAnthropic(
    model="claude-opus-4-6",
    api_key=settings.anthropic_api_key,
    max_tokens=1024,
    temperature=0,
)

# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass
class WeeklySupervisorResult:
    """
    Result returned by run_weekly_supervisor().

    action_taken: human-readable summary of what the supervisor did
    changes_applied: {key: new_value} for any config keys immediately updated
    email_sent: whether the weekly review email was delivered
    """
    action_taken: str
    changes_applied: dict[str, Any] = field(default_factory=dict)
    email_sent: bool = False


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------


class WeeklySupervisorState(TypedDict):
    run_id: str

    # Gathered data
    feedback_events: list[dict]
    digest_stats: list[dict]

    # Analysis output (from Opus)
    observations: list[str]
    low_risk_changes: list[dict]    # [{"key": ..., "value": ..., "reason": ...}]
    high_risk_proposals: list[dict] # [{"description": ..., "reason": ...}]

    # Applied changes
    changes_applied: dict[str, Any]

    # Email
    email_body: str
    email_sent: bool
    action_taken: str


# ---------------------------------------------------------------------------
# Prompt: analyze patterns
# Opus reasons over a week of engagement and feedback data.
# We ask for structured JSON so downstream nodes can apply low-risk changes
# without additional parsing. The "be conservative" instruction is deliberate —
# better to observe and propose than to silently change config with weak signal.
# ---------------------------------------------------------------------------

_ANALYZE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a weekly pattern analyst for a personal AI news digest system.
Analyze the past week of digest engagement and user feedback.

Low-risk config keys you may apply immediately:
- "topic_weights": object mapping topic → float weight (e.g. {{"ai": 1.5, "crypto": 0.3}})
- "word_budget": object with budget keys (e.g. {{"daily_brief_total": 2500}})
- "cosine_similarity_threshold": float 0.0–1.0

High-risk changes (require user approval — list in proposals, do NOT apply):
- prompt edits, source changes, structural format changes, anything else

Return JSON only:
{{
  "observations": ["string", ...],
  "low_risk_changes": [{{"key": "...", "value": ..., "reason": "one sentence"}}],
  "high_risk_proposals": [{{"description": "...", "reason": "one sentence"}}]
}}

Rules:
- Be conservative. Only propose changes when you see clear signal from multiple data points.
- If there is insufficient data (fewer than 3 digests sent), note it in observations and propose nothing.
- Do not re-propose changes that were already applied this week (check feedback_events.applied=true).
- observations must be concrete and specific (e.g. "3 of 5 daily briefs unacknowledged this week" not "low engagement").""",
    ),
    (
        "human",
        "DIGEST STATS (past 7 days):\n{digest_summary}\n\nFEEDBACK EVENTS (past 7 days):\n{feedback_summary}",
    ),
])

_analyze_chain = _ANALYZE_PROMPT | _opus | JsonOutputParser()


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def gather_data_node(state: WeeklySupervisorState) -> dict:
    """
    Fetch feedback events and digest stats for the past 7 days.
    Non-fatal: empty lists returned on DB failure — analysis will note insufficient data.
    """
    try:
        feedback_events = get_recent_feedback(days_back=7)
    except Exception as e:
        log.warning("weekly_supervisor_feedback_fetch_failed", run_id=state["run_id"], error=str(e))
        feedback_events = []

    try:
        digest_stats = get_weekly_digest_stats(days_back=7)
    except Exception as e:
        log.warning("weekly_supervisor_stats_fetch_failed", run_id=state["run_id"], error=str(e))
        digest_stats = []

    log.info(
        "weekly_supervisor_data_gathered",
        run_id=state["run_id"],
        feedback_count=len(feedback_events),
        digest_count=len(digest_stats),
    )
    return {**state, "feedback_events": feedback_events, "digest_stats": digest_stats}


def analyze_patterns_node(state: WeeklySupervisorState) -> dict:
    """
    Use Opus to reason over the week's data and identify observations and proposed changes.
    Defaults to safe empty lists on LLM failure — the email will still be sent with a note.
    """
    digest_summary = _format_digest_summary(state["digest_stats"])
    feedback_summary = _format_feedback_summary(state["feedback_events"])

    try:
        result = _analyze_chain.invoke({
            "digest_summary": digest_summary,
            "feedback_summary": feedback_summary,
        })
        observations = result.get("observations", [])
        low_risk_changes = result.get("low_risk_changes", [])
        high_risk_proposals = result.get("high_risk_proposals", [])
    except Exception as e:
        log.warning(
            "weekly_supervisor_analysis_failed",
            run_id=state["run_id"],
            error=str(e),
        )
        observations = [f"Pattern analysis failed this week: {e}"]
        low_risk_changes = []
        high_risk_proposals = []

    log.info(
        "weekly_supervisor_analysis_complete",
        run_id=state["run_id"],
        observation_count=len(observations),
        low_risk_count=len(low_risk_changes),
        high_risk_count=len(high_risk_proposals),
    )
    return {
        **state,
        "observations": observations,
        "low_risk_changes": low_risk_changes,
        "high_risk_proposals": high_risk_proposals,
    }


def apply_changes_node(state: WeeklySupervisorState) -> dict:
    """
    Apply low-risk config changes identified by the pattern analysis.
    Only applies keys in LOW_RISK_CONFIG_KEYS — anything else is silently skipped
    (it should have been in high_risk_proposals, not low_risk_changes).
    Logs each applied change as a feedback event. Non-fatal per change.
    """
    changes_applied: dict[str, Any] = {}

    for change in state.get("low_risk_changes", []):
        key = change.get("key", "")
        value = change.get("value")
        reason = change.get("reason", "")

        if key not in LOW_RISK_CONFIG_KEYS:
            log.warning(
                "weekly_supervisor_skipped_unsafe_key",
                run_id=state["run_id"],
                key=key,
            )
            continue

        try:
            set_config(key, value, updated_by="supervisor")
            changes_applied[key] = value

            # Log as an applied feedback event for future pattern analysis
            event_id = insert_feedback_event(
                digest_id="weekly-sweep",
                raw_reply=f"[weekly sweep] {reason}",
                supervisor_interpretation=reason,
                proposed_change=json.dumps({"key": key, "value": value}),
            )
            mark_feedback_applied(event_id)

            log.info(
                "weekly_supervisor_change_applied",
                run_id=state["run_id"],
                key=key,
                reason=reason,
            )
        except Exception as e:
            log.error(
                "weekly_supervisor_change_failed",
                run_id=state["run_id"],
                key=key,
                error=str(e),
            )

    return {**state, "changes_applied": changes_applied}


def compose_email_node(state: WeeklySupervisorState) -> dict:
    """
    Format the weekly review email from the analysis results.
    Always produces a non-empty body — even a no-data week gets a minimal email.
    """
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    lines: list[str] = [
        f"WEEKLY DIGEST REVIEW — {today}",
        "",
        "─" * 50,
    ]

    # Changes applied this week
    changes_applied = state.get("changes_applied", {})
    lines.append("CHANGES APPLIED THIS WEEK")
    lines.append("─" * 50)
    if changes_applied:
        for key, value in changes_applied.items():
            lines.append(f"• {key} updated to {json.dumps(value)}")
    else:
        lines.append("No config changes were applied this week.")
    lines.append("")

    # Observations
    lines.append("─" * 50)
    lines.append("OBSERVATIONS")
    lines.append("─" * 50)
    observations = state.get("observations", [])
    if observations:
        for obs in observations:
            lines.append(f"• {obs}")
    else:
        lines.append("No notable patterns this week.")
    lines.append("")

    # Proposed changes
    high_risk = state.get("high_risk_proposals", [])
    if high_risk:
        lines.append("─" * 50)
        lines.append("PROPOSED CHANGES (reply to approve)")
        lines.append("─" * 50)
        for i, proposal in enumerate(high_risk, 1):
            desc = proposal.get("description", "")
            reason = proposal.get("reason", "")
            lines.append(f"{i}. {desc}")
            if reason:
                lines.append(f"   Why: {reason}")
        lines.append("")

    lines.append("─" * 50)
    lines.append("Reply to approve any proposed changes, or just ignore this email.")
    lines.append("─" * 50)

    return {**state, "email_body": "\n".join(lines)}


def send_email_node(state: WeeklySupervisorState) -> dict:
    """
    Send the weekly review email via GmailService.
    Raises on failure — a silent send failure means the user never sees the review.
    """
    from gmail_service import GmailService

    gmail = GmailService()
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    subject = f"Weekly Digest Review — {today}"

    gmail.send_message(
        to=settings.gmail_send_as,
        subject=subject,
        body=state["email_body"],
    )
    log.info("weekly_supervisor_email_sent", run_id=state["run_id"], subject=subject)

    changes_applied = state.get("changes_applied", {})
    action_parts = [f"sent weekly review email"]
    if changes_applied:
        action_parts.append(f"applied {len(changes_applied)} config change(s)")

    return {**state, "email_sent": True, "action_taken": "; ".join(action_parts)}


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

_builder = StateGraph(WeeklySupervisorState)

_builder.add_node("gather_data", gather_data_node)
_builder.add_node("analyze_patterns", analyze_patterns_node)
_builder.add_node("apply_changes", apply_changes_node)
_builder.add_node("compose_email", compose_email_node)
_builder.add_node("send_email", send_email_node)

_builder.add_edge(START, "gather_data")
_builder.add_edge("gather_data", "analyze_patterns")
_builder.add_edge("analyze_patterns", "apply_changes")
_builder.add_edge("apply_changes", "compose_email")
_builder.add_edge("compose_email", "send_email")
_builder.add_edge("send_email", END)

_graph = _builder.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_weekly_supervisor(run_id: str) -> WeeklySupervisorResult:
    """
    Run the weekly pattern sweep: analyze past week, apply low-risk changes,
    send a review email with observations and proposed changes.

    Args:
        run_id: Unique ID for this run, propagated through logs.

    Returns:
        WeeklySupervisorResult with action taken, changes applied, and send status.

    Raises:
        Exception if the email send fails (GmailService error).
        All other failures (DB reads, LLM analysis) are non-fatal and noted in the email.
    """
    log.info("weekly_supervisor_start", run_id=run_id)

    initial_state: WeeklySupervisorState = {
        "run_id": run_id,
        "feedback_events": [],
        "digest_stats": [],
        "observations": [],
        "low_risk_changes": [],
        "high_risk_proposals": [],
        "changes_applied": {},
        "email_body": "",
        "email_sent": False,
        "action_taken": "",
    }

    final_state = _graph.invoke(initial_state)

    result = WeeklySupervisorResult(
        action_taken=final_state.get("action_taken", "no action"),
        changes_applied=final_state.get("changes_applied", {}),
        email_sent=final_state.get("email_sent", False),
    )

    log.info(
        "weekly_supervisor_complete",
        run_id=run_id,
        action_taken=result.action_taken,
        changes_applied=list(result.changes_applied.keys()),
        email_sent=result.email_sent,
    )

    return result


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_digest_summary(digest_stats: list[dict]) -> str:
    """Format digest stats into a concise summary for the LLM prompt."""
    if not digest_stats:
        return "No digests sent this week."

    total = len(digest_stats)
    acked = sum(1 for d in digest_stats if d.get("acknowledged_at"))
    by_type: dict[str, int] = {}
    for d in digest_stats:
        dtype = d.get("type", "unknown")
        by_type[dtype] = by_type.get(dtype, 0) + 1

    lines = [
        f"Total digests sent: {total}",
        f"Acknowledged: {acked}/{total}",
        f"By type: {', '.join(f'{k}={v}' for k, v in by_type.items())}",
    ]

    # List each digest with ack status and date
    for d in digest_stats:
        sent = d.get("sent_at", "")
        if hasattr(sent, "strftime"):
            sent = sent.strftime("%a %b %d")
        ack = "acked" if d.get("acknowledged_at") else "NOT acked"
        dtype = d.get("type", "")
        words = d.get("word_count") or "?"
        lines.append(f"  {sent} | {dtype} | {words} words | {ack}")

    return "\n".join(lines)


def _format_feedback_summary(feedback_events: list[dict]) -> str:
    """Format feedback events into a concise summary for the LLM prompt."""
    if not feedback_events:
        return "No feedback received this week."

    lines = [f"Total feedback events: {len(feedback_events)}"]
    for event in feedback_events:
        reply = (event.get("raw_reply") or "")[:100]
        interpretation = event.get("supervisor_interpretation") or ""
        applied = "applied" if event.get("applied") else "queued/pending"
        lines.append(f"  Reply: {reply!r}")
        lines.append(f"  Interpretation: {interpretation} [{applied}]")
    return "\n".join(lines)

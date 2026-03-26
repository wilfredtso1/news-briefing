"""
Onboarding pipeline — Phase 6.

First-run flow: scans the inbox for newsletters, emails the user a
prioritization question, and uses the reply to set initial topic weights
and source trust weights before the first daily brief runs.

Entry points:
  run_onboarding(run_id)                        — scan inbox and send setup email (idempotent)
  process_onboarding_reply(event_id, raw_reply) — parse reply and apply preferences

Why this is separate from the supervisor:
  The supervisor processes replies to digest emails; feedback_events.digest_id
  is NOT NULL. Onboarding has no digest — it uses onboarding_events.
  See DECISIONS.md 2026-03-26.

Model: Haiku for reply parsing — structured JSON extraction, not open-ended reasoning.
"""

from __future__ import annotations

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

import source_classifier
from config import settings
from gmail_service import GmailService
from tools.db import (
    create_onboarding_event,
    deprioritize_source,
    get_active_sources,
    get_config,
    get_pending_onboarding_event,
    mark_onboarding_applied,
    set_config,
    update_onboarding_thread,
    update_source_trust_weight,
)

log = structlog.get_logger(__name__)

# Trust weight applied to sources the user marks as important.
# 1.0 is neutral; 1.8 gives these sources a strong ranking boost.
_IMPORTANT_SOURCE_TRUST_WEIGHT = 1.8

# ---------------------------------------------------------------------------
# LLM client
# Haiku: reply parsing is structured JSON extraction, not open-ended reasoning.
# ---------------------------------------------------------------------------

_haiku = ChatAnthropic(
    model="claude-haiku-4-5",
    api_key=settings.anthropic_api_key,
    max_tokens=1024,
    temperature=0,
)

# ---------------------------------------------------------------------------
# Prompt: parse onboarding reply
#
# The user replies in free-form text describing which sources and topics they
# care about. We provide the discovered source list so the LLM can match
# names to email addresses (e.g. "Axios" → axiosam@axios.com).
#
# Output format: four keys so the pipeline can apply preferences directly
# without further parsing. We list exact topic keys used in agent_config
# so the LLM doesn't invent new names.
# ---------------------------------------------------------------------------

_PARSE_REPLY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You parse a user's reply to a newsletter setup email and extract their preferences.

You will be given:
1. A list of discovered newsletter sources (name + email)
2. The user's free-form reply

Return JSON only:
{{
  "important_sources": ["email@example.com"],
  "deprioritize_sources": ["email@example.com"],
  "unsubscribe_sources": ["email@example.com"],
  "topic_adjustments": {{"topic_name": 1.5}},
  "notes": "one sentence summary"
}}

Rules:
- Match source names in the reply to emails from the list (case-insensitive, partial match OK)
- important_sources: sources the user says they value, want more of, or called out positively
- deprioritize_sources: sources the user said they care less about but did NOT ask to remove
- unsubscribe_sources: sources the user explicitly asked to stop receiving (must be explicit)
- topic_adjustments: float multipliers for topic weights (>1.0 = boost, <1.0 = reduce)
  Valid topic keys: ai, health_tech, venture_capital, financial_markets, tech, crypto, sports, entertainment
- "I don't care about X" → deprioritize, NOT unsubscribe. Only use unsubscribe for explicit removal requests.
- If the reply is vague or gives no actionable preferences, return empty lists and an empty dict.""",
    ),
    (
        "human",
        "Discovered sources:\n{sources_list}\n\nUser reply:\n{raw_reply}",
    ),
])

_parse_reply_chain = _PARSE_REPLY_PROMPT | _haiku | JsonOutputParser()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_onboarding(run_id: str) -> dict:
    """
    Scan the inbox for newsletters and send the user a setup email.

    Idempotent: no-ops if onboarding is already complete or if a setup email
    is pending a reply. Safe to call on every poll cycle.

    Returns a dict with a 'status' key:
      'already_complete'  — onboarding_complete is True; nothing to do
      'pending_reply'     — setup email already sent; waiting for user reply
      'sent'              — setup email sent successfully this run
      'no_sources_found'  — inbox scan found no newsletters (logged as warning)
    """
    if get_config("onboarding_complete") is True:
        log.info("onboarding_already_complete", run_id=run_id)
        return {"status": "already_complete"}

    pending = get_pending_onboarding_event()
    if pending:
        log.info(
            "onboarding_pending_reply",
            run_id=run_id,
            event_id=str(pending["id"]),
            thread_id=pending.get("thread_id"),
        )
        return {"status": "pending_reply"}

    gmail = GmailService()

    # Scan inbox — classify every unread message, collect newsletters
    message_ids = gmail.list_inbox_messages(max_results=200)
    messages = gmail.get_messages(message_ids)

    discovered: dict[str, dict] = {}  # sender_email → {name, type}
    for msg in messages:
        result = source_classifier.classify(msg)
        if result.is_newsletter:
            discovered[result.sender_email] = {
                "name": result.sender_name,
                "type": result.source_type,
            }

    # Merge in already-known active sources so the list is complete even
    # if the relevant newsletters haven't arrived in today's inbox yet
    for source in get_active_sources():
        email = source["sender_email"]
        if email not in discovered:
            discovered[email] = {"name": source["name"], "type": source["type"]}

    if not discovered:
        log.warning("onboarding_no_sources_found", run_id=run_id)
        return {"status": "no_sources_found"}

    log.info("onboarding_sources_discovered", run_id=run_id, count=len(discovered))

    # Create the DB row before sending — prevents a duplicate send if the
    # thread ID write fails after the email goes out
    event_id = create_onboarding_event()

    body = _format_setup_email(discovered)
    message_id, thread_id = gmail.send_message(
        to=settings.gmail_send_as,
        subject="News Briefing Agent setup — which sources matter most?",
        body=body,
    )

    update_onboarding_thread(event_id, thread_id, message_id)
    log.info("onboarding_email_sent", run_id=run_id, event_id=event_id, thread_id=thread_id)
    return {"status": "sent"}


def process_onboarding_reply(event_id: str, raw_reply: str, run_id: str) -> dict:
    """
    Parse the user's reply to the setup email and apply their preferences.

    Extracts source priorities and topic preferences from free-form text,
    writes trust_weight updates to newsletter_sources, merges topic_adjustments
    into agent_config topic_weights, and marks onboarding complete.

    Unsubscribe requests are logged but not executed — per AGENT_INSTRUCTIONS.md,
    unsubscribes require separate explicit confirmation.

    Returns a dict with 'applied_changes' and 'notes'.
    """
    active_sources = get_active_sources()
    sources_list = "\n".join(
        f"- {s['name']} ({s['sender_email']}) — {s['type']}"
        for s in active_sources
    )

    try:
        parsed = _parse_reply_chain.invoke({
            "sources_list": sources_list,
            "raw_reply": raw_reply,
        })
    except Exception as e:
        log.warning("onboarding_parse_failed", run_id=run_id, error=str(e))
        parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "notes": f"parse failed: {e}",
        }

    applied: list[str] = []

    for email in parsed.get("important_sources", []):
        try:
            update_source_trust_weight(email, _IMPORTANT_SOURCE_TRUST_WEIGHT)
            applied.append(f"boosted trust_weight for {email}")
        except Exception as e:
            log.warning("onboarding_trust_weight_failed", run_id=run_id, email=email, error=str(e))

    for email in parsed.get("deprioritize_sources", []):
        try:
            deprioritize_source(email)
            applied.append(f"deprioritized {email}")
        except Exception as e:
            log.warning("onboarding_deprioritize_failed", run_id=run_id, email=email, error=str(e))

    # Log unsubscribe requests but do NOT execute — requires separate confirmation
    for email in parsed.get("unsubscribe_sources", []):
        log.info(
            "onboarding_unsubscribe_noted",
            run_id=run_id,
            email=email,
            note="unsubscribe requires explicit confirmation per AGENT_INSTRUCTIONS.md",
        )
        applied.append(f"unsubscribe requested for {email} (pending confirmation)")

    topic_adjustments = parsed.get("topic_adjustments", {})
    if topic_adjustments:
        existing_weights = get_config("topic_weights") or {}
        merged = {**existing_weights, **topic_adjustments}
        try:
            set_config("topic_weights", merged, updated_by="onboarding")
            applied.append(f"topic_weights updated: {sorted(topic_adjustments.keys())}")
        except Exception as e:
            log.warning("onboarding_topic_weights_failed", run_id=run_id, error=str(e))

    mark_onboarding_applied(event_id, raw_reply, parsed)
    set_config("onboarding_complete", True, updated_by="onboarding")

    log.info(
        "onboarding_complete",
        run_id=run_id,
        event_id=event_id,
        applied_count=len(applied),
        notes=parsed.get("notes", ""),
    )
    return {"applied_changes": applied, "notes": parsed.get("notes", "")}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_setup_email(discovered: dict[str, dict]) -> str:
    """
    Format the onboarding setup email listing discovered newsletters.
    Splits sources into daily brief and long-form sections.
    Plain text only — matches the project-wide no-HTML-email rule.
    """
    news_brief = [(e, d) for e, d in discovered.items() if d["type"] == "news_brief"]
    long_form = [(e, d) for e, d in discovered.items() if d["type"] == "long_form"]

    lines = ["I scanned your inbox and found these newsletters:", ""]

    if news_brief:
        lines.append("Daily Brief:")
        for email, data in sorted(news_brief, key=lambda x: x[1]["name"].lower()):
            lines.append(f"  - {data['name']} ({email})")
        lines.append("")

    if long_form:
        lines.append("Long-Form / Deep Read:")
        for email, data in sorted(long_form, key=lambda x: x[1]["name"].lower()):
            lines.append(f"  - {data['name']} ({email})")
        lines.append("")

    lines += [
        "Reply with:",
        "1. Your most important sources (I'll prioritize these in every digest)",
        "2. Anything to deprioritize or less of",
        "3. Any topic preferences (e.g. \"more AI, less crypto\")",
        "",
        "The first daily brief runs after I hear back.",
    ]

    return "\n".join(lines)

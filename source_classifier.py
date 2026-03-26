"""
Newsletter source classifier.

Determines whether an inbox email is:
  - A newsletter (and if so, 'news_brief' or 'long_form')
  - A personal/transactional email (skip)

Classification priority:
  1. List-Unsubscribe header — strongest signal, legally required on bulk email
  2. List-Id header — also a bulk-mail indicator
  3. Sender pattern matching against known sources
  4. Body length heuristic — long_form emails are typically >1,500 words

No LLM is used for classification — this is deterministic and fast.
All new sources are upserted into newsletter_sources for the registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

from gmail_service import EmailMessage
from tools.db import get_source_by_email, upsert_newsletter_source

log = structlog.get_logger(__name__)

# Words above this threshold → long_form (Stratechery, Money Stuff etc.)
LONG_FORM_WORD_THRESHOLD = 1_500

# Senders we know are news_brief regardless of length
KNOWN_NEWS_BRIEF_SENDERS = {
    "axiosam@axios.com",
    "newsletters@axios.com",
    "morningbrew@morningbrew.com",
    "hello@morningbrew.com",
    "rundown@therundown.ai",
    "hello@tldr.tech",
    "newsletters@a16z.com",
    "hello@healthtechnerds.com",
    "crew@morningbrew.com",    # Morning Brew — long body but is a news brief
    "markets@axios.com",       # Axios Markets
}

# Senders we know are long_form
KNOWN_LONG_FORM_SENDERS = {
    "newsletters@stratechery.com",
    "moneystuff@bloomberg.net",
}

# Patterns that indicate transactional / personal email — skip these
SKIP_PATTERNS = [
    r"noreply@",
    r"no-reply@",
    r"donotreply@",
    r"notifications@",
    r"support@",
    r"security@",
    r"billing@",
    r"invoice@",
    r"receipt@",
    r"confirmation@",
    r"verify@",
]


@dataclass
class ClassificationResult:
    is_newsletter: bool
    source_type: str | None   # 'news_brief', 'long_form', or None if not a newsletter
    sender_email: str
    sender_name: str
    confidence: str           # 'high', 'medium', 'low'
    reason: str               # Human-readable explanation for debugging


def classify(message: EmailMessage) -> ClassificationResult:
    """
    Classify a single email message and upsert into newsletter_sources if it's a newsletter.

    Side effect: calls upsert_newsletter_source for any classified newsletter,
    so the registry stays current across pipeline runs.
    """
    sender = message.sender_email
    sender_name = _extract_name(message.sender)

    # --- Skip obvious non-newsletters ---
    if _is_skip_sender(sender):
        log.debug("classified_skip", sender=sender, reason="transactional_pattern")
        return ClassificationResult(
            is_newsletter=False, source_type=None, sender_email=sender,
            sender_name=sender_name, confidence="high", reason="transactional sender pattern",
        )

    # --- Known senders (highest confidence) ---
    if sender in KNOWN_NEWS_BRIEF_SENDERS:
        result = ClassificationResult(
            is_newsletter=True, source_type="news_brief", sender_email=sender,
            sender_name=sender_name, confidence="high", reason="known news_brief sender",
        )
        _register(message, result)
        return result

    if sender in KNOWN_LONG_FORM_SENDERS:
        result = ClassificationResult(
            is_newsletter=True, source_type="long_form", sender_email=sender,
            sender_name=sender_name, confidence="high", reason="known long_form sender",
        )
        _register(message, result)
        return result

    # --- DB lookup: check for user-confirmed type before running length heuristic ---
    try:
        existing = get_source_by_email(sender)
        if existing and existing.get("type") in ("news_brief", "long_form"):
            result = ClassificationResult(
                is_newsletter=True, source_type=existing["type"], sender_email=sender,
                sender_name=sender_name, confidence="high",
                reason=f"DB override: user-confirmed type={existing['type']}",
            )
            _register(message, result)
            return result
    except Exception as e:
        log.warning("classifier_db_lookup_failed", sender=sender, error=str(e))
        # Fall through to heuristic

    # --- List-Unsubscribe header (strong signal — legally required on bulk mail) ---
    if message.list_unsubscribe:
        source_type = _classify_type_by_length(message.body_text)
        result = ClassificationResult(
            is_newsletter=True, source_type=source_type, sender_email=sender,
            sender_name=sender_name, confidence="high",
            reason=f"List-Unsubscribe header present; type by length → {source_type}",
        )
        _register(message, result)
        return result

    # --- List-Id header (also a bulk-mail signal) ---
    if message.list_id:
        source_type = _classify_type_by_length(message.body_text)
        result = ClassificationResult(
            is_newsletter=True, source_type=source_type, sender_email=sender,
            sender_name=sender_name, confidence="medium",
            reason=f"List-Id header present; type by length → {source_type}",
        )
        _register(message, result)
        return result

    # --- Not enough signal — treat as personal/transactional ---
    log.debug("classified_not_newsletter", sender=sender, reason="no_bulk_headers")
    return ClassificationResult(
        is_newsletter=False, source_type=None, sender_email=sender,
        sender_name=sender_name, confidence="medium", reason="no bulk-mail headers found",
    )


def is_anchor_present(messages: list[EmailMessage], anchor_email: str) -> bool:
    """Return True if any message in the list is from the given anchor sender."""
    return any(m.sender_email == anchor_email for m in messages)


def all_anchors_present(messages: list[EmailMessage], anchor_emails: tuple[str, ...]) -> bool:
    """Return True only when every anchor sender has at least one message in the batch."""
    present = {m.sender_email for m in messages}
    missing = [a for a in anchor_emails if a not in present]
    if missing:
        log.info("anchors_missing", missing=missing)
        return False
    return True


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _classify_type_by_length(body_text: str) -> str:
    """
    Use word count as a proxy for content density.
    Long-form newsletters (Stratechery, Money Stuff) are typically essay-length.
    """
    word_count = len(body_text.split())
    return "long_form" if word_count >= LONG_FORM_WORD_THRESHOLD else "news_brief"


def _is_skip_sender(sender_email: str) -> bool:
    """Return True if the sender matches any transactional/skip pattern."""
    return any(re.search(pattern, sender_email, re.IGNORECASE) for pattern in SKIP_PATTERNS)


def _extract_name(sender: str) -> str:
    """
    Extract display name from 'Name <email>' format.
    Falls back to the email address itself.
    """
    match = re.match(r'^"?([^"<]+)"?\s*<', sender)
    return match.group(1).strip() if match else sender.split("@")[0]


def _register(message: EmailMessage, result: ClassificationResult) -> None:
    """Upsert the source into newsletter_sources and log the classification."""
    try:
        upsert_newsletter_source(
            sender_email=result.sender_email,
            name=result.sender_name,
            source_type=result.source_type,
            unsubscribe_header=message.list_unsubscribe,
        )
    except Exception as e:
        # Registration failure must not crash the classifier
        log.warning("source_registration_failed", sender=result.sender_email, error=str(e))

    log.info(
        "source_classified",
        sender=result.sender_email,
        type=result.source_type,
        confidence=result.confidence,
        reason=result.reason,
    )

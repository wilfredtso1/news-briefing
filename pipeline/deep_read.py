"""
Deep Read pipeline.

Processes long-form newsletter content (essays, analyses, deep dives) that
are routed away from the daily brief. Runs when the long-form queue reaches
the configured threshold (default: 5 pieces), or as a Thursday fallback.

Each article is presented individually at full depth — no cross-source synthesis.
The original sender and subject are included so the reader can access the source.

Entry point: run_deep_read(run_id) -> dict
"""

from __future__ import annotations

import re
from datetime import datetime

import structlog

from gmail_service import EmailMessage, GmailService
from pipeline.extractor import ExtractedStory, extract_stories
from tools.db import (
    create_digest,
    get_active_sources,
    get_config,
    get_or_create_cluster,
    insert_story,
    mark_digest_sent,
)

log = structlog.get_logger(__name__)

# How many articles to include in a single Deep Read digest
_MIN_ARTICLES = 3
_MAX_ARTICLES = 5

# Default threshold — abort if fewer long-form pieces available.
# Overridden by agent_config key "deep_read_threshold".
_DEFAULT_THRESHOLD = 5


def run_deep_read(run_id: str, dry_run: bool = False) -> dict:
    """
    Execute the deep read pipeline.

    Queries active long_form newsletter sources, fetches their unread emails,
    checks the configured queue threshold, extracts article content, formats
    a depth-first digest (3–5 articles, each at full treatment), and sends it.

    Args:
        run_id: Unique identifier for this pipeline run (propagated to all logs).
        dry_run: If True, skips sending email and archiving.

    Returns a dict with articles_included, word_count, digest_id.
    Raises on unrecoverable errors (DB failure, email delivery failure).
    """
    log.info("deep_read_start", run_id=run_id, dry_run=dry_run)

    gmail = GmailService()

    # --- Step 1: Fetch unread long-form emails ---
    long_form_messages = _fetch_long_form_messages(gmail)
    log.info("deep_read_fetched", run_id=run_id, message_count=len(long_form_messages))

    # --- Step 2: Check threshold ---
    threshold = _load_threshold()
    if len(long_form_messages) < threshold:
        log.info(
            "deep_read_below_threshold",
            run_id=run_id,
            available=len(long_form_messages),
            threshold=threshold,
        )
        return {
            "run_id": run_id,
            "status": "below_threshold",
            "available": len(long_form_messages),
            "threshold": threshold,
            "articles_included": 0,
        }

    # --- Step 3: Select articles (cap at _MAX_ARTICLES) ---
    selected_messages = long_form_messages[:_MAX_ARTICLES]

    # --- Step 4: Extract content via extractor.py ---
    articles = _extract_articles(selected_messages)
    log.info("deep_read_extracted", run_id=run_id, article_count=len(articles))

    if len(articles) < _MIN_ARTICLES:
        log.info(
            "deep_read_insufficient_articles",
            run_id=run_id,
            extracted=len(articles),
            minimum=_MIN_ARTICLES,
        )
        return {
            "run_id": run_id,
            "status": "insufficient_articles",
            "articles_included": len(articles),
        }

    # --- Step 5: Format digest body ---
    # Each article is presented individually at full depth.
    # No synthesis — we preserve each piece's distinct voice and argument.
    date_str = datetime.now().strftime("%A, %B %-d")
    subject, body = _format_deep_read(articles, date_str)
    word_count = len(body.split())

    log.info(
        "deep_read_formatted",
        run_id=run_id,
        article_count=len(articles),
        word_count=word_count,
    )

    if dry_run:
        return {
            "run_id": run_id,
            "status": "dry_run",
            "articles_included": len(articles),
            "word_count": word_count,
            "subject": subject,
        }

    # --- Step 6: Send via Gmail ---
    from config import settings
    sent_message_id = gmail.send_message(
        to=settings.gmail_send_as,
        subject=subject,
        body=body,
    )
    log.info("deep_read_sent", run_id=run_id, gmail_message_id=sent_message_id)

    # --- Step 7: Archive source emails ---
    archive_ids = [msg.message_id for msg in selected_messages]
    gmail.archive_messages(archive_ids)
    log.info("deep_read_archived", run_id=run_id, count=len(archive_ids))

    # --- Step 8: Persist digest record ---
    digest_id = _persist_digest(run_id=run_id, articles=articles, word_count=word_count)

    log.info(
        "deep_read_complete",
        run_id=run_id,
        digest_id=digest_id,
        articles_included=len(articles),
        word_count=word_count,
    )

    return {
        "run_id": run_id,
        "status": "sent",
        "digest_id": digest_id,
        "articles_included": len(articles),
        "word_count": word_count,
    }


def _fetch_long_form_messages(gmail: GmailService) -> list[EmailMessage]:
    """
    Fetch unread emails from known long_form sources.

    Uses the Gmail API to list inbox messages, then filters to senders that
    appear in the newsletter_sources table as type='long_form' and status='active'.
    """
    # Load long_form senders from DB — avoid fetching all inbox messages blindly
    all_sources = get_active_sources()
    long_form_senders = {
        s["sender_email"]
        for s in all_sources
        if s.get("type") == "long_form" and s.get("status") == "active"
    }

    if not long_form_senders:
        log.info("deep_read_no_long_form_sources")
        return []

    # Fetch inbox messages and filter to long_form senders
    message_ids = gmail.list_inbox_messages(max_results=100)
    if not message_ids:
        return []

    messages = gmail.get_messages(message_ids)
    return [m for m in messages if m.sender_email in long_form_senders]


def _load_threshold() -> int:
    """
    Load the deep_read_threshold from agent_config.

    Falls back to _DEFAULT_THRESHOLD if the key is missing or malformed.
    The supervisor can lower this to trigger more frequent deep reads.
    """
    try:
        raw = get_config("deep_read_threshold")
        if raw is not None:
            return int(raw)
    except Exception as e:
        log.warning("deep_read_threshold_load_failed", error=str(e), action="using default")
    return _DEFAULT_THRESHOLD


def _extract_articles(messages: list[EmailMessage]) -> list[tuple[EmailMessage, ExtractedStory]]:
    """
    Extract the primary article from each long-form email.

    Returns a list of (message, story) pairs — message kept for subject and sender
    so the formatted digest can include the original link.

    A failure on one email is logged and skipped — pipeline continues with others.
    """
    results: list[tuple[EmailMessage, ExtractedStory]] = []
    for msg in messages:
        stories = extract_stories(
            body_text=msg.body_text,
            body_html=msg.body_html,
            newsletter_name=msg.sender,
            sender_email=msg.sender_email,
        )
        if not stories:
            log.warning(
                "deep_read_no_content_extracted",
                sender=msg.sender_email,
                subject=msg.subject,
            )
            continue
        # Use the first (primary) story — long-form newsletters typically have one article
        results.append((msg, stories[0]))
    return results


def _format_deep_read(
    articles: list[tuple[EmailMessage, ExtractedStory]],
    date_str: str,
) -> tuple[str, str]:
    """
    Format 3–5 articles into a depth-first plain-text digest.

    Each article gets full treatment: title, full body, and original source link.
    There is no synthesis — each piece is presented as-is to preserve its voice.

    Returns (subject, body).
    """
    first_title = articles[0][1].title if articles else "Deep Read"
    subject = f"Deep Read | {date_str}: {first_title}"

    sections: list[str] = [
        f"Deep Read — {date_str}",
        f"{len(articles)} articles for your reading queue.",
        "",
    ]

    for i, (msg, story) in enumerate(articles, 1):
        link = _extract_first_url(msg.body_html) or f"From: {msg.sender_email}"
        section = [
            f"{'=' * 60}",
            f"[{i} of {len(articles)}] {story.title}",
            f"Source: {msg.sender}",
            f"Link: {link}",
            f"{'=' * 60}",
            "",
            story.body,
            "",
        ]
        sections.extend(section)

    sections.append("---")
    sections.append(f"{len(articles)} articles | Reply to share feedback or adjust preferences.")

    return subject, "\n".join(sections)


def _extract_first_url(html_content: str | None) -> str | None:
    """
    Extract the first HTTP/HTTPS URL from email HTML.

    Long-form newsletters typically include a "Read online" or canonical link
    as the first anchor. We return it so the formatted digest includes a link
    to the original web version.

    Returns None if no URL is found — caller falls back to sender address.
    """
    if not html_content:
        return None
    # Match the first href with an http/https URL
    match = re.search(r'href=["\']?(https?://[^\s"\'<>]+)', html_content, re.IGNORECASE)
    return match.group(1) if match else None


def _persist_digest(
    run_id: str,
    articles: list[tuple[EmailMessage, ExtractedStory]],
    word_count: int,
) -> str:
    """Persist digest and stories to database. Returns digest_id."""
    try:
        digest_id = create_digest(digest_type="deep_read", run_id=run_id)

        for _msg, story in articles:
            cluster_id = get_or_create_cluster(story.title)
            insert_story(
                digest_id=digest_id,
                cluster_id=cluster_id,
                title=story.title,
                body=story.body,
                treatment="full",
                sources=[story.source_newsletter],
                topic=None,
                embedding=None,
            )

        mark_digest_sent(
            digest_id=digest_id,
            word_count=word_count,
            story_count=len(articles),
        )

    except Exception as e:
        log.error(
            "deep_read_persist_failed",
            run_id=run_id,
            error=str(e),
            action="digest was sent — persistence failure does not undo delivery",
        )
        return run_id

    return digest_id

"""
Daily brief pipeline orchestrator.

Coordinates the full sequence:
  1. Fetch today's newsletters from Gmail inbox
  2. Classify and filter (skip non-newsletters, route long-form to deep read queue)
  3. Extract stories from each newsletter (LLM, parallel-ish via sequential calls)
  4. Embed + cluster stories by cosine similarity
  5. Disambiguate ambiguous clusters (LangGraph)
  6. Synthesize clusters into canonical stories (LLM)
  7. Enrich single-source stories via Tavily search
  8. Rank stories by relevance
  9. Format into plain-text digest
 10. Send digest via Gmail API
 11. Archive source newsletters (label "Briefed", remove from inbox)
 12. Persist digest + stories to database

Called from main.py's _run_daily_brief() background task.
Raises on unrecoverable errors. Single-item failures are logged and skipped.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog

from gmail_service import GmailService
from pipeline.disambiguator import resolve_ambiguous_clusters
from pipeline.embedder import embed_and_cluster
from pipeline.enricher import enrich_stories
from pipeline.extractor import extract_stories
from pipeline.formatter import format_digest
from pipeline.ranker import rank_stories
from pipeline.synthesizer import synthesize_clusters
from source_classifier import classify, ClassificationResult
from tools.db import (
    create_digest,
    get_or_create_cluster,
    insert_story,
    mark_digest_sent,
)

log = structlog.get_logger(__name__)

# Source categories that go through the daily brief pipeline
_BRIEF_CATEGORY = "news_brief"


def run(run_id: str, dry_run: bool = False) -> dict:
    """
    Execute the full daily brief pipeline.

    Args:
        run_id: Unique identifier for this pipeline run (propagated to all logs).
        dry_run: If True, skips sending email and archiving. Useful for local testing.

    Returns a summary dict with pipeline stats. Raises on unrecoverable errors.
    """
    log.info("daily_brief_pipeline_start", run_id=run_id, dry_run=dry_run)

    gmail = GmailService()
    date_str = datetime.now().strftime("%A, %B %-d")

    # --- Step 1: Fetch inbox messages ---
    message_ids = gmail.list_inbox_messages(max_results=100)
    if not message_ids:
        log.info("daily_brief_no_messages", run_id=run_id)
        return {"run_id": run_id, "status": "no_messages", "story_count": 0}

    messages = gmail.get_messages(message_ids)
    log.info("daily_brief_fetched", run_id=run_id, message_count=len(messages))

    # --- Step 2: Classify messages ---
    brief_messages = []
    long_form_ids = []
    archive_ids = []  # non-newsletter emails to skip (but still archive later if needed)

    for msg in messages:
        result: ClassificationResult = classify(msg)
        if result.source_type == _BRIEF_CATEGORY:
            brief_messages.append(msg)
        elif result.source_type == "long_form":
            long_form_ids.append(msg.message_id)
            log.debug("daily_brief_long_form_queued", run_id=run_id, sender=msg.sender)
        # Skip personal, transactional, unknown — leave in inbox

    log.info(
        "daily_brief_classified",
        run_id=run_id,
        brief=len(brief_messages),
        long_form=len(long_form_ids),
    )

    if not brief_messages:
        log.info("daily_brief_no_brief_newsletters", run_id=run_id)
        return {"run_id": run_id, "status": "no_newsletters", "story_count": 0}

    # --- Step 3: Extract stories ---
    all_stories = []
    processed_message_ids = []

    for msg in brief_messages:
        stories = extract_stories(
            body_text=msg.body_text,
            body_html=msg.body_html,
            newsletter_name=msg.sender,
            sender_email=msg.sender_email,
        )
        if stories:
            all_stories.extend(stories)
            processed_message_ids.append(msg.message_id)
        else:
            log.debug("daily_brief_no_stories_extracted", run_id=run_id, sender=msg.sender)

    log.info("daily_brief_extracted", run_id=run_id, raw_story_count=len(all_stories))

    if not all_stories:
        log.info("daily_brief_no_stories", run_id=run_id)
        return {"run_id": run_id, "status": "no_stories", "story_count": 0}

    # --- Step 4: Embed + cluster ---
    clusters = embed_and_cluster(all_stories)
    log.info("daily_brief_clustered", run_id=run_id, cluster_count=len(clusters))

    # --- Step 5: Disambiguate ---
    clusters = resolve_ambiguous_clusters(clusters)

    # --- Step 6: Synthesize ---
    synthesized = synthesize_clusters(clusters)

    # --- Step 7: Enrich single-source stories ---
    synthesized = enrich_stories(synthesized)

    # --- Step 8: Rank ---
    ranked = rank_stories(synthesized)

    # --- Step 9: Format ---
    digest = format_digest(ranked, digest_type="daily", date_str=date_str)
    log.info(
        "daily_brief_formatted",
        run_id=run_id,
        story_count=digest.story_count,
        word_count=digest.word_count,
        full=digest.full_count,
        brief=digest.brief_count,
        one_liner=digest.one_liner_count,
    )

    if dry_run:
        log.info("daily_brief_dry_run_complete", run_id=run_id, subject=digest.subject)
        return {
            "run_id": run_id,
            "status": "dry_run",
            "story_count": digest.story_count,
            "word_count": digest.word_count,
            "subject": digest.subject,
        }

    # --- Step 10: Send email ---
    from config import settings
    sent_message_id = gmail.send_message(
        to=settings.gmail_send_as,
        subject=digest.subject,
        body=digest.body,
    )
    log.info("daily_brief_sent", run_id=run_id, gmail_message_id=sent_message_id)

    # --- Step 11: Archive source newsletters ---
    gmail.archive_messages(processed_message_ids)
    log.info("daily_brief_archived", run_id=run_id, count=len(processed_message_ids))

    # --- Step 12: Persist to database ---
    digest_id = _persist_digest(
        run_id=run_id,
        digest=digest,
        ranked=ranked,
        sent_message_id=sent_message_id,
    )

    log.info(
        "daily_brief_pipeline_complete",
        run_id=run_id,
        digest_id=digest_id,
        story_count=digest.story_count,
        word_count=digest.word_count,
    )

    return {
        "run_id": run_id,
        "status": "sent",
        "digest_id": digest_id,
        "story_count": digest.story_count,
        "word_count": digest.word_count,
    }


def _persist_digest(
    run_id: str,
    digest,
    ranked,
    sent_message_id: str,
) -> str:
    """Persist digest and stories to database. Returns digest_id."""
    try:
        digest_id = create_digest(digest_type="daily", run_id=run_id)

        for story in ranked:
            cluster_id = get_or_create_cluster(story.title)
            insert_story(
                digest_id=digest_id,
                cluster_id=cluster_id,
                title=story.title,
                body=story.body,
                treatment="full" if story.source_count >= 2 else "brief",
                sources=story.source_newsletters,
                topic=story.topic,
                embedding=story.cluster_embedding or None,
            )

        mark_digest_sent(
            digest_id=digest_id,
            word_count=digest.word_count,
            story_count=digest.story_count,
        )

    except Exception as e:
        log.error(
            "daily_brief_persist_failed",
            run_id=run_id,
            error=str(e),
        )
        # Digest was already sent — persistence failure doesn't undo delivery.
        return run_id  # fall back to run_id as a reference

    return digest_id

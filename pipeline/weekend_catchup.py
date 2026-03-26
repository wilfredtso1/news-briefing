"""
Weekend catch-up pipeline.

Runs Sunday morning. Collects stories from unacknowledged daily briefs sent
Mon–Fri of the current week, deduplicates cross-day repeats using the stored
embedding vectors in the DB (pgvector cosine similarity — no re-embedding),
reranks by importance (source count + topic weights), and delivers a single
catch-up digest sized for a 30-minute read (~4500 words).

Entry point: run_weekend_catchup(run_id) -> dict
"""

from __future__ import annotations

from datetime import datetime

import structlog

from gmail_service import GmailService
from pipeline.formatter import format_digest
from pipeline.ranker import rank_stories
from pipeline.synthesizer import SynthesizedStory
from tools.db import (
    create_digest,
    get_unacknowledged_stories,
    get_or_create_cluster,
    insert_story,
    mark_digest_sent,
)
from tools.retry import with_retry
from tools.tracing import traced

log = structlog.get_logger(__name__)

# Fetch Mon–Fri of the current week (5 days back is sufficient from Sunday)
_DAYS_BACK = 6


@traced("weekend_catchup")
def run_weekend_catchup(run_id: str, dry_run: bool = False) -> dict:
    """
    Execute the weekend catch-up pipeline.

    Queries unacknowledged daily brief stories from Mon–Fri, deduplicates
    cross-day repeats via cluster_id (already handled by get_unacknowledged_stories),
    reranks by importance, formats, and sends a digest.

    Args:
        run_id: Unique identifier for this pipeline run (propagated to all logs).
        dry_run: If True, skips sending email and archiving.

    Returns a dict with stories_included, word_count, digest_id.
    Raises on unrecoverable errors (DB failure, email delivery failure).
    """
    log.info("weekend_catchup_start", run_id=run_id, dry_run=dry_run)

    # --- Step 1: Fetch unacknowledged stories ---
    raw_stories = get_unacknowledged_stories(days_back=_DAYS_BACK)
    log.info("weekend_catchup_fetched", run_id=run_id, story_count=len(raw_stories))

    if not raw_stories:
        log.info("weekend_catchup_no_stories", run_id=run_id)
        return {"run_id": run_id, "status": "no_stories", "stories_included": 0}

    # --- Step 2: Convert DB rows to SynthesizedStory objects ---
    # Cross-day dedup is already applied by get_unacknowledged_stories (DISTINCT ON cluster_id).
    # We do NOT re-embed — embeddings are already stored and the DB query deduplicates.
    stories = [_db_row_to_synthesized_story(row) for row in raw_stories]
    stories = [s for s in stories if s is not None]

    if not stories:
        log.info("weekend_catchup_no_valid_stories", run_id=run_id)
        return {"run_id": run_id, "status": "no_valid_stories", "stories_included": 0}

    # --- Step 3: Rerank by importance (source count + topic weights), not recency ---
    ranked = rank_stories(stories)

    # --- Step 4: Format at 30-min time budget ---
    # format_digest reads the "weekend" word budget from agent_config internally.
    date_str = datetime.now().strftime("%A, %B %-d")
    digest = format_digest(ranked, digest_type="weekend", date_str=date_str)

    log.info(
        "weekend_catchup_formatted",
        run_id=run_id,
        story_count=digest.story_count,
        word_count=digest.word_count,
    )

    if dry_run:
        return {
            "run_id": run_id,
            "status": "dry_run",
            "stories_included": digest.story_count,
            "word_count": digest.word_count,
            "subject": digest.subject,
        }

    # --- Step 5: Send via Gmail ---
    from config import settings
    gmail = GmailService()
    sent_message_id, sent_thread_id = with_retry(gmail.send_message)(
        to=settings.gmail_send_as,
        subject=digest.subject,
        body=digest.body,
    )
    log.info("weekend_catchup_sent", run_id=run_id, gmail_message_id=sent_message_id, thread_id=sent_thread_id)

    # --- Step 6: Persist digest record ---
    digest_id = _persist_digest(run_id=run_id, digest=digest, ranked=ranked, sent_message_id=sent_message_id, thread_id=sent_thread_id)

    log.info(
        "weekend_catchup_complete",
        run_id=run_id,
        digest_id=digest_id,
        stories_included=digest.story_count,
        word_count=digest.word_count,
    )

    return {
        "run_id": run_id,
        "status": "sent",
        "digest_id": digest_id,
        "stories_included": digest.story_count,
        "word_count": digest.word_count,
    }


def _db_row_to_synthesized_story(row: dict) -> SynthesizedStory | None:
    """
    Convert a raw DB story row into a SynthesizedStory suitable for ranking/formatting.

    Returns None if the row is missing required fields (title, body).
    Single-item failures are skipped without crashing the pipeline.
    """
    title = (row.get("title") or "").strip()
    body = (row.get("body") or "").strip()
    if not title or not body:
        log.warning(
            "weekend_catchup_invalid_row",
            story_id=row.get("id"),
            reason="missing title or body",
        )
        return None

    sources: list[str] = row.get("sources") or []
    return SynthesizedStory(
        title=title,
        body=body,
        topic=row.get("topic") or "other",
        source_newsletters=sources,
        source_emails=[],
        key_facts=[],
        cluster_embedding=list(row["embedding"]) if row.get("embedding") is not None else [],
        source_count=len(sources) if sources else 1,
    )



def _persist_digest(run_id: str, digest, ranked: list[SynthesizedStory], sent_message_id: str, thread_id: str) -> str:
    """Persist digest and stories to database. Returns digest_id."""
    try:
        digest_id = create_digest(digest_type="weekend_catchup", run_id=run_id)

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
            sent_message_id=sent_message_id,
            thread_id=thread_id,
        )

    except Exception as e:
        log.error(
            "weekend_catchup_persist_failed",
            run_id=run_id,
            error=str(e),
            action="digest was sent — persistence failure does not undo delivery",
        )
        return run_id  # fall back to run_id as a reference

    return digest_id

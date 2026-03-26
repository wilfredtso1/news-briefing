"""
Database helpers for all tables.
All SQL lives here — no inline queries in pipeline code.

Connection uses psycopg3 with the Supabase PostgreSQL URL from config.
For production on Railway, switch to the pooler URL (port 6543) to avoid
exhausting Supabase's direct connection limit.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator

import psycopg
import structlog
from pgvector.psycopg import register_vector

from config import settings

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    """Yield a psycopg3 connection with pgvector registered. Auto-commits on clean exit."""
    with psycopg.connect(settings.database_url, autocommit=False) as conn:
        register_vector(conn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# newsletter_sources
# ---------------------------------------------------------------------------

def upsert_newsletter_source(
    sender_email: str,
    name: str,
    source_type: str,
    unsubscribe_header: str | None = None,
) -> dict:
    """
    Insert a new newsletter source or update last_seen_at if already known.
    Returns the full row.

    source_type must be 'news_brief', 'long_form', or 'unknown'.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO newsletter_sources (name, sender_email, type, unsubscribe_header)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (sender_email) DO UPDATE
                SET last_seen_at = NOW(),
                    name = EXCLUDED.name,
                    unsubscribe_header = COALESCE(EXCLUDED.unsubscribe_header, newsletter_sources.unsubscribe_header)
            RETURNING *
            """,
            (name, sender_email, source_type, unsubscribe_header),
        )
        row = cur.fetchone()
        if not row:
            return {}
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def get_active_sources() -> list[dict]:
    """Return all sources with status='active' or 'deprioritized'."""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM newsletter_sources WHERE status IN ('active', 'deprioritized') ORDER BY trust_weight DESC"
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


def get_source_by_email(sender_email: str) -> dict | None:
    """Return a single newsletter source by sender email, or None if not found."""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM newsletter_sources WHERE sender_email = %s",
            (sender_email,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def mark_source_unsubscribed(sender_email: str) -> None:
    """Mark a source as unsubscribed after the agent executes List-Unsubscribe."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE newsletter_sources SET status = 'unsubscribed', unsubscribed_at = NOW() WHERE sender_email = %s",
            (sender_email,),
        )
    log.info("source_unsubscribed", sender_email=sender_email)


def deprioritize_source(sender_email: str) -> None:
    """Lower a source's priority without unsubscribing."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE newsletter_sources SET status = 'deprioritized' WHERE sender_email = %s",
            (sender_email,),
        )
    log.info("source_deprioritized", sender_email=sender_email)


def update_source_trust_weight(sender_email: str, trust_weight: float) -> None:
    """Update a source's trust weight. Used by the onboarding agent to boost important sources."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE newsletter_sources SET trust_weight = %s WHERE sender_email = %s",
            (trust_weight, sender_email),
        )
    log.info("source_trust_weight_updated", sender_email=sender_email, trust_weight=trust_weight)


def update_source_type(sender_email: str, source_type: str) -> None:
    """Update a source's type classification. Called by supervisor and onboarding."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE newsletter_sources SET type = %s WHERE sender_email = %s",
            (source_type, sender_email),
        )
    log.info("source_type_updated", sender_email=sender_email, source_type=source_type)


# ---------------------------------------------------------------------------
# digests
# ---------------------------------------------------------------------------

def create_digest(digest_type: str, run_id: str) -> str:
    """Insert a new digest record. Returns the new digest UUID."""
    digest_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO digests (id, type, run_id) VALUES (%s, %s, %s)",
            (digest_id, digest_type, run_id),
        )
    log.info("digest_created", digest_id=digest_id, type=digest_type, run_id=run_id)
    return digest_id


def mark_digest_sent(
    digest_id: str,
    word_count: int,
    story_count: int,
    sent_message_id: str | None = None,
    thread_id: str | None = None,
) -> None:
    """
    Record delivery timestamp, word/story counts, and Gmail identifiers.
    thread_id and sent_message_id are required by _run_poll_replies to detect
    user replies; they are optional here so weekend_catchup and deep_read can
    call this function the same way as daily_brief.
    """
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE digests
            SET sent_at = NOW(),
                word_count = %s,
                story_count = %s,
                sent_message_id = %s,
                thread_id = %s
            WHERE id = %s
            """,
            (word_count, story_count, sent_message_id, thread_id, digest_id),
        )
    log.info(
        "digest_sent",
        digest_id=digest_id,
        word_count=word_count,
        story_count=story_count,
        thread_id=thread_id,
    )


def mark_digest_acknowledged(digest_id: str) -> None:
    """Record acknowledgment timestamp when user replies to confirm they've read it."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE digests SET acknowledged_at = NOW() WHERE id = %s",
            (digest_id,),
        )
    log.info("digest_acknowledged", digest_id=digest_id)


def get_unacknowledged_digests(digest_type: str = "daily_brief", days_back: int = 7) -> list[dict]:
    """
    Return sent but unacknowledged digests within the lookback window.
    Used by the weekend catch-up pipeline to find missed content.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT * FROM digests
            WHERE type = %s
              AND sent_at IS NOT NULL
              AND acknowledged_at IS NULL
              AND sent_at >= NOW() - INTERVAL '%s days'
            ORDER BY sent_at ASC
            LIMIT 50
            """,
            (digest_type, days_back),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


# ---------------------------------------------------------------------------
# story_clusters
# ---------------------------------------------------------------------------

def get_or_create_cluster(canonical_title: str) -> str:
    """
    Return existing cluster ID if the title matches, otherwise create new.
    Title matching is exact here — fuzzy matching is handled by the embedder
    before this function is called.
    """
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM story_clusters WHERE canonical_title = %s",
            (canonical_title,),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE story_clusters SET last_seen_at = NOW() WHERE id = %s",
                (existing[0],),
            )
            return str(existing[0])

        cluster_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO story_clusters (id, canonical_title) VALUES (%s, %s)",
            (cluster_id, canonical_title),
        )
        return cluster_id


def mark_clusters_read(digest_id: str) -> None:
    """
    Mark all story_clusters referenced by this digest's stories as read.

    Sets read_at = NOW() on each cluster so any future get_unacknowledged_stories
    call excludes them — even across different digests that contain the same cluster.

    Idempotent: already-read clusters are not re-stamped (AND read_at IS NULL guard).
    Called automatically from mark_digest_acknowledged.
    """
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE story_clusters
            SET read_at = NOW()
            WHERE id IN (
                SELECT cluster_id FROM stories
                WHERE digest_id = %s AND cluster_id IS NOT NULL
            )
            AND read_at IS NULL
            """,
            (digest_id,),
        )
    log.info("clusters_marked_read", digest_id=digest_id)


# ---------------------------------------------------------------------------
# stories
# ---------------------------------------------------------------------------

def insert_story(
    digest_id: str,
    cluster_id: str,
    title: str,
    body: str,
    treatment: str,
    sources: list[str],
    topic: str | None,
    embedding: list[float] | None,
) -> str:
    """Insert a synthesized story. Returns the new story UUID."""
    story_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stories (id, digest_id, cluster_id, title, body, treatment, sources, topic, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (story_id, digest_id, cluster_id, title, body, treatment, sources, topic, embedding),
        )
    return story_id


def get_recent_story_embeddings(days_back: int = 2) -> list[dict]:
    """
    Return story embeddings from the last N days for cross-day deduplication.
    Used by the embedder to avoid re-synthesizing stories already covered.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT s.id, s.title, s.embedding, s.cluster_id
            FROM stories s
            JOIN digests d ON s.digest_id = d.id
            WHERE d.sent_at >= NOW() - INTERVAL '%s days'
              AND s.embedding IS NOT NULL
            ORDER BY d.sent_at DESC
            LIMIT 200
            """,
            (days_back,),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


def get_stories_for_digest(digest_id: str) -> list[dict]:
    """Return all stories for a given digest, ordered by treatment then topic."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT * FROM stories
            WHERE digest_id = %s
            ORDER BY
                CASE treatment WHEN 'full' THEN 1 WHEN 'brief' THEN 2 ELSE 3 END,
                topic NULLS LAST
            """,
            (digest_id,),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


def get_unacknowledged_stories(days_back: int = 7) -> list[dict]:
    """
    Return stories from unacknowledged daily briefs within the lookback window.
    Used by the weekend catch-up pipeline.
    Deduplicates by cluster_id — same story appearing on multiple days appears once.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT DISTINCT ON (COALESCE(s.cluster_id::text, s.id::text))
                s.*, d.sent_at as digest_sent_at
            FROM stories s
            JOIN digests d ON s.digest_id = d.id
            WHERE d.type = 'daily_brief'
              AND d.sent_at IS NOT NULL
              AND d.acknowledged_at IS NULL
              AND d.sent_at >= NOW() - INTERVAL '%s days'
            ORDER BY COALESCE(s.cluster_id::text, s.id::text), d.sent_at DESC
            LIMIT 100
            """,
            (days_back,),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


# ---------------------------------------------------------------------------
# feedback_events
# ---------------------------------------------------------------------------

def insert_feedback_event(
    digest_id: str,
    raw_reply: str,
    supervisor_interpretation: str | None = None,
    proposed_change: str | None = None,
) -> str:
    """Log a user reply that contained feedback. Returns the new event UUID."""
    event_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO feedback_events (id, digest_id, raw_reply, supervisor_interpretation, proposed_change)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (event_id, digest_id, raw_reply, supervisor_interpretation, proposed_change),
        )
    log.info("feedback_logged", event_id=event_id, digest_id=digest_id)
    return event_id


def mark_feedback_applied(event_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE feedback_events SET applied = TRUE, applied_at = NOW() WHERE id = %s",
            (event_id,),
        )


def get_weekly_digest_stats(days_back: int = 7) -> list[dict]:
    """
    Return all sent digests from the last N days with acknowledgment status.
    Used by the weekly supervisor to analyze engagement patterns.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, type, sent_at, acknowledged_at, word_count, story_count
            FROM digests
            WHERE sent_at >= NOW() - INTERVAL '%s days'
            ORDER BY sent_at ASC
            LIMIT 50
            """,
            (days_back,),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


def get_recent_feedback(days_back: int = 7) -> list[dict]:
    """Return feedback events from the last N days for the weekly supervisor sweep."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT * FROM feedback_events
            WHERE created_at >= NOW() - INTERVAL '%s days'
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (days_back,),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]


# ---------------------------------------------------------------------------
# agent_config
# ---------------------------------------------------------------------------

def get_config(key: str) -> Any:
    """
    Return the current value for a config key, or None if not set.
    Supervisor overrides in the DB take precedence; code defaults are fallbacks.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM agent_config WHERE key = %s",
            (key,),
        ).fetchone()
    return row[0] if row else None


def set_config(key: str, value: Any, updated_by: str = "supervisor") -> None:
    """
    Upsert a config value. Stores previous value for rollback.
    updated_by should be 'supervisor' or 'user'.
    """
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_config (key, value, updated_by, previous_value)
            VALUES (%s, %s::jsonb, %s, NULL)
            ON CONFLICT (key) DO UPDATE
                SET previous_value = agent_config.value,
                    value = EXCLUDED.value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
            """,
            (key, psycopg.types.json.Jsonb(value), updated_by),
        )
    log.info("config_updated", key=key, updated_by=updated_by)


def rollback_config(key: str) -> bool:
    """
    Restore previous_value as the current value.
    Returns True if rollback succeeded, False if no previous value exists.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT previous_value FROM agent_config WHERE key = %s",
            (key,),
        ).fetchone()

        if not row or row[0] is None:
            log.warning("config_rollback_no_previous", key=key)
            return False

        conn.execute(
            """
            UPDATE agent_config
            SET value = previous_value, previous_value = NULL, updated_at = NOW(), updated_by = 'rollback'
            WHERE key = %s
            """,
            (key,),
        )
    log.info("config_rolled_back", key=key)
    return True


# ---------------------------------------------------------------------------
# onboarding_events
# ---------------------------------------------------------------------------


def create_onboarding_event() -> str:
    """
    Insert a new onboarding event row. Returns the new event UUID.
    thread_id and sent_message_id are NULL until the setup email is sent —
    call update_onboarding_thread() immediately after send_message() returns.
    """
    event_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO onboarding_events (id) VALUES (%s)",
            (event_id,),
        )
    log.info("onboarding_event_created", event_id=event_id)
    return event_id


def update_onboarding_thread(event_id: str, thread_id: str, sent_message_id: str) -> None:
    """Store the Gmail thread and message IDs after the setup email is sent."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE onboarding_events SET thread_id = %s, sent_message_id = %s WHERE id = %s",
            (thread_id, sent_message_id, event_id),
        )
    log.info("onboarding_thread_stored", event_id=event_id, thread_id=thread_id)


def get_pending_onboarding_event() -> dict | None:
    """
    Return the most recent unapplied onboarding event, or None if not found.
    A pending event means the setup email was sent but no reply has been processed yet.
    Also returns events with no thread_id yet (created but email not yet sent).
    """
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM onboarding_events WHERE applied = FALSE ORDER BY created_at DESC LIMIT 1",
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def mark_onboarding_applied(event_id: str, raw_reply: str, parsed_preferences: dict) -> None:
    """Record the user's reply and parsed preferences, and mark the event applied."""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE onboarding_events
            SET applied = TRUE,
                applied_at = NOW(),
                raw_reply = %s,
                parsed_preferences = %s::jsonb
            WHERE id = %s
            """,
            (raw_reply, psycopg.types.json.Jsonb(parsed_preferences), event_id),
        )
    log.info("onboarding_applied", event_id=event_id)

-- News Briefing Agent — Database Schema
-- Run once against Supabase to initialise all tables.
-- pgvector extension must be enabled before running (Database → Extensions → vector).

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;


-- ---------------------------------------------------------------------------
-- newsletter_sources
-- Discovered automatically from inbox. No predefined list required.
-- ---------------------------------------------------------------------------

CREATE TABLE newsletter_sources (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT        NOT NULL,
    sender_email        TEXT        NOT NULL UNIQUE,
    -- 'news_brief' routes to Daily Brief; 'long_form' routes to Deep Read queue
    type                TEXT        NOT NULL DEFAULT 'news_brief'
                            CHECK (type IN ('news_brief', 'long_form', 'unknown')),
    status              TEXT        NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'deprioritized', 'unsubscribed', 'ignored')),
    -- Supervisor-adjustable quality/relevance signal (1.0 = neutral)
    trust_weight        FLOAT       NOT NULL DEFAULT 1.0,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Raw List-Unsubscribe header value — used for automated unsubscribe
    unsubscribe_header  TEXT,
    unsubscribed_at     TIMESTAMPTZ
);


-- ---------------------------------------------------------------------------
-- digests
-- One row per sent digest (daily brief, deep read, weekend catch-up).
-- ---------------------------------------------------------------------------

CREATE TABLE digests (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    type            TEXT        NOT NULL
                        CHECK (type IN ('daily_brief', 'deep_read', 'weekend_catchup')),
    -- run_id propagates through all logs and LangSmith traces for this pipeline run
    run_id          TEXT        NOT NULL,
    sent_at         TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    word_count      INTEGER,
    story_count     INTEGER,
    -- Gmail thread/message IDs stored at send time; used by _run_poll_replies
    -- to detect user replies. NULL for digests created before migration 001.
    thread_id       TEXT,
    sent_message_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- story_clusters
-- Canonical story identities across days.
-- Same real-world story appearing Mon + Tue shares a cluster_id.
-- ---------------------------------------------------------------------------

CREATE TABLE story_clusters (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_title TEXT        NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Set when the user acknowledges any digest containing this cluster.
    -- Prevents the story from re-appearing in future catch-up digests
    -- even if it was included in a different, unacknowledged digest.
    read_at         TIMESTAMPTZ
);


-- ---------------------------------------------------------------------------
-- stories
-- Individual synthesized stories within a digest.
-- ---------------------------------------------------------------------------

CREATE TABLE stories (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    digest_id   UUID        NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
    cluster_id  UUID        REFERENCES story_clusters(id),
    title       TEXT        NOT NULL,
    body        TEXT        NOT NULL,
    -- treatment determines how the story is rendered in the digest
    treatment   TEXT        NOT NULL
                    CHECK (treatment IN ('full', 'brief', 'one_liner')),
    -- newsletters that covered this story
    sources     TEXT[]      NOT NULL DEFAULT '{}',
    topic       TEXT,
    -- voyage-3 produces 1024-dimensional embeddings
    embedding   vector(1024),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- feedback_events
-- One row per user reply that contains feedback (not pure acknowledgments).
-- ---------------------------------------------------------------------------

CREATE TABLE feedback_events (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    digest_id                   UUID        NOT NULL REFERENCES digests(id),
    raw_reply                   TEXT        NOT NULL,
    supervisor_interpretation   TEXT,
    proposed_change             TEXT,
    applied                     BOOLEAN     NOT NULL DEFAULT FALSE,
    applied_at                  TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- agent_config
-- Runtime configuration managed by the supervisor agent.
-- Baseline values live in code (config.py); supervisor overrides stored here.
-- ---------------------------------------------------------------------------

CREATE TABLE agent_config (
    key             TEXT        PRIMARY KEY,
    value           JSONB       NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- 'supervisor' or 'user' (for manually applied changes)
    updated_by      TEXT        NOT NULL DEFAULT 'system',
    -- Kept for rollback — one level of history is sufficient
    previous_value  JSONB
);


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- Stories: frequent lookups by digest and cluster
CREATE INDEX idx_stories_digest_id     ON stories(digest_id);
CREATE INDEX idx_stories_cluster_id    ON stories(cluster_id);
CREATE INDEX idx_stories_created_at    ON stories(created_at DESC);

-- Vector similarity search for story clustering (HNSW — no training data required)
CREATE INDEX idx_stories_embedding
    ON stories USING hnsw (embedding vector_cosine_ops);

-- Digests: filter by type and date range
CREATE INDEX idx_digests_type          ON digests(type);
CREATE INDEX idx_digests_sent_at       ON digests(sent_at DESC);

-- Unacknowledged digests (weekend catch-up query)
CREATE INDEX idx_digests_unacked
    ON digests(sent_at DESC)
    WHERE acknowledged_at IS NULL;

-- Reply polling: look up digest by thread_id
CREATE INDEX idx_digests_thread_id
    ON digests(thread_id)
    WHERE thread_id IS NOT NULL;

-- Unread story clusters (weekend catch-up dedup query)
CREATE INDEX idx_story_clusters_unread
    ON story_clusters(id)
    WHERE read_at IS NULL;

-- Feedback: link back to digest
CREATE INDEX idx_feedback_digest_id    ON feedback_events(digest_id);

-- Sources: lookup by sender, filter by status
CREATE INDEX idx_sources_sender_email  ON newsletter_sources(sender_email);
CREATE INDEX idx_sources_status        ON newsletter_sources(status);


-- ---------------------------------------------------------------------------
-- Seed agent_config with baseline values
-- Supervisor can override these at runtime without a code deploy.
-- ---------------------------------------------------------------------------

INSERT INTO agent_config (key, value, updated_by) VALUES
    ('topic_weights', '{
        "ai": 1.5,
        "health_tech": 1.5,
        "venture_capital": 1.3,
        "financial_markets": 1.3,
        "tech": 1.2,
        "crypto": 0.5,
        "sports": 0.3,
        "entertainment": 0.3
    }', 'system'),
    ('word_budget', '{
        "daily_brief_total": 3000,
        "full_treatment_words": 180,
        "brief_treatment_words": 60,
        "top_full_count": 5,
        "top_brief_count": 10
    }', 'system'),
    ('cosine_similarity_threshold', '0.82', 'system'),
    ('deep_read_threshold', '5', 'system');

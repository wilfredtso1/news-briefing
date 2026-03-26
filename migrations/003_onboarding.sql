-- Migration 003: onboarding_events table + onboarding_complete agent_config key
--
-- Context: Phase 6 onboarding flow. The onboarding agent scans the inbox,
-- sends a setup email, and processes the user's reply to set initial source
-- priorities and topic preferences before the first daily brief runs.
--
-- Why separate from feedback_events: feedback_events.digest_id is NOT NULL.
-- Onboarding replies have no associated digest. See DECISIONS.md 2026-03-26.
--
-- Rollback:
--   DROP TABLE IF EXISTS onboarding_events;
--   DELETE FROM agent_config WHERE key = 'onboarding_complete';

CREATE TABLE IF NOT EXISTS onboarding_events (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Populated after setup email is sent; NULL until then
    thread_id           TEXT,
    sent_message_id     TEXT,
    -- Populated after user reply is processed
    raw_reply           TEXT,
    parsed_preferences  JSONB,
    applied             BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at          TIMESTAMPTZ
);

-- Lookup for reply polling: find the pending event by thread_id
CREATE INDEX IF NOT EXISTS idx_onboarding_events_applied
    ON onboarding_events(applied)
    WHERE applied = FALSE;

INSERT INTO agent_config (key, value, updated_by)
VALUES ('onboarding_complete', 'false', 'system')
ON CONFLICT (key) DO NOTHING;

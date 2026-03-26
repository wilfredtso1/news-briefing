-- Migration 001: add thread_id and sent_message_id to digests
--
-- Required by _run_poll_replies (main.py) to poll Gmail for replies on
-- each digest thread. Rows created before this migration have NULL values,
-- which _run_poll_replies skips gracefully.
--
-- Rollback:
--   ALTER TABLE digests DROP COLUMN thread_id;
--   ALTER TABLE digests DROP COLUMN sent_message_id;

ALTER TABLE digests
    ADD COLUMN thread_id        TEXT,
    ADD COLUMN sent_message_id  TEXT;

-- Index for efficient lookup when polling replies across recent digests
CREATE INDEX idx_digests_thread_id ON digests(thread_id) WHERE thread_id IS NOT NULL;

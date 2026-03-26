-- Migration 002: Add read_at to story_clusters for cluster-level read tracking
--
-- Context: When a user acknowledges any digest, all story clusters in that digest
-- are marked read. This prevents the same story from re-appearing in future
-- catch-up digests even if it appeared in a different unacknowledged digest.
--
-- Rollback:
--   ALTER TABLE story_clusters DROP COLUMN read_at;
--   DROP INDEX IF EXISTS idx_story_clusters_unread;

ALTER TABLE story_clusters
    ADD COLUMN read_at TIMESTAMPTZ;

CREATE INDEX idx_story_clusters_unread
    ON story_clusters(id)
    WHERE read_at IS NULL;

-- Migration 004: synthesis_style_notes and web_search_topics agent_config keys
-- Rollback: DELETE FROM agent_config WHERE key IN ('synthesis_style_notes', 'web_search_topics');

INSERT INTO agent_config (key, value, updated_by)
VALUES
    ('synthesis_style_notes', '[]', 'system'),
    ('web_search_topics', '[]', 'system')
ON CONFLICT (key) DO NOTHING;

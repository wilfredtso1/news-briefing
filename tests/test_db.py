"""
Tests for tools/db.py.

These are integration tests — they test the SQL logic against a real database.
To avoid polluting the production Supabase instance, these tests are skipped
unless the TEST_DATABASE_URL environment variable is set.

Run with a test DB:
    TEST_DATABASE_URL=postgresql://... pytest tests/test_db.py -v

For CI, set up a separate Supabase project or a local Postgres instance with
pgvector installed and run the schema.sql against it.
"""

import os
import uuid

import pytest

# Skip all tests in this file unless TEST_DATABASE_URL is set
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — skipping DB integration tests",
)


@pytest.fixture(autouse=True)
def patch_db_url(monkeypatch):
    """Use test database for all DB tests."""
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    # Re-import settings with the patched URL
    import importlib
    import config
    importlib.reload(config)
    import tools.db
    importlib.reload(tools.db)


# ---------------------------------------------------------------------------
# newsletter_sources
# ---------------------------------------------------------------------------

class TestNewsletterSources:
    def test_upsert_creates_new_source(self):
        from tools.db import upsert_newsletter_source, get_active_sources

        email = f"test-{uuid.uuid4()}@example.com"
        upsert_newsletter_source(
            sender_email=email,
            name="Test Newsletter",
            source_type="news_brief",
            unsubscribe_header="<https://example.com/unsub>",
        )
        sources = get_active_sources()
        found = [s for s in sources if s["sender_email"] == email]
        assert len(found) == 1
        assert found[0]["type"] == "news_brief"
        assert found[0]["unsubscribe_header"] == "<https://example.com/unsub>"

    def test_upsert_updates_existing_source_name(self):
        from tools.db import upsert_newsletter_source

        email = f"test-{uuid.uuid4()}@example.com"
        upsert_newsletter_source(email, "Old Name", "news_brief")
        upsert_newsletter_source(email, "New Name", "news_brief")

        from tools.db import get_active_sources
        sources = get_active_sources()
        found = next(s for s in sources if s["sender_email"] == email)
        assert found["name"] == "New Name"

    def test_deprioritize_source(self):
        from tools.db import upsert_newsletter_source, deprioritize_source, get_active_sources

        email = f"test-{uuid.uuid4()}@example.com"
        upsert_newsletter_source(email, "Test", "news_brief")
        deprioritize_source(email)

        sources = get_active_sources()
        found = next((s for s in sources if s["sender_email"] == email), None)
        assert found is not None  # deprioritized still returned
        assert found["status"] == "deprioritized"


# ---------------------------------------------------------------------------
# digests
# ---------------------------------------------------------------------------

class TestDigests:
    def test_create_and_mark_sent(self):
        from tools.db import create_digest, mark_digest_sent

        run_id = str(uuid.uuid4())
        digest_id = create_digest("daily_brief", run_id)
        assert digest_id is not None

        mark_digest_sent(digest_id, word_count=2500, story_count=12)

        from tools.db import get_unacknowledged_digests
        unacked = get_unacknowledged_digests()
        found = next((d for d in unacked if d["id"] == digest_id), None)
        assert found is not None
        assert found["word_count"] == 2500

    def test_mark_acknowledged_excludes_from_unacked(self):
        from tools.db import create_digest, mark_digest_sent, mark_digest_acknowledged, get_unacknowledged_digests

        run_id = str(uuid.uuid4())
        digest_id = create_digest("daily_brief", run_id)
        mark_digest_sent(digest_id, 1000, 5)
        mark_digest_acknowledged(digest_id)

        unacked = get_unacknowledged_digests()
        found = next((d for d in unacked if d["id"] == digest_id), None)
        assert found is None  # acknowledged — should not appear


# ---------------------------------------------------------------------------
# agent_config
# ---------------------------------------------------------------------------

class TestAgentConfig:
    def test_get_seeded_config(self):
        from tools.db import get_config

        # This key is seeded in schema.sql
        value = get_config("cosine_similarity_threshold")
        assert value is not None

    def test_set_and_get_config(self):
        from tools.db import set_config, get_config

        key = f"test_key_{uuid.uuid4().hex[:8]}"
        set_config(key, {"test": True}, updated_by="test")
        value = get_config(key)
        assert value == {"test": True}

    def test_rollback_config(self):
        from tools.db import set_config, get_config, rollback_config

        key = f"test_rollback_{uuid.uuid4().hex[:8]}"
        set_config(key, "original", updated_by="test")
        set_config(key, "updated", updated_by="test")

        assert get_config(key) == "updated"
        rollback_config(key)
        assert get_config(key) == "original"

    def test_rollback_with_no_previous_returns_false(self):
        from tools.db import set_config, rollback_config

        key = f"test_no_prev_{uuid.uuid4().hex[:8]}"
        set_config(key, "first_value", updated_by="test")

        result = rollback_config(key)
        assert result is False

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

    def test_mark_acknowledged_marks_clusters_read(self):
        """Acknowledging a digest marks its story_clusters as read."""
        from tools.db import (
            create_digest, mark_digest_sent, mark_digest_acknowledged,
            get_or_create_cluster, insert_story, mark_clusters_read,
        )
        import tools.db as db_module

        run_id = str(uuid.uuid4())
        digest_id = create_digest("daily_brief", run_id)
        mark_digest_sent(digest_id, 500, 1)
        cluster_id = get_or_create_cluster(f"Test Story {uuid.uuid4().hex[:8]}")
        insert_story(
            digest_id=digest_id,
            cluster_id=cluster_id,
            title="Test Story",
            body="body text",
            treatment="brief",
            sources=["test@example.com"],
            topic="tech",
            embedding=None,
        )

        mark_digest_acknowledged(digest_id)

        # Verify the cluster is now marked read
        with db_module.get_conn() as conn:
            row = conn.execute(
                "SELECT read_at FROM story_clusters WHERE id = %s",
                (cluster_id,),
            ).fetchone()
        assert row is not None
        assert row[0] is not None, "cluster.read_at should be set after acknowledgment"


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


# ---------------------------------------------------------------------------
# story_clusters — cluster-level read tracking
# ---------------------------------------------------------------------------


class TestStoryClusterReadTracking:
    """
    Cluster-level read tracking: acknowledging one digest marks its clusters
    as read so the same stories don't appear in future catch-up digests,
    even if those stories appeared in a different unacknowledged digest.
    """

    def _make_digest_with_story(self, cluster_id: str, digest_type: str = "daily_brief"):
        """Helper: create a sent digest containing one story that shares cluster_id."""
        from tools.db import create_digest, mark_digest_sent, insert_story

        digest_id = create_digest(digest_type, str(uuid.uuid4()))
        mark_digest_sent(digest_id, 500, 1)
        insert_story(
            digest_id=digest_id,
            cluster_id=cluster_id,
            title="Shared Story",
            body="body text",
            treatment="brief",
            sources=["test@example.com"],
            topic="tech",
            embedding=None,
        )
        return digest_id

    def test_mark_clusters_read_sets_read_at(self):
        """mark_clusters_read stamps read_at on each cluster referenced by the digest."""
        import tools.db as db_module
        from tools.db import get_or_create_cluster, mark_clusters_read

        cluster_id = get_or_create_cluster(f"Cluster {uuid.uuid4().hex[:8]}")
        digest_id = self._make_digest_with_story(cluster_id)

        mark_clusters_read(digest_id)

        with db_module.get_conn() as conn:
            row = conn.execute(
                "SELECT read_at FROM story_clusters WHERE id = %s",
                (cluster_id,),
            ).fetchone()
        assert row[0] is not None, "read_at should be set"

    def test_mark_clusters_read_is_idempotent(self):
        """Calling mark_clusters_read twice does not overwrite the original timestamp."""
        import tools.db as db_module
        from tools.db import get_or_create_cluster, mark_clusters_read

        cluster_id = get_or_create_cluster(f"Idempotent {uuid.uuid4().hex[:8]}")
        digest_id = self._make_digest_with_story(cluster_id)

        mark_clusters_read(digest_id)
        with db_module.get_conn() as conn:
            first_read_at = conn.execute(
                "SELECT read_at FROM story_clusters WHERE id = %s", (cluster_id,)
            ).fetchone()[0]

        mark_clusters_read(digest_id)
        with db_module.get_conn() as conn:
            second_read_at = conn.execute(
                "SELECT read_at FROM story_clusters WHERE id = %s", (cluster_id,)
            ).fetchone()[0]

        assert first_read_at == second_read_at, "read_at should not be overwritten on second call"

    def test_get_unacknowledged_stories_excludes_read_clusters(self):
        """
        Core scenario: story appears in digest A and digest B.
        User acknowledges digest A → cluster marked read.
        get_unacknowledged_stories should NOT include the story from unacknowledged digest B.
        """
        from tools.db import (
            get_or_create_cluster, mark_digest_acknowledged,
            get_unacknowledged_stories,
        )

        cluster_id = get_or_create_cluster(f"Cross-digest Story {uuid.uuid4().hex[:8]}")

        # Digest A and B both contain the same story cluster
        digest_a = self._make_digest_with_story(cluster_id)
        digest_b = self._make_digest_with_story(cluster_id)

        # Only acknowledge digest A
        mark_digest_acknowledged(digest_a)

        # Digest B is unacknowledged — but its cluster is now read via digest A
        stories = get_unacknowledged_stories(days_back=7)
        cluster_ids_in_result = {str(s.get("cluster_id")) for s in stories}

        assert cluster_id not in cluster_ids_in_result, (
            "Story whose cluster was read via digest A should not appear "
            "in unacknowledged stories even though digest B is unacknowledged"
        )

    def test_get_unacknowledged_stories_includes_unread_clusters(self):
        """Stories in unread clusters continue to appear in the catch-up query."""
        from tools.db import get_or_create_cluster, get_unacknowledged_stories

        cluster_id = get_or_create_cluster(f"Unread Story {uuid.uuid4().hex[:8]}")
        self._make_digest_with_story(cluster_id)

        # No acknowledgment — cluster is unread
        stories = get_unacknowledged_stories(days_back=7)
        cluster_ids_in_result = {str(s.get("cluster_id")) for s in stories}

        assert cluster_id in cluster_ids_in_result, (
            "Story in an unread cluster should appear in unacknowledged stories"
        )

    def test_stories_without_cluster_id_always_included(self):
        """
        Stories with NULL cluster_id (no cluster assigned) are always included
        regardless of any other clusters being marked read.
        """
        from tools.db import create_digest, mark_digest_sent, insert_story, get_unacknowledged_stories

        digest_id = create_digest("daily_brief", str(uuid.uuid4()))
        mark_digest_sent(digest_id, 300, 1)
        # Story with no cluster
        insert_story(
            digest_id=digest_id,
            cluster_id=None,
            title=f"No-cluster Story {uuid.uuid4().hex[:8]}",
            body="body text",
            treatment="brief",
            sources=["test@example.com"],
            topic="other",
            embedding=None,
        )

        stories = get_unacknowledged_stories(days_back=7)
        null_cluster_stories = [s for s in stories if s.get("cluster_id") is None]
        assert len(null_cluster_stories) > 0, (
            "Stories with NULL cluster_id should always appear in unacknowledged stories"
        )

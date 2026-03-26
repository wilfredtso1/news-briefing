"""
Tests for pipeline/weekend_catchup.py

Unit tests: all DB and gmail_service calls are mocked.
E2E tests: marked @pytest.mark.e2e — skipped if DATABASE_URL not set.

Coverage target: >90% of orchestration logic.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from pipeline.synthesizer import SynthesizedStory
from pipeline.weekend_catchup import (
    _db_row_to_synthesized_story,
    run_weekend_catchup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_row(
    story_id: str = "story-uuid-1",
    title: str = "AI Breakthrough Promises Better Chips",
    body: str = "Researchers unveiled a new chip design this week.",
    topic: str = "ai",
    sources: list[str] | None = None,
    embedding: list[float] | None = None,
    cluster_id: str = "cluster-uuid-1",
) -> dict:
    return {
        "id": story_id,
        "digest_id": "digest-uuid-1",
        "cluster_id": cluster_id,
        "title": title,
        "body": body,
        "treatment": "full",
        "sources": sources or ["Morning Brew", "Axios AM"],
        "topic": topic,
        "embedding": embedding or ([0.1] * 1024),
        "digest_sent_at": "2026-03-24T08:00:00Z",
    }


def _make_synthesized_story(
    title: str = "AI Breakthrough Promises Better Chips",
    topic: str = "ai",
    source_count: int = 2,
) -> SynthesizedStory:
    return SynthesizedStory(
        title=title,
        body="Researchers unveiled a new chip design this week.",
        topic=topic,
        source_newsletters=["Morning Brew", "Axios AM"][:source_count],
        source_emails=["email@example.com"] * source_count,
        source_count=source_count,
    )


# ---------------------------------------------------------------------------
# _db_row_to_synthesized_story
# ---------------------------------------------------------------------------

class TestDbRowToSynthesizedStory:
    def test_valid_row_returns_synthesized_story(self):
        row = _make_db_row()
        story = _db_row_to_synthesized_story(row)
        assert story is not None
        assert story.title == row["title"]
        assert story.body == row["body"]
        assert story.topic == row["topic"]

    def test_source_count_derived_from_sources_list(self):
        row = _make_db_row(sources=["A", "B", "C"])
        story = _db_row_to_synthesized_story(row)
        assert story.source_count == 3

    def test_empty_sources_defaults_source_count_to_one(self):
        # Build row directly — _make_db_row uses `or` which converts [] to default list
        row = {**_make_db_row(), "sources": []}
        story = _db_row_to_synthesized_story(row)
        assert story.source_count == 1

    def test_missing_title_returns_none(self):
        row = _make_db_row(title="")
        result = _db_row_to_synthesized_story(row)
        assert result is None

    def test_missing_body_returns_none(self):
        row = _make_db_row(body="")
        result = _db_row_to_synthesized_story(row)
        assert result is None

    def test_none_title_returns_none(self):
        row = _make_db_row()
        row["title"] = None
        result = _db_row_to_synthesized_story(row)
        assert result is None

    def test_embedding_stored_on_story(self):
        embedding = [0.5] * 1024
        row = _make_db_row(embedding=embedding)
        story = _db_row_to_synthesized_story(row)
        assert story.cluster_embedding == embedding

    def test_null_embedding_yields_empty_list(self):
        row = _make_db_row()
        row["embedding"] = None
        story = _db_row_to_synthesized_story(row)
        assert story.cluster_embedding == []

    def test_unknown_topic_falls_back_to_other(self):
        row = _make_db_row(topic=None)
        story = _db_row_to_synthesized_story(row)
        assert story.topic == "other"


# ---------------------------------------------------------------------------
# run_weekend_catchup — orchestration
# ---------------------------------------------------------------------------

class TestRunWeekendCatchup:
    """Unit tests with mocked DB and gmail_service."""

    def _make_patchers(self, rows: list[dict]):
        return {
            "get_unacknowledged_stories": patch(
                "pipeline.weekend_catchup.get_unacknowledged_stories",
                return_value=rows,
            ),
            "rank_stories": patch(
                "pipeline.weekend_catchup.rank_stories",
                side_effect=lambda stories: stories,  # passthrough
            ),
            "format_digest": patch(
                "pipeline.weekend_catchup.format_digest",
            ),
        }

    def test_returns_no_stories_when_db_empty(self):
        with patch("pipeline.weekend_catchup.get_unacknowledged_stories", return_value=[]):
            result = run_weekend_catchup(run_id="test-run")
        assert result["status"] == "no_stories"
        assert result["stories_included"] == 0

    def test_returns_no_valid_stories_when_all_rows_invalid(self):
        bad_rows = [{"id": "x", "title": "", "body": "", "sources": [], "topic": None, "embedding": None}]
        with patch("pipeline.weekend_catchup.get_unacknowledged_stories", return_value=bad_rows):
            result = run_weekend_catchup(run_id="test-run")
        assert result["status"] == "no_valid_stories"

    def test_dry_run_skips_send_and_returns_stats(self):
        rows = [_make_db_row()]
        mock_digest = MagicMock()
        mock_digest.story_count = 1
        mock_digest.word_count = 350
        mock_digest.subject = "Weekend Catch-Up | Saturday, March 28: AI Breakthrough"

        with (
            patch("pipeline.weekend_catchup.get_unacknowledged_stories", return_value=rows),
            patch("pipeline.weekend_catchup.rank_stories", side_effect=lambda s: s),
            patch("pipeline.weekend_catchup.format_digest", return_value=mock_digest),
        ):
            result = run_weekend_catchup(run_id="test-run", dry_run=True)

        assert result["status"] == "dry_run"
        assert result["stories_included"] == 1
        assert result["word_count"] == 350
        assert "subject" in result

    def test_full_run_calls_send_and_persist(self):
        rows = [_make_db_row(), _make_db_row(story_id="story-2", title="Markets Rally on Fed Data")]
        mock_digest = MagicMock()
        mock_digest.story_count = 2
        mock_digest.word_count = 700
        mock_digest.subject = "Weekend Catch-Up | Saturday, March 28: AI Breakthrough"
        mock_digest.body = "digest body text"

        mock_gmail = MagicMock()
        mock_gmail.send_message.return_value = "sent-msg-id"

        with (
            patch("pipeline.weekend_catchup.get_unacknowledged_stories", return_value=rows),
            patch("pipeline.weekend_catchup.rank_stories", side_effect=lambda s: s),
            patch("pipeline.weekend_catchup.format_digest", return_value=mock_digest),
            patch("pipeline.weekend_catchup.GmailService", return_value=mock_gmail),
            patch("pipeline.weekend_catchup.create_digest", return_value="digest-uuid"),
            patch("pipeline.weekend_catchup.get_or_create_cluster", return_value="cluster-uuid"),
            patch("pipeline.weekend_catchup.insert_story"),
            patch("pipeline.weekend_catchup.mark_digest_sent"),
        ):
            result = run_weekend_catchup(run_id="test-run")

        assert result["status"] == "sent"
        assert result["stories_included"] == 2
        assert result["digest_id"] == "digest-uuid"
        mock_gmail.send_message.assert_called_once()

    def test_full_run_calls_rank_stories(self):
        """Ranking by importance (not recency) is the core requirement — verify rank_stories is called."""
        rows = [_make_db_row()]
        mock_digest = MagicMock()
        mock_digest.story_count = 1
        mock_digest.word_count = 200
        mock_digest.subject = "Weekend Catch-Up"
        mock_digest.body = "body"

        mock_rank = MagicMock(side_effect=lambda s: s)
        mock_gmail = MagicMock()
        mock_gmail.send_message.return_value = "msg-id"

        with (
            patch("pipeline.weekend_catchup.get_unacknowledged_stories", return_value=rows),
            patch("pipeline.weekend_catchup.rank_stories", mock_rank),
            patch("pipeline.weekend_catchup.format_digest", return_value=mock_digest),
            patch("pipeline.weekend_catchup.GmailService", return_value=mock_gmail),
            patch("pipeline.weekend_catchup.create_digest", return_value="d-id"),
            patch("pipeline.weekend_catchup.get_or_create_cluster", return_value="c-id"),
            patch("pipeline.weekend_catchup.insert_story"),
            patch("pipeline.weekend_catchup.mark_digest_sent"),
        ):
            run_weekend_catchup(run_id="test-run")

        mock_rank.assert_called_once()

    def test_persist_failure_does_not_suppress_sent_status(self):
        """If DB persist fails after email is sent, we fall back to run_id as digest_id."""
        rows = [_make_db_row()]
        mock_digest = MagicMock()
        mock_digest.story_count = 1
        mock_digest.word_count = 200
        mock_digest.subject = "Weekend"
        mock_digest.body = "body"

        mock_gmail = MagicMock()
        mock_gmail.send_message.return_value = "msg-id"

        with (
            patch("pipeline.weekend_catchup.get_unacknowledged_stories", return_value=rows),
            patch("pipeline.weekend_catchup.rank_stories", side_effect=lambda s: s),
            patch("pipeline.weekend_catchup.format_digest", return_value=mock_digest),
            patch("pipeline.weekend_catchup.GmailService", return_value=mock_gmail),
            patch("pipeline.weekend_catchup.create_digest", side_effect=RuntimeError("DB error")),
        ):
            result = run_weekend_catchup(run_id="fallback-run")

        # Should still report "sent" — digest was delivered
        assert result["status"] == "sent"
        # digest_id falls back to run_id
        assert result["digest_id"] == "fallback-run"

    def test_multiple_valid_rows_all_converted(self):
        rows = [
            _make_db_row(story_id="s1", title="Story One"),
            _make_db_row(story_id="s2", title="Story Two"),
            _make_db_row(story_id="s3", title="Story Three"),
        ]
        mock_digest = MagicMock()
        mock_digest.story_count = 3
        mock_digest.word_count = 900
        mock_digest.subject = "Weekend"
        mock_digest.body = "body"

        rank_call_stories = []

        def capture_rank(stories):
            rank_call_stories.extend(stories)
            return stories

        mock_gmail = MagicMock()
        mock_gmail.send_message.return_value = "msg-id"

        with (
            patch("pipeline.weekend_catchup.get_unacknowledged_stories", return_value=rows),
            patch("pipeline.weekend_catchup.rank_stories", side_effect=capture_rank),
            patch("pipeline.weekend_catchup.format_digest", return_value=mock_digest),
            patch("pipeline.weekend_catchup.GmailService", return_value=mock_gmail),
            patch("pipeline.weekend_catchup.create_digest", return_value="d-id"),
            patch("pipeline.weekend_catchup.get_or_create_cluster", return_value="c-id"),
            patch("pipeline.weekend_catchup.insert_story"),
            patch("pipeline.weekend_catchup.mark_digest_sent"),
        ):
            run_weekend_catchup(run_id="test-run")

        assert len(rank_call_stories) == 3
        titles = {s.title for s in rank_call_stories}
        assert titles == {"Story One", "Story Two", "Story Three"}

    def test_invalid_rows_in_batch_are_skipped(self):
        """Bad rows (missing title/body) are skipped; valid rows proceed."""
        rows = [
            _make_db_row(story_id="s1", title=""),          # invalid
            _make_db_row(story_id="s2", title="Valid Story"),  # valid
        ]
        mock_digest = MagicMock()
        mock_digest.story_count = 1
        mock_digest.word_count = 200
        mock_digest.subject = "Weekend"
        mock_digest.body = "body"

        captured = []

        def capture_rank(stories):
            captured.extend(stories)
            return stories

        mock_gmail = MagicMock()
        mock_gmail.send_message.return_value = "msg-id"

        with (
            patch("pipeline.weekend_catchup.get_unacknowledged_stories", return_value=rows),
            patch("pipeline.weekend_catchup.rank_stories", side_effect=capture_rank),
            patch("pipeline.weekend_catchup.format_digest", return_value=mock_digest),
            patch("pipeline.weekend_catchup.GmailService", return_value=mock_gmail),
            patch("pipeline.weekend_catchup.create_digest", return_value="d-id"),
            patch("pipeline.weekend_catchup.get_or_create_cluster", return_value="c-id"),
            patch("pipeline.weekend_catchup.insert_story"),
            patch("pipeline.weekend_catchup.mark_digest_sent"),
        ):
            run_weekend_catchup(run_id="test-run")

        # Only 1 valid story reaches the ranker
        assert len(captured) == 1
        assert captured[0].title == "Valid Story"


# ---------------------------------------------------------------------------
# E2E tests (skipped unless DATABASE_URL is set)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestWeekendCatchupE2E:
    """Integration tests against real DB. Skipped if DATABASE_URL not set."""

    @pytest.fixture(autouse=True)
    def require_db(self):
        if not os.getenv("DATABASE_URL"):
            pytest.skip("DATABASE_URL not set — skipping E2E tests")

    def test_get_unacknowledged_stories_returns_list(self):
        """Verify the DB query runs without error and returns a list."""
        from tools.db import get_unacknowledged_stories
        result = get_unacknowledged_stories(days_back=7)
        assert isinstance(result, list), "Expected a list from get_unacknowledged_stories"

    def test_run_weekend_catchup_dry_run_against_real_db(self):
        """
        Happy-path E2E smoke test: dry_run mode queries real DB and formats a digest
        without sending email. May return 'no_stories' if no unacknowledged stories exist.
        """
        result = run_weekend_catchup(run_id="e2e-test-run", dry_run=True)
        assert result["status"] in ("dry_run", "no_stories", "no_valid_stories")
        assert "stories_included" in result or "status" in result

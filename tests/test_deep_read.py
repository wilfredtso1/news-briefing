"""
Tests for pipeline/deep_read.py

Unit tests: all DB, gmail_service, and extractor calls are mocked.
E2E tests: marked @pytest.mark.e2e — skipped if SUPABASE_URL not set.

Coverage target: >90% of orchestration logic.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, call, patch

import pytest

from gmail_service import EmailMessage
from pipeline.deep_read import (
    _extract_articles,
    _extract_first_url,
    _format_deep_read,
    _load_threshold,
    run_deep_read,
)
from pipeline.extractor import ExtractedStory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_email(
    message_id: str = "msg-001",
    sender: str = "Stratechery <newsletters@stratechery.com>",
    sender_email: str = "newsletters@stratechery.com",
    subject: str = "Stratechery: The Platform Wars",
    body_text: str = "This is a long deep-dive analysis. " * 100,
    body_html: str = "",
) -> EmailMessage:
    return EmailMessage(
        message_id=message_id,
        thread_id=f"thread-{message_id}",
        subject=subject,
        sender=sender,
        sender_email=sender_email,
        body_text=body_text,
        body_html=body_html,
        list_unsubscribe="<https://stratechery.com/unsubscribe>",
        list_id="<stratechery.stratechery.com>",
        date="Wed, 26 Mar 2026 08:00:00 -0500",
        labels=["INBOX", "UNREAD"],
    )


def _make_extracted_story(
    title: str = "The Platform Wars",
    body: str = "Deep analysis of how platforms compete for developer attention.",
    source_newsletter: str = "Stratechery <newsletters@stratechery.com>",
    source_email: str = "newsletters@stratechery.com",
) -> ExtractedStory:
    return ExtractedStory(
        title=title,
        body=body,
        key_facts=["Fact 1", "Fact 2"],
        source_newsletter=source_newsletter,
        source_email=source_email,
    )


def _make_article_pair(
    msg_id: str = "msg-001",
    title: str = "The Platform Wars",
) -> tuple[EmailMessage, ExtractedStory]:
    return (_make_email(message_id=msg_id), _make_extracted_story(title=title))


# ---------------------------------------------------------------------------
# _extract_first_url
# ---------------------------------------------------------------------------

class TestExtractFirstUrl:
    def test_extracts_href_from_html(self):
        html = '<a href="https://example.com/article">Read online</a>'
        assert _extract_first_url(html) == "https://example.com/article"

    def test_extracts_url_with_single_quotes(self):
        html = "<a href='https://stratechery.com/2026/platform-wars'>Read</a>"
        assert _extract_first_url(html) == "https://stratechery.com/2026/platform-wars"

    def test_returns_none_for_empty_html(self):
        assert _extract_first_url("") is None

    def test_returns_none_when_no_http_href(self):
        html = '<a href="mailto:editor@example.com">Contact</a>'
        assert _extract_first_url(html) is None

    def test_returns_none_for_none_input(self):
        assert _extract_first_url(None) is None

    def test_returns_first_url_when_multiple_present(self):
        html = (
            '<a href="https://first.com">First</a>'
            '<a href="https://second.com">Second</a>'
        )
        assert _extract_first_url(html) == "https://first.com"

    def test_handles_href_without_quotes(self):
        html = "<a href=https://noquotes.com/path>Link</a>"
        assert _extract_first_url(html) == "https://noquotes.com/path"


# ---------------------------------------------------------------------------
# _load_threshold
# ---------------------------------------------------------------------------

class TestLoadThreshold:
    def test_returns_value_from_agent_config(self):
        with patch("pipeline.deep_read.get_config", return_value=3):
            assert _load_threshold() == 3

    def test_falls_back_to_default_when_config_none(self):
        with patch("pipeline.deep_read.get_config", return_value=None):
            assert _load_threshold() == 5

    def test_falls_back_to_default_on_exception(self):
        with patch("pipeline.deep_read.get_config", side_effect=RuntimeError("DB down")):
            assert _load_threshold() == 5

    def test_coerces_string_to_int(self):
        with patch("pipeline.deep_read.get_config", return_value="7"):
            assert _load_threshold() == 7


# ---------------------------------------------------------------------------
# _extract_articles
# ---------------------------------------------------------------------------

class TestExtractArticles:
    def test_returns_story_for_each_successful_extraction(self):
        messages = [_make_email("msg-1"), _make_email("msg-2")]
        story = _make_extracted_story()

        with patch("pipeline.deep_read.extract_stories", return_value=[story]):
            results = _extract_articles(messages)

        assert len(results) == 2
        # Each result is (EmailMessage, ExtractedStory)
        assert results[0][1].title == story.title

    def test_uses_first_story_from_extraction(self):
        """Long-form emails have one primary article — we use the first."""
        messages = [_make_email()]
        story1 = _make_extracted_story(title="Primary Article")
        story2 = _make_extracted_story(title="Secondary Article")

        with patch("pipeline.deep_read.extract_stories", return_value=[story1, story2]):
            results = _extract_articles(messages)

        assert results[0][1].title == "Primary Article"

    def test_skips_message_when_extraction_returns_empty(self):
        # Give the second message a distinct sender_email so the side_effect can detect it.
        # _extract_articles passes msg.sender_email to extract_stories as sender_email.
        messages = [
            _make_email("good"),
            _make_email("empty-result", sender_email="empty-result@example.com"),
        ]

        def extraction_side_effect(body_text, body_html, newsletter_name, sender_email):
            if "empty-result" in newsletter_name or "empty-result" in sender_email:
                return []
            return [_make_extracted_story()]

        with patch("pipeline.deep_read.extract_stories", side_effect=extraction_side_effect):
            results = _extract_articles(messages)

        assert len(results) == 1

    def test_preserves_message_alongside_story(self):
        """The original EmailMessage is kept so the formatter can include the link."""
        msg = _make_email(message_id="test-msg")
        story = _make_extracted_story()

        with patch("pipeline.deep_read.extract_stories", return_value=[story]):
            results = _extract_articles([msg])

        assert results[0][0].message_id == "test-msg"

    def test_empty_message_list_returns_empty(self):
        results = _extract_articles([])
        assert results == []


# ---------------------------------------------------------------------------
# _format_deep_read
# ---------------------------------------------------------------------------

class TestFormatDeepRead:
    def _make_articles(self, n: int) -> list[tuple[EmailMessage, ExtractedStory]]:
        return [_make_article_pair(f"msg-{i}", f"Article {i}") for i in range(1, n + 1)]

    def test_subject_includes_first_article_title(self):
        articles = self._make_articles(3)
        subject, _ = _format_deep_read(articles, "Thursday, March 27")
        assert "Article 1" in subject

    def test_subject_includes_deep_read_label(self):
        articles = self._make_articles(3)
        subject, _ = _format_deep_read(articles, "Thursday, March 27")
        assert "Deep Read" in subject

    def test_body_includes_all_article_titles(self):
        articles = self._make_articles(4)
        _, body = _format_deep_read(articles, "Thursday, March 27")
        for i in range(1, 5):
            assert f"Article {i}" in body

    def test_body_includes_article_numbering(self):
        articles = self._make_articles(3)
        _, body = _format_deep_read(articles, "Thursday, March 27")
        assert "[1 of 3]" in body
        assert "[2 of 3]" in body
        assert "[3 of 3]" in body

    def test_body_includes_sender_for_each_article(self):
        articles = self._make_articles(3)
        _, body = _format_deep_read(articles, "Thursday, March 27")
        # All articles use the default sender
        assert "Stratechery <newsletters@stratechery.com>" in body

    def test_body_includes_original_link_from_html(self):
        msg = _make_email(body_html='<a href="https://stratechery.com/2026/platform-wars">Read</a>')
        story = _make_extracted_story()
        articles = [(msg, story)]
        _, body = _format_deep_read(articles, "Thursday, March 27")
        assert "https://stratechery.com/2026/platform-wars" in body

    def test_body_falls_back_to_sender_email_when_no_link(self):
        articles = self._make_articles(3)  # body_html="" by default
        _, body = _format_deep_read(articles, "Thursday, March 27")
        assert "newsletters@stratechery.com" in body

    def test_body_includes_article_content(self):
        articles = self._make_articles(3)
        _, body = _format_deep_read(articles, "Thursday, March 27")
        assert "Deep analysis of how platforms compete" in body

    def test_footer_includes_article_count(self):
        articles = self._make_articles(4)
        _, body = _format_deep_read(articles, "Thursday, March 27")
        assert "4 articles" in body


# ---------------------------------------------------------------------------
# run_deep_read — orchestration
# ---------------------------------------------------------------------------

class TestRunDeepRead:
    """Unit tests with all external dependencies mocked."""

    def _mock_sources(self, n_long_form: int = 6):
        """Return mock active sources with n_long_form long_form entries."""
        return [
            {
                "sender_email": f"newsletter{i}@example.com",
                "type": "long_form",
                "status": "active",
            }
            for i in range(n_long_form)
        ]

    def test_below_threshold_returns_early(self):
        """Pipeline aborts if fewer long-form pieces available than threshold."""
        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = ["msg-1", "msg-2"]
        mock_gmail.get_messages.return_value = [
            _make_email(message_id="msg-1", sender_email="newsletter0@example.com"),
            _make_email(message_id="msg-2", sender_email="newsletter1@example.com"),
        ]

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=self._mock_sources()),
            patch("pipeline.deep_read.get_config", return_value=5),  # threshold = 5
        ):
            result = run_deep_read(run_id="test-run")

        assert result["status"] == "below_threshold"
        assert result["available"] == 2
        assert result["threshold"] == 5

    def test_no_long_form_sources_returns_below_threshold(self):
        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = ["msg-1"]
        mock_gmail.get_messages.return_value = [_make_email()]

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=[]),
            patch("pipeline.deep_read.get_config", return_value=5),
        ):
            result = run_deep_read(run_id="test-run")

        assert result["status"] == "below_threshold"
        assert result["available"] == 0

    def test_dry_run_skips_send_and_archive(self):
        # 5 long_form messages — meets default threshold of 5
        messages = [
            _make_email(message_id=f"msg-{i}", sender_email=f"newsletter{i}@example.com")
            for i in range(5)
        ]
        story = _make_extracted_story()
        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = [m.message_id for m in messages]
        mock_gmail.get_messages.return_value = messages

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=self._mock_sources(5)),
            patch("pipeline.deep_read.get_config", return_value=5),
            patch("pipeline.deep_read.extract_stories", return_value=[story]),
        ):
            result = run_deep_read(run_id="test-run", dry_run=True)

        assert result["status"] == "dry_run"
        assert result["articles_included"] >= 3
        mock_gmail.send_message.assert_not_called()
        mock_gmail.archive_messages.assert_not_called()

    def test_full_run_sends_and_archives(self):
        messages = [
            _make_email(message_id=f"msg-{i}", sender_email=f"newsletter{i}@example.com")
            for i in range(5)
        ]
        story = _make_extracted_story()
        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = [m.message_id for m in messages]
        mock_gmail.get_messages.return_value = messages
        mock_gmail.send_message.return_value = "sent-msg-id"

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=self._mock_sources(5)),
            patch("pipeline.deep_read.get_config", return_value=5),
            patch("pipeline.deep_read.extract_stories", return_value=[story]),
            patch("pipeline.deep_read.create_digest", return_value="digest-id"),
            patch("pipeline.deep_read.get_or_create_cluster", return_value="cluster-id"),
            patch("pipeline.deep_read.insert_story"),
            patch("pipeline.deep_read.mark_digest_sent"),
        ):
            result = run_deep_read(run_id="test-run")

        assert result["status"] == "sent"
        assert result["digest_id"] == "digest-id"
        mock_gmail.send_message.assert_called_once()
        mock_gmail.archive_messages.assert_called_once()

    def test_caps_articles_at_five(self):
        """Even with 10 messages, only 5 are processed."""
        messages = [
            _make_email(message_id=f"msg-{i}", sender_email=f"newsletter{i}@example.com")
            for i in range(10)
        ]
        story = _make_extracted_story()
        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = [m.message_id for m in messages]
        mock_gmail.get_messages.return_value = messages
        mock_gmail.send_message.return_value = "sent-msg-id"

        extract_call_count = []

        def counting_extract(body_text, body_html, newsletter_name, sender_email):
            extract_call_count.append(1)
            return [story]

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=self._mock_sources(10)),
            patch("pipeline.deep_read.get_config", return_value=5),
            patch("pipeline.deep_read.extract_stories", side_effect=counting_extract),
            patch("pipeline.deep_read.create_digest", return_value="digest-id"),
            patch("pipeline.deep_read.get_or_create_cluster", return_value="cluster-id"),
            patch("pipeline.deep_read.insert_story"),
            patch("pipeline.deep_read.mark_digest_sent"),
        ):
            result = run_deep_read(run_id="test-run")

        # Only 5 extraction calls (capped at _MAX_ARTICLES)
        assert len(extract_call_count) == 5
        assert result["articles_included"] == 5

    def test_insufficient_articles_after_extraction(self):
        """If extraction yields fewer than 3 articles, abort."""
        messages = [
            _make_email(message_id=f"msg-{i}", sender_email=f"newsletter{i}@example.com")
            for i in range(5)
        ]
        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = [m.message_id for m in messages]
        mock_gmail.get_messages.return_value = messages

        call_count = [0]

        def sparse_extract(body_text, body_html, newsletter_name, sender_email):
            call_count[0] += 1
            # Return empty for all but first 2
            if call_count[0] <= 2:
                return [_make_extracted_story(title=f"Article {call_count[0]}")]
            return []

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=self._mock_sources(5)),
            patch("pipeline.deep_read.get_config", return_value=5),
            patch("pipeline.deep_read.extract_stories", side_effect=sparse_extract),
        ):
            result = run_deep_read(run_id="test-run")

        assert result["status"] == "insufficient_articles"
        assert result["articles_included"] == 2

    def test_persist_failure_does_not_suppress_sent_status(self):
        """If DB persist fails after email is sent, we fall back to run_id as digest_id."""
        messages = [
            _make_email(message_id=f"msg-{i}", sender_email=f"newsletter{i}@example.com")
            for i in range(5)
        ]
        story = _make_extracted_story()
        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = [m.message_id for m in messages]
        mock_gmail.get_messages.return_value = messages
        mock_gmail.send_message.return_value = "sent-msg-id"

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=self._mock_sources(5)),
            patch("pipeline.deep_read.get_config", return_value=5),
            patch("pipeline.deep_read.extract_stories", return_value=[story]),
            patch("pipeline.deep_read.create_digest", side_effect=RuntimeError("DB error")),
        ):
            result = run_deep_read(run_id="fallback-run")

        assert result["status"] == "sent"
        assert result["digest_id"] == "fallback-run"

    def test_filters_to_long_form_senders_only(self):
        """Messages from non-long_form sources are excluded even if present in inbox."""
        long_form_msg = _make_email(message_id="lf-1", sender_email="longform@example.com")
        news_brief_msg = _make_email(message_id="nb-1", sender_email="brief@example.com")

        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = ["lf-1", "nb-1"]
        mock_gmail.get_messages.return_value = [long_form_msg, news_brief_msg]

        sources = [
            {"sender_email": "longform@example.com", "type": "long_form", "status": "active"},
            {"sender_email": "brief@example.com", "type": "news_brief", "status": "active"},
        ]

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=sources),
            patch("pipeline.deep_read.get_config", return_value=5),
        ):
            result = run_deep_read(run_id="test-run")

        # Only 1 long_form message — below threshold of 5
        assert result["status"] == "below_threshold"
        assert result["available"] == 1

    def test_returns_word_count_in_result(self):
        messages = [
            _make_email(message_id=f"msg-{i}", sender_email=f"newsletter{i}@example.com")
            for i in range(5)
        ]
        story = _make_extracted_story()
        mock_gmail = MagicMock()
        mock_gmail.list_inbox_messages.return_value = [m.message_id for m in messages]
        mock_gmail.get_messages.return_value = messages
        mock_gmail.send_message.return_value = "sent-msg-id"

        with (
            patch("pipeline.deep_read.GmailService", return_value=mock_gmail),
            patch("pipeline.deep_read.get_active_sources", return_value=self._mock_sources(5)),
            patch("pipeline.deep_read.get_config", return_value=5),
            patch("pipeline.deep_read.extract_stories", return_value=[story]),
            patch("pipeline.deep_read.create_digest", return_value="digest-id"),
            patch("pipeline.deep_read.get_or_create_cluster", return_value="cluster-id"),
            patch("pipeline.deep_read.insert_story"),
            patch("pipeline.deep_read.mark_digest_sent"),
        ):
            result = run_deep_read(run_id="test-run")

        assert "word_count" in result
        assert isinstance(result["word_count"], int)
        assert result["word_count"] > 0


# ---------------------------------------------------------------------------
# E2E tests (skipped unless SUPABASE_URL is set)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestDeepReadE2E:
    """Integration tests against real DB. Skipped if SUPABASE_URL not set."""

    @pytest.fixture(autouse=True)
    def require_db(self):
        if not os.getenv("SUPABASE_URL"):
            pytest.skip("SUPABASE_URL not set — skipping E2E tests")

    def test_get_active_sources_returns_list(self):
        """Verify the DB query runs without error."""
        from tools.db import get_active_sources
        result = get_active_sources()
        assert isinstance(result, list)

    def test_load_threshold_from_real_config(self):
        """Verify _load_threshold reads from real agent_config without crashing."""
        threshold = _load_threshold()
        assert isinstance(threshold, int)
        assert threshold >= 1

"""
Tests for pipeline/daily_brief.py and the _run_daily_brief() job handler in main.py.

Coverage:
- Happy-path end-to-end (all steps succeed → email sent, DB persisted)
- Early-return guards (no messages, no newsletters, no stories)
- Anchor cutoff logic (before cutoff skips; after cutoff runs regardless)
- Onboarding gate (brief skipped when onboarding incomplete)
- Component failure resilience (single-newsletter extraction failure continues)
- dry_run mode (skips send + archive, skips DB persist)

External I/O: all mocked. Never calls real Gmail, Anthropic, Voyage, Supabase.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from gmail_service import EmailMessage
from pipeline.daily_brief import run
from pipeline.extractor import ExtractedStory
from pipeline.synthesizer import SynthesizedStory
from pipeline.embedder import StoryCluster
from pipeline.formatter import FormattedDigest


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------

def _make_email(
    message_id: str = "msg-001",
    sender: str = "Morning Brew <crew@morningbrew.com>",
    sender_email: str = "crew@morningbrew.com",
    subject: str = "☕ Morning Brew",
    body_text: str = "Tech: AI is booming. Markets: Stocks up. Crypto: Bitcoin rises.",
    body_html: str = "",
    labels: list[str] | None = None,
) -> EmailMessage:
    return EmailMessage(
        message_id=message_id,
        thread_id=f"thread-{message_id}",
        subject=subject,
        sender=sender,
        sender_email=sender_email,
        body_text=body_text,
        body_html=body_html,
        list_unsubscribe="<https://morningbrew.com/unsubscribe>",
        list_id="morning-brew",
        date="Wed, 26 Mar 2026 06:15:00 -0500",
        labels=labels or ["INBOX", "UNREAD"],
    )


def _make_extracted_story(title: str = "AI Is Booming", source_email: str = "crew@morningbrew.com") -> ExtractedStory:
    return ExtractedStory(
        title=title,
        body="Researchers say AI investment is at record highs this quarter.",
        key_facts=["AI investment at record highs", "Q1 2026"],
        source_newsletter="Morning Brew",
        source_email=source_email,
    )


def _make_synthesized_story(title: str = "AI Is Booming", source_count: int = 2) -> SynthesizedStory:
    return SynthesizedStory(
        title=title,
        body="Researchers say AI investment is at record highs.",
        topic="ai",
        source_newsletters=["Morning Brew", "Axios AM"][:source_count],
        source_emails=["crew@morningbrew.com", "axiosam@axios.com"][:source_count],
        source_count=source_count,
        key_facts=["AI investment at record highs"],
        cluster_embedding=[0.1] * 1024,
    )


def _make_digest(
    subject: str = "Your Brief — Wednesday, March 26",
    body: str = "--- AI Is Booming ---\nResearchers say AI investment is at record highs.",
    word_count: int = 120,
    story_count: int = 1,
) -> FormattedDigest:
    return FormattedDigest(
        subject=subject,
        body=body,
        word_count=word_count,
        story_count=story_count,
        full_count=1,
        brief_count=0,
        one_liner_count=0,
    )


def _make_cluster(stories: list | None = None) -> StoryCluster:
    cluster = MagicMock(spec=StoryCluster)
    cluster.stories = stories or [_make_extracted_story()]
    return cluster


def _news_brief_result(sender_email: str = "crew@morningbrew.com") -> MagicMock:
    r = MagicMock()
    r.is_newsletter = True
    r.source_type = "news_brief"
    r.sender_email = sender_email
    return r


def _long_form_result(sender_email: str = "newsletters@stratechery.com") -> MagicMock:
    r = MagicMock()
    r.is_newsletter = True
    r.source_type = "long_form"
    r.sender_email = sender_email
    return r


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestRunHappyPath:
    """Full pipeline runs without errors → email sent, DB persisted."""

    def _run_with_all_mocked(self, dry_run: bool = False) -> dict:
        msg = _make_email()
        cluster = _make_cluster()
        story = _make_synthesized_story()
        digest = _make_digest()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", return_value=[_make_extracted_story()]),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
            patch("pipeline.daily_brief.create_digest", return_value="digest-uuid-1"),
            patch("pipeline.daily_brief.get_or_create_cluster", return_value="cluster-uuid-1"),
            patch("pipeline.daily_brief.insert_story"),
            patch("pipeline.daily_brief.mark_digest_sent"),
            patch("pipeline.daily_brief.with_retry", side_effect=lambda fn: fn),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            gmail.send_message.return_value = ("sent-msg-id", "sent-thread-id")
            mock_gmail_cls.return_value = gmail
            return run(run_id="test-run-1", dry_run=dry_run)

    def test_happy_path_returns_sent_status(self):
        result = self._run_with_all_mocked()
        assert result["status"] == "sent"

    def test_happy_path_returns_story_count(self):
        result = self._run_with_all_mocked()
        assert result["story_count"] == 1

    def test_happy_path_email_sent(self):
        msg = _make_email()
        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", return_value=[_make_extracted_story()]),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
            patch("pipeline.daily_brief.create_digest", return_value="digest-uuid-1"),
            patch("pipeline.daily_brief.get_or_create_cluster", return_value="cluster-uuid-1"),
            patch("pipeline.daily_brief.insert_story"),
            patch("pipeline.daily_brief.mark_digest_sent"),
            patch("pipeline.daily_brief.with_retry", side_effect=lambda fn: fn),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            gmail.send_message.return_value = ("sent-msg-id", "sent-thread-id")
            mock_gmail_cls.return_value = gmail

            run(run_id="test-run-1")

        gmail.send_message.assert_called_once()
        call_kwargs = gmail.send_message.call_args
        assert call_kwargs is not None, "send_message was never called"

    def test_happy_path_source_emails_archived(self):
        msg = _make_email(message_id="msg-001")
        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", return_value=[_make_extracted_story()]),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
            patch("pipeline.daily_brief.create_digest", return_value="digest-uuid-1"),
            patch("pipeline.daily_brief.get_or_create_cluster", return_value="cluster-uuid-1"),
            patch("pipeline.daily_brief.insert_story"),
            patch("pipeline.daily_brief.mark_digest_sent"),
            patch("pipeline.daily_brief.with_retry", side_effect=lambda fn: fn),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            gmail.send_message.return_value = ("sent-msg-id", "sent-thread-id")
            mock_gmail_cls.return_value = gmail

            run(run_id="test-run-1")

        gmail.archive_messages.assert_called_once_with(["msg-001"])

    def test_happy_path_digest_persisted_to_db(self):
        msg = _make_email()
        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", return_value=[_make_extracted_story()]),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
            patch("pipeline.daily_brief.with_retry", side_effect=lambda fn: fn),
            patch("pipeline.daily_brief.create_digest", return_value="digest-uuid-1") as mock_create,
            patch("pipeline.daily_brief.get_or_create_cluster", return_value="cluster-uuid-1"),
            patch("pipeline.daily_brief.insert_story") as mock_insert,
            patch("pipeline.daily_brief.mark_digest_sent") as mock_mark,
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            gmail.send_message.return_value = ("sent-msg-id", "sent-thread-id")
            mock_gmail_cls.return_value = gmail

            run(run_id="test-run-1")

        mock_create.assert_called_once_with(digest_type="daily_brief", run_id="test-run-1")
        mock_insert.assert_called_once()
        mock_mark.assert_called_once_with(
            digest_id="digest-uuid-1",
            word_count=digest.word_count,
            story_count=digest.story_count,
            sent_message_id="sent-msg-id",
            thread_id="sent-thread-id",
        )


# ---------------------------------------------------------------------------
# Early returns / guards
# ---------------------------------------------------------------------------

class TestEarlyReturns:
    """Pipeline returns a non-sent status when input is insufficient."""

    def test_no_inbox_messages_returns_no_messages(self):
        with patch("pipeline.daily_brief.GmailService") as mock_gmail_cls:
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = []
            mock_gmail_cls.return_value = gmail

            result = run(run_id="test-run")

        assert result["status"] == "no_messages"
        assert result["story_count"] == 0

    def test_only_long_form_newsletters_returns_no_newsletters(self):
        msg = _make_email(sender_email="newsletters@stratechery.com")

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_long_form_result()),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            mock_gmail_cls.return_value = gmail

            result = run(run_id="test-run")

        assert result["status"] == "no_newsletters"
        assert result["story_count"] == 0

    def test_extraction_failure_for_all_newsletters_returns_no_stories(self):
        msg = _make_email()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", return_value=[]),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            mock_gmail_cls.return_value = gmail

            result = run(run_id="test-run")

        assert result["status"] == "no_stories"
        assert result["story_count"] == 0

    def test_long_form_newsletter_not_added_to_brief_messages(self):
        """Long-form newsletters are classified out and should not reach extract_stories."""
        long_form_msg = _make_email(sender_email="newsletters@stratechery.com")
        brief_msg = _make_email(sender_email="crew@morningbrew.com", message_id="msg-002")

        classify_results = [_long_form_result(), _news_brief_result()]
        call_count = {"n": 0}

        def side_effect_classify(msg):
            result = classify_results[call_count["n"]]
            call_count["n"] += 1
            return result

        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", side_effect=side_effect_classify),
            patch("pipeline.daily_brief.extract_stories", return_value=[_make_extracted_story()]) as mock_extract,
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
            patch("pipeline.daily_brief.create_digest", return_value="digest-uuid-1"),
            patch("pipeline.daily_brief.get_or_create_cluster", return_value="cluster-uuid-1"),
            patch("pipeline.daily_brief.insert_story"),
            patch("pipeline.daily_brief.mark_digest_sent"),
            patch("pipeline.daily_brief.with_retry", side_effect=lambda fn: fn),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001", "msg-002"]
            gmail.get_messages.return_value = [long_form_msg, brief_msg]
            gmail.send_message.return_value = ("sent-id", "thread-id")
            mock_gmail_cls.return_value = gmail

            run(run_id="test-run")

        # extract_stories called once — only for the brief newsletter
        assert mock_extract.call_count == 1
        assert mock_extract.call_args[1]["sender_email"] == "crew@morningbrew.com"


# ---------------------------------------------------------------------------
# Resilience: single newsletter extraction failure
# ---------------------------------------------------------------------------

class TestResilienceExtractionFailure:
    """A newsletter that fails extraction should be skipped; others continue."""

    def test_single_newsletter_extraction_failure_does_not_crash_pipeline(self):
        """If one newsletter fails to extract stories, the pipeline continues with others."""
        msg_good = _make_email(message_id="msg-good", sender_email="crew@morningbrew.com")
        msg_bad = _make_email(message_id="msg-bad", sender_email="axiosam@axios.com")

        extract_results = {
            "crew@morningbrew.com": [_make_extracted_story()],
            "axiosam@axios.com": [],  # extraction failed → empty
        }

        def extract_side_effect(**kwargs):
            return extract_results[kwargs["sender_email"]]

        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", side_effect=extract_side_effect),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
            patch("pipeline.daily_brief.create_digest", return_value="digest-uuid-1"),
            patch("pipeline.daily_brief.get_or_create_cluster", return_value="cluster-uuid-1"),
            patch("pipeline.daily_brief.insert_story"),
            patch("pipeline.daily_brief.mark_digest_sent"),
            patch("pipeline.daily_brief.with_retry", side_effect=lambda fn: fn),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-good", "msg-bad"]
            gmail.get_messages.return_value = [msg_good, msg_bad]
            gmail.send_message.return_value = ("sent-id", "thread-id")
            mock_gmail_cls.return_value = gmail

            result = run(run_id="test-run")

        # Pipeline completes; successful newsletter contributed its story
        assert result["status"] == "sent"

    def test_newsletter_with_zero_stories_not_archived(self):
        """A newsletter that yielded no stories should not be in the archive list."""
        msg_good = _make_email(message_id="msg-good", sender_email="crew@morningbrew.com")
        msg_bad = _make_email(message_id="msg-bad", sender_email="axiosam@axios.com")

        extract_results = {
            "crew@morningbrew.com": [_make_extracted_story()],
            "axiosam@axios.com": [],
        }

        def extract_side_effect(**kwargs):
            return extract_results[kwargs["sender_email"]]

        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", side_effect=extract_side_effect),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
            patch("pipeline.daily_brief.create_digest", return_value="digest-uuid-1"),
            patch("pipeline.daily_brief.get_or_create_cluster", return_value="cluster-uuid-1"),
            patch("pipeline.daily_brief.insert_story"),
            patch("pipeline.daily_brief.mark_digest_sent"),
            patch("pipeline.daily_brief.with_retry", side_effect=lambda fn: fn),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-good", "msg-bad"]
            gmail.get_messages.return_value = [msg_good, msg_bad]
            gmail.send_message.return_value = ("sent-id", "thread-id")
            mock_gmail_cls.return_value = gmail

            run(run_id="test-run")

        # Only the newsletter that yielded stories should be archived
        archived_ids = gmail.archive_messages.call_args[0][0]
        assert "msg-good" in archived_ids
        assert "msg-bad" not in archived_ids


# ---------------------------------------------------------------------------
# dry_run mode
# ---------------------------------------------------------------------------

class TestDryRun:
    """dry_run=True skips email send, archiving, and DB persistence."""

    def test_dry_run_returns_dry_run_status(self):
        msg = _make_email()
        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", return_value=[_make_extracted_story()]),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            mock_gmail_cls.return_value = gmail

            result = run(run_id="test-run", dry_run=True)

        assert result["status"] == "dry_run"

    def test_dry_run_does_not_call_send_message(self):
        msg = _make_email()
        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", return_value=[_make_extracted_story()]),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            mock_gmail_cls.return_value = gmail

            run(run_id="test-run", dry_run=True)

        gmail.send_message.assert_not_called()
        gmail.archive_messages.assert_not_called()

    def test_dry_run_does_not_persist_to_db(self):
        msg = _make_email()
        story = _make_synthesized_story()
        digest = _make_digest()
        cluster = _make_cluster()

        with (
            patch("pipeline.daily_brief.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.classify", return_value=_news_brief_result()),
            patch("pipeline.daily_brief.extract_stories", return_value=[_make_extracted_story()]),
            patch("pipeline.daily_brief.embed_and_cluster", return_value=[cluster]),
            patch("pipeline.daily_brief.resolve_ambiguous_clusters", return_value=[cluster]),
            patch("pipeline.daily_brief.synthesize_clusters", return_value=[story]),
            patch("pipeline.daily_brief.enrich_stories", return_value=[story]),
            patch("pipeline.daily_brief.gap_fill_topics", return_value=[story]),
            patch("pipeline.daily_brief.rank_stories", return_value=[story]),
            patch("pipeline.daily_brief.format_digest", return_value=digest),
            patch("pipeline.daily_brief.create_digest") as mock_create,
            patch("pipeline.daily_brief.insert_story") as mock_insert,
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [msg]
            mock_gmail_cls.return_value = gmail

            run(run_id="test-run", dry_run=True)

        mock_create.assert_not_called()
        mock_insert.assert_not_called()


# ---------------------------------------------------------------------------
# _run_daily_brief anchor cutoff logic (in main.py)
# ---------------------------------------------------------------------------

class TestRunDailyBriefAnchorCutoff:
    """
    Tests for the _run_daily_brief() background task in main.py.
    Specifically the anchor check + cutoff hour logic.

    _run_daily_brief uses local imports inside the function body, so patches
    target the source modules (tools.db, gmail_service, pipeline.daily_brief)
    rather than the main module namespace.
    """

    def _import_run(self):
        from main import _run_daily_brief
        return _run_daily_brief

    def test_onboarding_incomplete_skips_pipeline(self):
        """Pipeline is skipped entirely when onboarding not complete."""
        _run_daily_brief = self._import_run()

        with (
            patch("tools.db.get_config", return_value=False),
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            _run_daily_brief(run_id="test-run")

        mock_run.assert_not_called()

    def test_already_sent_today_skips_pipeline(self):
        """If a brief was already sent today, skip — prevents duplicate sends."""
        _run_daily_brief = self._import_run()

        with (
            patch("tools.db.get_config", return_value=True),
            patch("tools.db.was_brief_sent_today", return_value=True),
            patch("gmail_service.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            _run_daily_brief(run_id="test-run")

        mock_run.assert_not_called()
        mock_gmail_cls.assert_not_called()

    def test_not_yet_sent_today_proceeds_to_anchor_check(self):
        """If no brief sent today, continue to anchor check."""
        _run_daily_brief = self._import_run()

        with (
            patch("tools.db.get_config", return_value=True),
            patch("tools.db.was_brief_sent_today", return_value=False),
            patch("gmail_service.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            gmail = MagicMock()
            gmail.check_anchor_sources_present.return_value = True
            mock_gmail_cls.return_value = gmail

            _run_daily_brief(run_id="test-run")

        mock_run.assert_called_once_with(run_id="test-run")

    def test_anchors_not_ready_before_cutoff_skips_pipeline(self):
        """If anchors not present and current hour < cutoff → skip."""
        _run_daily_brief = self._import_run()

        with (
            patch("tools.db.get_config", return_value=True),
            patch("tools.db.was_brief_sent_today", return_value=False),
            patch("gmail_service.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.run") as mock_run,
            patch("main.datetime") as mock_dt,
        ):
            gmail = MagicMock()
            gmail.check_anchor_sources_present.return_value = False
            mock_gmail_cls.return_value = gmail
            mock_dt.now.return_value.hour = 8  # 8am — before 10am cutoff

            _run_daily_brief(run_id="test-run")

        mock_run.assert_not_called()

    def test_anchors_not_ready_at_cutoff_hour_runs_pipeline(self):
        """If anchors not present but current hour == cutoff → run anyway."""
        _run_daily_brief = self._import_run()

        with (
            patch("tools.db.get_config", return_value=True),
            patch("tools.db.was_brief_sent_today", return_value=False),
            patch("gmail_service.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.run") as mock_run,
            patch("main.datetime") as mock_dt,
        ):
            gmail = MagicMock()
            gmail.check_anchor_sources_present.return_value = False
            mock_gmail_cls.return_value = gmail
            mock_dt.now.return_value.hour = 10  # exactly at cutoff hour

            _run_daily_brief(run_id="test-run")

        mock_run.assert_called_once_with(run_id="test-run")

    def test_anchors_not_ready_past_cutoff_runs_pipeline(self):
        """If anchors not present and current hour > cutoff → run anyway."""
        _run_daily_brief = self._import_run()

        with (
            patch("tools.db.get_config", return_value=True),
            patch("tools.db.was_brief_sent_today", return_value=False),
            patch("gmail_service.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.run") as mock_run,
            patch("main.datetime") as mock_dt,
        ):
            gmail = MagicMock()
            gmail.check_anchor_sources_present.return_value = False
            mock_gmail_cls.return_value = gmail
            mock_dt.now.return_value.hour = 11  # past cutoff

            _run_daily_brief(run_id="test-run")

        mock_run.assert_called_once_with(run_id="test-run")

    def test_anchors_ready_before_cutoff_runs_pipeline(self):
        """If anchors are present, run immediately regardless of hour."""
        _run_daily_brief = self._import_run()

        with (
            patch("tools.db.get_config", return_value=True),
            patch("tools.db.was_brief_sent_today", return_value=False),
            patch("gmail_service.GmailService") as mock_gmail_cls,
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            gmail = MagicMock()
            gmail.check_anchor_sources_present.return_value = True
            mock_gmail_cls.return_value = gmail

            _run_daily_brief(run_id="test-run")

        mock_run.assert_called_once_with(run_id="test-run")

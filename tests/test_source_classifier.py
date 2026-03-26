"""
Unit tests for source_classifier.py.

All tests are pure — no DB calls, no network, no filesystem.
DB side-effects (_register) are mocked so tests remain isolated.
"""

from unittest.mock import MagicMock, patch

import pytest

from gmail_service import EmailMessage
from source_classifier import (
    ClassificationResult,
    _classify_type_by_length,
    _extract_name,
    _is_skip_sender,
    all_anchors_present,
    classify,
    is_anchor_present,
)


# ---------------------------------------------------------------------------
# _is_skip_sender
# ---------------------------------------------------------------------------

class TestIsSkipSender:
    def test_is_skip_sender_noreply(self):
        assert _is_skip_sender("noreply@amazon.com") is True

    def test_is_skip_sender_no_reply_hyphen(self):
        assert _is_skip_sender("no-reply@shopify.com") is True

    def test_is_skip_sender_notifications(self):
        assert _is_skip_sender("notifications@github.com") is True

    def test_is_skip_sender_support(self):
        assert _is_skip_sender("support@stripe.com") is True

    def test_is_skip_sender_billing(self):
        assert _is_skip_sender("billing@company.com") is True

    def test_is_skip_sender_normal_newsletter(self):
        assert _is_skip_sender("hello@morningbrew.com") is False

    def test_is_skip_sender_unknown_newsletter(self):
        assert _is_skip_sender("newsletter@somesite.com") is False


# ---------------------------------------------------------------------------
# _classify_type_by_length
# ---------------------------------------------------------------------------

class TestClassifyTypeByLength:
    def test_short_body_is_news_brief(self):
        short_body = "word " * 500  # 500 words — below threshold
        assert _classify_type_by_length(short_body) == "news_brief"

    def test_long_body_is_long_form(self):
        long_body = "word " * 2_000  # 2000 words — above threshold
        assert _classify_type_by_length(long_body) == "long_form"

    def test_exactly_at_threshold_is_long_form(self):
        body = "word " * 1_500
        assert _classify_type_by_length(body) == "long_form"

    def test_empty_body_is_news_brief(self):
        assert _classify_type_by_length("") == "news_brief"


# ---------------------------------------------------------------------------
# _extract_name
# ---------------------------------------------------------------------------

class TestExtractName:
    def test_extract_name_from_full_format(self):
        assert _extract_name("Morning Brew <morningbrew@morningbrew.com>") == "Morning Brew"

    def test_extract_name_quoted(self):
        assert _extract_name('"The Hustle" <hello@thehustle.co>') == "The Hustle"

    def test_extract_name_no_display_name(self):
        # Falls back to local part of email
        assert _extract_name("hello@morningbrew.com") == "hello"

    def test_extract_name_plain_email(self):
        assert _extract_name("axiosam@axios.com") == "axiosam"


# ---------------------------------------------------------------------------
# classify — known senders
# ---------------------------------------------------------------------------

class TestClassifyKnownSenders:
    def test_morning_brew_is_news_brief(self, news_brief_email):
        with patch("source_classifier._register"):
            result = classify(news_brief_email)
        assert result.is_newsletter is True
        assert result.source_type == "news_brief"
        assert result.confidence == "high"

    def test_stratechery_is_long_form(self, long_form_email):
        with patch("source_classifier._register"):
            result = classify(long_form_email)
        assert result.is_newsletter is True
        assert result.source_type == "long_form"
        assert result.confidence == "high"

    def test_axios_am_is_news_brief(self, axios_am_email):
        with patch("source_classifier._register"):
            result = classify(axios_am_email)
        assert result.is_newsletter is True
        assert result.source_type == "news_brief"
        assert result.confidence == "high"


# ---------------------------------------------------------------------------
# classify — non-newsletters
# ---------------------------------------------------------------------------

class TestClassifyNonNewsletters:
    def test_personal_email_not_newsletter(self, personal_email):
        result = classify(personal_email)
        assert result.is_newsletter is False
        assert result.source_type is None

    def test_transactional_email_not_newsletter(self, transactional_email):
        result = classify(transactional_email)
        assert result.is_newsletter is False
        assert result.source_type is None


# ---------------------------------------------------------------------------
# classify — unknown newsletter (discovered dynamically)
# ---------------------------------------------------------------------------

class TestClassifyUnknownNewsletter:
    def test_unknown_with_unsubscribe_header_is_newsletter(self, unknown_newsletter_email):
        with patch("source_classifier._register"):
            result = classify(unknown_newsletter_email)
        assert result.is_newsletter is True
        assert result.source_type == "news_brief"
        assert result.confidence == "high"

    def test_unknown_newsletter_calls_register(self, unknown_newsletter_email):
        with patch("source_classifier._register") as mock_register:
            classify(unknown_newsletter_email)
        mock_register.assert_called_once()

    def test_register_failure_does_not_crash_classifier(self, unknown_newsletter_email):
        """A DB failure in _register must not crash classification."""
        with patch("source_classifier.upsert_newsletter_source", side_effect=Exception("DB down")):
            result = classify(unknown_newsletter_email)
        assert result.is_newsletter is True  # Classification still succeeded


# ---------------------------------------------------------------------------
# Anchor detection
# ---------------------------------------------------------------------------

class TestAnchorDetection:
    def test_is_anchor_present_true(self, axios_am_email, news_brief_email):
        messages = [axios_am_email, news_brief_email]
        assert is_anchor_present(messages, "axiosam@axios.com") is True

    def test_is_anchor_present_false(self, news_brief_email, personal_email):
        messages = [news_brief_email, personal_email]
        assert is_anchor_present(messages, "axiosam@axios.com") is False

    def test_all_anchors_present_both_here(self, axios_am_email, news_brief_email):
        messages = [axios_am_email, news_brief_email]
        anchors = ("axiosam@axios.com", "morningbrew@morningbrew.com")
        assert all_anchors_present(messages, anchors) is True

    def test_all_anchors_present_one_missing(self, axios_am_email, personal_email):
        messages = [axios_am_email, personal_email]
        anchors = ("axiosam@axios.com", "morningbrew@morningbrew.com")
        assert all_anchors_present(messages, anchors) is False

    def test_all_anchors_present_empty_inbox(self):
        anchors = ("axiosam@axios.com", "morningbrew@morningbrew.com")
        assert all_anchors_present([], anchors) is False


# ---------------------------------------------------------------------------
# New KNOWN_NEWS_BRIEF_SENDERS — crew@morningbrew.com and markets@axios.com
# ---------------------------------------------------------------------------

def _make_email(sender_email: str, body_text: str = "") -> EmailMessage:
    """Helper to build a minimal EmailMessage for classification tests."""
    return EmailMessage(
        message_id="msg_test",
        thread_id="thread_test",
        subject="Test",
        sender=f"Test <{sender_email}>",
        sender_email=sender_email,
        body_text=body_text,
        body_html="",
        list_unsubscribe="<https://example.com/unsub>",
        list_id=None,
        date="Wed, 26 Mar 2026 06:00:00 -0500",
        labels=["INBOX", "UNREAD"],
    )


class TestNewKnownSenders:
    def test_crew_morningbrew_is_news_brief_regardless_of_body_length(self):
        """crew@morningbrew.com must be classified as news_brief even with a long body."""
        long_body = "word " * 3_000  # well above LONG_FORM_WORD_THRESHOLD
        msg = _make_email("crew@morningbrew.com", long_body)
        with patch("source_classifier._register"), \
             patch("source_classifier.get_source_by_email") as mock_db:
            result = classify(msg)
        # DB lookup must NOT be called — known sender short-circuits before DB check
        mock_db.assert_not_called()
        assert result.is_newsletter is True
        assert result.source_type == "news_brief"
        assert result.confidence == "high"

    def test_markets_axios_is_news_brief(self):
        """markets@axios.com must be classified as news_brief."""
        msg = _make_email("markets@axios.com", "word " * 100)
        with patch("source_classifier._register"), \
             patch("source_classifier.get_source_by_email") as mock_db:
            result = classify(msg)
        mock_db.assert_not_called()
        assert result.is_newsletter is True
        assert result.source_type == "news_brief"


# ---------------------------------------------------------------------------
# DB lookup behaviour
# ---------------------------------------------------------------------------

class TestDbLookup:
    def test_db_returning_news_brief_overrides_long_body_heuristic(self):
        """A long-body email from an unknown sender with DB type=news_brief stays news_brief."""
        long_body = "word " * 3_000
        msg = _make_email("unknown@newsletter.com", long_body)
        with patch("source_classifier._register"), \
             patch("source_classifier.get_source_by_email", return_value={"type": "news_brief"}):
            result = classify(msg)
        assert result.source_type == "news_brief"
        assert result.confidence == "high"
        assert "DB override" in result.reason

    def test_db_returning_long_form_overrides_short_body_heuristic(self):
        """A short-body email from an unknown sender with DB type=long_form becomes long_form."""
        short_body = "word " * 100
        msg = _make_email("unknown@newsletter.com", short_body)
        with patch("source_classifier._register"), \
             patch("source_classifier.get_source_by_email", return_value={"type": "long_form"}):
            result = classify(msg)
        assert result.source_type == "long_form"
        assert result.confidence == "high"

    def test_db_returning_none_falls_through_to_heuristic(self):
        """When DB returns None the heuristic runs normally."""
        short_body = "word " * 100
        msg = _make_email("unknown@newsletter.com", short_body)
        with patch("source_classifier._register"), \
             patch("source_classifier.get_source_by_email", return_value=None):
            result = classify(msg)
        # Short body → heuristic says news_brief
        assert result.source_type == "news_brief"
        assert "DB override" not in result.reason

    def test_db_exception_falls_through_to_heuristic_no_crash(self):
        """A DB exception must not crash the classifier; heuristic runs as fallback."""
        short_body = "word " * 100
        msg = _make_email("unknown@newsletter.com", short_body)
        with patch("source_classifier._register"), \
             patch("source_classifier.get_source_by_email", side_effect=Exception("DB down")):
            result = classify(msg)
        # Should still classify via heuristic — no exception raised
        assert result.is_newsletter is True
        assert result.source_type == "news_brief"

    def test_db_not_called_for_known_news_brief_sender(self):
        """DB lookup must be skipped entirely when sender is in KNOWN_NEWS_BRIEF_SENDERS."""
        msg = _make_email("axiosam@axios.com", "word " * 100)
        with patch("source_classifier._register"), \
             patch("source_classifier.get_source_by_email") as mock_db:
            classify(msg)
        mock_db.assert_not_called()

    def test_db_not_called_for_known_long_form_sender(self):
        """DB lookup must be skipped entirely when sender is in KNOWN_LONG_FORM_SENDERS."""
        msg = _make_email("newsletters@stratechery.com", "word " * 100)
        with patch("source_classifier._register"), \
             patch("source_classifier.get_source_by_email") as mock_db:
            classify(msg)
        mock_db.assert_not_called()

"""
Tests for pipeline/onboarding.py.

LLM calls: mock _parse_reply_chain.invoke directly — never call real Anthropic API.
Gmail: mock GmailService — never call real Gmail API.
DB: mock all tools.db helpers — never hit a real database.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from pipeline.onboarding import (
    _format_setup_email,
    process_onboarding_reply,
    run_onboarding,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_gmail():
    gmail = MagicMock()
    gmail.list_inbox_messages.return_value = ["msg_001", "msg_002"]
    gmail.get_messages.return_value = [
        MagicMock(sender_email="axiosam@axios.com"),
        MagicMock(sender_email="newsletters@stratechery.com"),
    ]
    gmail.send_message.return_value = ("sent_msg_id", "thread_id_abc")
    return gmail


@pytest.fixture
def mock_classify_news_brief():
    result = MagicMock()
    result.is_newsletter = True
    result.source_type = "news_brief"
    result.sender_email = "axiosam@axios.com"
    result.sender_name = "Axios AM"
    return result


@pytest.fixture
def mock_classify_long_form():
    result = MagicMock()
    result.is_newsletter = True
    result.source_type = "long_form"
    result.sender_email = "newsletters@stratechery.com"
    result.sender_name = "Stratechery"
    return result


@pytest.fixture
def active_sources():
    return [
        {"sender_email": "axiosam@axios.com", "name": "Axios AM", "type": "news_brief"},
        {"sender_email": "newsletters@stratechery.com", "name": "Stratechery", "type": "long_form"},
    ]


# ---------------------------------------------------------------------------
# run_onboarding — guard: already complete
# ---------------------------------------------------------------------------

class TestRunOnboardingAlreadyComplete:
    def test_returns_already_complete_when_flag_is_true(self):
        with patch("pipeline.onboarding.get_config", return_value=True):
            result = run_onboarding(run_id="test-run")

        assert result["status"] == "already_complete"

    def test_does_not_create_gmail_service_when_already_complete(self):
        with patch("pipeline.onboarding.get_config", return_value=True), \
             patch("pipeline.onboarding.GmailService") as mock_svc:
            run_onboarding(run_id="test-run")

        mock_svc.assert_not_called()


# ---------------------------------------------------------------------------
# run_onboarding — guard: pending reply
# ---------------------------------------------------------------------------

class TestRunOnboardingPendingReply:
    def test_returns_pending_reply_when_event_exists(self):
        with patch("pipeline.onboarding.get_config", return_value=False), \
             patch("pipeline.onboarding.get_pending_onboarding_event",
                   return_value={"id": "evt_001", "thread_id": "thr_abc"}):
            result = run_onboarding(run_id="test-run")

        assert result["status"] == "pending_reply"

    def test_does_not_send_email_when_pending(self, mock_gmail):
        with patch("pipeline.onboarding.get_config", return_value=False), \
             patch("pipeline.onboarding.get_pending_onboarding_event",
                   return_value={"id": "evt_001", "thread_id": "thr_abc"}), \
             patch("pipeline.onboarding.GmailService", return_value=mock_gmail):
            run_onboarding(run_id="test-run")

        mock_gmail.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# run_onboarding — happy path: sends email
# ---------------------------------------------------------------------------

class TestRunOnboardingSendsEmail:
    def test_returns_sent_status(self, mock_gmail, mock_classify_news_brief, mock_classify_long_form):
        with patch("pipeline.onboarding.get_config", return_value=False), \
             patch("pipeline.onboarding.get_pending_onboarding_event", return_value=None), \
             patch("pipeline.onboarding.GmailService", return_value=mock_gmail), \
             patch("pipeline.onboarding.source_classifier.classify",
                   side_effect=[mock_classify_news_brief, mock_classify_long_form]), \
             patch("pipeline.onboarding.get_active_sources", return_value=[]), \
             patch("pipeline.onboarding.create_onboarding_event", return_value="evt_001"), \
             patch("pipeline.onboarding.update_onboarding_thread"):
            result = run_onboarding(run_id="test-run")

        assert result["status"] == "sent"

    def test_creates_event_before_sending_email(self, mock_gmail, mock_classify_news_brief):
        call_order = []
        with patch("pipeline.onboarding.get_config", return_value=False), \
             patch("pipeline.onboarding.get_pending_onboarding_event", return_value=None), \
             patch("pipeline.onboarding.GmailService", return_value=mock_gmail), \
             patch("pipeline.onboarding.source_classifier.classify",
                   return_value=mock_classify_news_brief), \
             patch("pipeline.onboarding.get_active_sources", return_value=[]), \
             patch("pipeline.onboarding.create_onboarding_event",
                   side_effect=lambda: call_order.append("create") or "evt_001"), \
             patch("pipeline.onboarding.update_onboarding_thread"):
            mock_gmail.send_message.side_effect = lambda **kwargs: (
                call_order.append("send") or ("msg_id", "thread_id")
            )
            run_onboarding(run_id="test-run")

        assert call_order.index("create") < call_order.index("send")

    def test_stores_thread_id_after_send(self, mock_gmail, mock_classify_news_brief):
        with patch("pipeline.onboarding.get_config", return_value=False), \
             patch("pipeline.onboarding.get_pending_onboarding_event", return_value=None), \
             patch("pipeline.onboarding.GmailService", return_value=mock_gmail), \
             patch("pipeline.onboarding.source_classifier.classify",
                   return_value=mock_classify_news_brief), \
             patch("pipeline.onboarding.get_active_sources", return_value=[]), \
             patch("pipeline.onboarding.create_onboarding_event", return_value="evt_001"), \
             patch("pipeline.onboarding.update_onboarding_thread") as mock_update:
            run_onboarding(run_id="test-run")

        mock_update.assert_called_once_with("evt_001", "thread_id_abc", "sent_msg_id")

    def test_merges_active_sources_with_discovered(
        self, mock_gmail, mock_classify_news_brief, active_sources
    ):
        # Inbox only has Axios AM; Stratechery should be merged from active_sources
        mock_gmail.get_messages.return_value = [MagicMock()]
        with patch("pipeline.onboarding.get_config", return_value=False), \
             patch("pipeline.onboarding.get_pending_onboarding_event", return_value=None), \
             patch("pipeline.onboarding.GmailService", return_value=mock_gmail), \
             patch("pipeline.onboarding.source_classifier.classify",
                   return_value=mock_classify_news_brief), \
             patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding.create_onboarding_event", return_value="evt_001"), \
             patch("pipeline.onboarding.update_onboarding_thread"):
            result = run_onboarding(run_id="test-run")

        assert result["status"] == "sent"


# ---------------------------------------------------------------------------
# run_onboarding — no sources found
# ---------------------------------------------------------------------------

class TestRunOnboardingNoSources:
    def test_returns_no_sources_found_when_inbox_empty(self, mock_gmail):
        non_newsletter = MagicMock()
        non_newsletter.is_newsletter = False
        with patch("pipeline.onboarding.get_config", return_value=False), \
             patch("pipeline.onboarding.get_pending_onboarding_event", return_value=None), \
             patch("pipeline.onboarding.GmailService", return_value=mock_gmail), \
             patch("pipeline.onboarding.source_classifier.classify",
                   return_value=non_newsletter), \
             patch("pipeline.onboarding.get_active_sources", return_value=[]):
            result = run_onboarding(run_id="test-run")

        assert result["status"] == "no_sources_found"

    def test_does_not_send_email_when_no_sources(self, mock_gmail):
        non_newsletter = MagicMock()
        non_newsletter.is_newsletter = False
        with patch("pipeline.onboarding.get_config", return_value=False), \
             patch("pipeline.onboarding.get_pending_onboarding_event", return_value=None), \
             patch("pipeline.onboarding.GmailService", return_value=mock_gmail), \
             patch("pipeline.onboarding.source_classifier.classify",
                   return_value=non_newsletter), \
             patch("pipeline.onboarding.get_active_sources", return_value=[]):
            run_onboarding(run_id="test-run")

        mock_gmail.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# process_onboarding_reply — source trust weights
# ---------------------------------------------------------------------------

class TestProcessOnboardingReplySourceWeights:
    def test_boosts_trust_weight_for_important_sources(self, active_sources):
        fake_parsed = {
            "important_sources": ["axiosam@axios.com"],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "notes": "user likes Axios AM",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight") as mock_trust, \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied"):
            mock_chain.invoke.return_value = fake_parsed
            result = process_onboarding_reply("evt_001", "I love Axios AM", "run_001")

        mock_trust.assert_called_once_with("axiosam@axios.com", 1.8)
        assert any("axiosam@axios.com" in c for c in result["applied_changes"])

    def test_deprioritizes_specified_sources(self, active_sources):
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": ["newsletters@stratechery.com"],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "notes": "less Stratechery",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source") as mock_deprio, \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied"):
            mock_chain.invoke.return_value = fake_parsed
            result = process_onboarding_reply("evt_001", "less Stratechery", "run_001")

        mock_deprio.assert_called_once_with("newsletters@stratechery.com")
        assert any("deprioritized" in c for c in result["applied_changes"])

    def test_does_not_execute_unsubscribe_only_logs(self, active_sources):
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": ["newsletters@stratechery.com"],
            "topic_adjustments": {},
            "notes": "wants to unsubscribe",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied"):
            mock_chain.invoke.return_value = fake_parsed
            result = process_onboarding_reply("evt_001", "unsubscribe from Stratechery", "run_001")

        # Unsubscribe is noted in applied_changes but NOT executed
        assert any("pending confirmation" in c for c in result["applied_changes"])


# ---------------------------------------------------------------------------
# process_onboarding_reply — topic adjustments
# ---------------------------------------------------------------------------

class TestProcessOnboardingReplyTopics:
    def test_merges_topic_adjustments_with_existing_weights(self, active_sources):
        existing = {"ai": 1.5, "crypto": 0.5, "sports": 0.3}
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {"crypto": 0.2, "health_tech": 1.8},
            "notes": "less crypto, more health",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value=existing), \
             patch("pipeline.onboarding.set_config") as mock_set_config, \
             patch("pipeline.onboarding.mark_onboarding_applied"):
            mock_chain.invoke.return_value = fake_parsed
            process_onboarding_reply("evt_001", "less crypto, more health", "run_001")

        topic_call = next(
            c for c in mock_set_config.call_args_list
            if c.args[0] == "topic_weights"
        )
        merged = topic_call.args[1]
        # Existing keys preserved; updated keys use new values
        assert merged["ai"] == 1.5
        assert merged["crypto"] == 0.2
        assert merged["health_tech"] == 1.8
        assert merged["sports"] == 0.3

    def test_skips_topic_update_when_no_adjustments(self, active_sources):
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "notes": "no preferences",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config") as mock_set_config, \
             patch("pipeline.onboarding.mark_onboarding_applied"):
            mock_chain.invoke.return_value = fake_parsed
            process_onboarding_reply("evt_001", "looks good", "run_001")

        # set_config should only be called for onboarding_complete, not topic_weights
        topic_calls = [c for c in mock_set_config.call_args_list if c.args[0] == "topic_weights"]
        assert len(topic_calls) == 0


# ---------------------------------------------------------------------------
# process_onboarding_reply — marks onboarding complete
# ---------------------------------------------------------------------------

class TestProcessOnboardingReplyCompletion:
    def test_always_marks_onboarding_complete(self, active_sources):
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "notes": "",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config") as mock_set_config, \
             patch("pipeline.onboarding.mark_onboarding_applied"):
            mock_chain.invoke.return_value = fake_parsed
            process_onboarding_reply("evt_001", "read", "run_001")

        complete_call = next(
            c for c in mock_set_config.call_args_list
            if c.args[0] == "onboarding_complete"
        )
        assert complete_call.args[1] is True

    def test_marks_complete_even_when_parse_fails(self, active_sources):
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config") as mock_set_config, \
             patch("pipeline.onboarding.mark_onboarding_applied"):
            mock_chain.invoke.side_effect = Exception("LLM timeout")
            process_onboarding_reply("evt_001", "whatever", "run_001")

        complete_call = next(
            c for c in mock_set_config.call_args_list
            if c.args[0] == "onboarding_complete"
        )
        assert complete_call.args[1] is True

    def test_calls_mark_onboarding_applied_with_reply_and_preferences(self, active_sources):
        fake_parsed = {
            "important_sources": ["axiosam@axios.com"],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "notes": "test",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied") as mock_applied:
            mock_chain.invoke.return_value = fake_parsed
            process_onboarding_reply("evt_001", "I like Axios AM", "run_001")

        mock_applied.assert_called_once_with("evt_001", "I like Axios AM", fake_parsed)


# ---------------------------------------------------------------------------
# _format_setup_email
# ---------------------------------------------------------------------------

class TestFormatSetupEmail:
    def test_splits_news_brief_and_long_form_into_sections(self):
        discovered = {
            "axiosam@axios.com": {"name": "Axios AM", "type": "news_brief"},
            "newsletters@stratechery.com": {"name": "Stratechery", "type": "long_form"},
        }
        body = _format_setup_email(discovered)
        assert "Daily Brief:" in body
        assert "Long-Form" in body
        assert "Axios AM" in body
        assert "Stratechery" in body

    def test_omits_long_form_section_when_none_found(self):
        discovered = {
            "axiosam@axios.com": {"name": "Axios AM", "type": "news_brief"},
        }
        body = _format_setup_email(discovered)
        assert "Daily Brief:" in body
        assert "Long-Form" not in body

    def test_includes_reply_instructions(self):
        discovered = {
            "axiosam@axios.com": {"name": "Axios AM", "type": "news_brief"},
        }
        body = _format_setup_email(discovered)
        assert "Reply with:" in body
        assert "most important sources" in body
        assert "first daily brief runs after I hear back" in body

    def test_includes_sender_email_in_source_line(self):
        discovered = {
            "axiosam@axios.com": {"name": "Axios AM", "type": "news_brief"},
        }
        body = _format_setup_email(discovered)
        assert "axiosam@axios.com" in body

    def test_sources_sorted_alphabetically_by_name(self):
        discovered = {
            "z@example.com": {"name": "Zebra Newsletter", "type": "news_brief"},
            "a@example.com": {"name": "Aardvark Daily", "type": "news_brief"},
        }
        body = _format_setup_email(discovered)
        assert body.index("Aardvark") < body.index("Zebra")

    def test_includes_instruction_to_move_sources_between_lists(self):
        """4th bullet must tell user they can move sources between Daily Brief and Long-Form."""
        discovered = {
            "axiosam@axios.com": {"name": "Axios AM", "type": "news_brief"},
            "newsletters@stratechery.com": {"name": "Stratechery", "type": "long_form"},
        }
        body = _format_setup_email(discovered)
        assert "Move any source between" in body or "move any source between" in body.lower()


# ---------------------------------------------------------------------------
# process_onboarding_reply — source_type_corrections
# ---------------------------------------------------------------------------

class TestProcessOnboardingReplySourceTypeCorrections:
    def test_calls_update_source_type_for_valid_correction(self, active_sources):
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "source_type_corrections": [
                {"email": "crew@morningbrew.com", "type": "news_brief"}
            ],
            "notes": "morning brew should be in brief",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied"), \
             patch("pipeline.onboarding.update_source_type") as mock_update_type:
            mock_chain.invoke.return_value = fake_parsed
            result = process_onboarding_reply("evt_001", "Morning Brew should be in brief", "run_001")

        mock_update_type.assert_called_once_with("crew@morningbrew.com", "news_brief")
        assert any("reclassified" in c for c in result["applied_changes"])

    def test_calls_update_source_type_for_each_valid_correction(self, active_sources):
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "source_type_corrections": [
                {"email": "crew@morningbrew.com", "type": "news_brief"},
                {"email": "newsletters@stratechery.com", "type": "long_form"},
            ],
            "notes": "two corrections",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied"), \
             patch("pipeline.onboarding.update_source_type") as mock_update_type:
            mock_chain.invoke.return_value = fake_parsed
            process_onboarding_reply("evt_001", "corrections", "run_001")

        assert mock_update_type.call_count == 2

    def test_invalid_type_string_silently_skipped(self, active_sources):
        """A correction with an invalid type must be silently skipped — no crash, no DB call."""
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "source_type_corrections": [
                {"email": "crew@morningbrew.com", "type": "invalid_type"}
            ],
            "notes": "bad type",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied"), \
             patch("pipeline.onboarding.update_source_type") as mock_update_type:
            mock_chain.invoke.return_value = fake_parsed
            result = process_onboarding_reply("evt_001", "bad correction", "run_001")

        mock_update_type.assert_not_called()
        # Should complete without raising
        assert "applied_changes" in result

    def test_empty_type_string_silently_skipped(self, active_sources):
        """A correction with an empty type must be silently skipped."""
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "source_type_corrections": [
                {"email": "crew@morningbrew.com", "type": ""}
            ],
            "notes": "empty type",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied"), \
             patch("pipeline.onboarding.update_source_type") as mock_update_type:
            mock_chain.invoke.return_value = fake_parsed
            process_onboarding_reply("evt_001", "empty type", "run_001")

        mock_update_type.assert_not_called()

    def test_no_source_type_corrections_key_does_not_crash(self, active_sources):
        """When source_type_corrections is absent from parsed output, no crash occurs."""
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "topic_adjustments": {},
            "notes": "no corrections key",
        }
        with patch("pipeline.onboarding.get_active_sources", return_value=active_sources), \
             patch("pipeline.onboarding._parse_reply_chain") as mock_chain, \
             patch("pipeline.onboarding.update_source_trust_weight"), \
             patch("pipeline.onboarding.deprioritize_source"), \
             patch("pipeline.onboarding.get_config", return_value={}), \
             patch("pipeline.onboarding.set_config"), \
             patch("pipeline.onboarding.mark_onboarding_applied"), \
             patch("pipeline.onboarding.update_source_type") as mock_update_type:
            mock_chain.invoke.return_value = fake_parsed
            result = process_onboarding_reply("evt_001", "no corrections", "run_001")

        mock_update_type.assert_not_called()
        assert "applied_changes" in result


# ---------------------------------------------------------------------------
# run_onboarding — user_id parameter (per-user onboarding flag)
# ---------------------------------------------------------------------------

class TestRunOnboardingUserIdFlag:
    """When user_id is provided, per-user flag takes precedence over global flag."""

    def test_user_already_onboarded_returns_already_complete(self):
        """If user.onboarding_complete is True, skip regardless of global flag."""
        with (
            patch("pipeline.onboarding.get_user_by_id", return_value={"onboarding_complete": True}),
            patch("pipeline.onboarding.get_config", return_value=False),  # global flag is False
            patch("pipeline.onboarding.GmailService") as mock_svc,
        ):
            result = run_onboarding(run_id="test-run", user_id="user-uuid-1")

        assert result["status"] == "already_complete"
        mock_svc.assert_not_called()

    def test_user_not_yet_onboarded_proceeds_despite_global_flag_true(self):
        """If user.onboarding_complete is False, proceed even when global flag is True."""
        with (
            patch("pipeline.onboarding.get_user_by_id", return_value={"onboarding_complete": False}),
            patch("pipeline.onboarding.get_config", return_value=True),  # global flag says complete
            patch("pipeline.onboarding.get_pending_onboarding_event", return_value=None),
            patch("pipeline.onboarding.GmailService") as mock_svc,
            patch("pipeline.onboarding.source_classifier") as mock_classifier,
            patch("pipeline.onboarding.get_active_sources", return_value=[]),
            patch("pipeline.onboarding.create_onboarding_event", return_value="evt-001"),
            patch("pipeline.onboarding.update_onboarding_thread"),
        ):
            classifier_result = MagicMock()
            classifier_result.is_newsletter = True
            classifier_result.source_type = "news_brief"
            classifier_result.sender_email = "axiosam@axios.com"
            classifier_result.sender_name = "Axios AM"
            mock_classifier.classify.return_value = classifier_result

            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = ["msg-001"]
            gmail.get_messages.return_value = [MagicMock(sender_email="axiosam@axios.com")]
            gmail.send_message.return_value = ("sent-id", "thread-id")
            mock_svc.return_value = gmail

            result = run_onboarding(run_id="test-run", user_id="user-uuid-1")

        # GmailService was created — pipeline proceeded
        mock_svc.assert_called_once()
        assert result["status"] in ("sent", "no_sources_found")

    def test_no_user_id_falls_back_to_global_flag(self):
        """Without user_id, global agent_config.onboarding_complete is used as guard."""
        with (
            patch("pipeline.onboarding.get_config", return_value=True),
            patch("pipeline.onboarding.get_user_by_id") as mock_get_user,
            patch("pipeline.onboarding.GmailService") as mock_svc,
        ):
            result = run_onboarding(run_id="test-run")  # no user_id

        mock_get_user.assert_not_called()
        assert result["status"] == "already_complete"
        mock_svc.assert_not_called()

    def test_user_id_provided_but_user_not_found_proceeds(self):
        """If get_user_by_id returns None (user deleted?), fall through to inbox scan."""
        with (
            patch("pipeline.onboarding.get_user_by_id", return_value=None),
            patch("pipeline.onboarding.get_pending_onboarding_event", return_value=None),
            patch("pipeline.onboarding.GmailService") as mock_svc,
            patch("pipeline.onboarding.source_classifier"),
            patch("pipeline.onboarding.get_active_sources", return_value=[]),
            patch("pipeline.onboarding.create_onboarding_event", return_value="evt-001"),
            patch("pipeline.onboarding.update_onboarding_thread"),
        ):
            gmail = MagicMock()
            gmail.list_inbox_messages.return_value = []
            gmail.get_messages.return_value = []
            gmail.send_message.return_value = ("sent-id", "thread-id")
            mock_svc.return_value = gmail

            result = run_onboarding(run_id="test-run", user_id="unknown-uuid")

        # GmailService was created — pipeline proceeded
        mock_svc.assert_called_once()


# ---------------------------------------------------------------------------
# process_onboarding_reply — marks users onboarding complete
# ---------------------------------------------------------------------------

class TestProcessOnboardingReplyMarksUsersComplete:
    """After a reply is processed, mark_users_onboarding_complete() is called."""

    def test_mark_users_onboarding_complete_called_on_success(self, active_sources):
        fake_parsed = {
            "important_sources": [],
            "deprioritize_sources": [],
            "unsubscribe_sources": [],
            "source_type_corrections": [],
            "topic_adjustments": {},
            "notes": "",
        }
        with (
            patch("pipeline.onboarding.get_active_sources", return_value=active_sources),
            patch("pipeline.onboarding._parse_reply_chain") as mock_chain,
            patch("pipeline.onboarding.update_source_trust_weight"),
            patch("pipeline.onboarding.deprioritize_source"),
            patch("pipeline.onboarding.get_config", return_value={}),
            patch("pipeline.onboarding.set_config"),
            patch("pipeline.onboarding.mark_onboarding_applied"),
            patch("pipeline.onboarding.update_source_type"),
            patch("pipeline.onboarding.mark_users_onboarding_complete") as mock_mark,
        ):
            mock_chain.invoke.return_value = fake_parsed
            process_onboarding_reply("evt_001", "looks good", "run_001")

        mock_mark.assert_called_once()

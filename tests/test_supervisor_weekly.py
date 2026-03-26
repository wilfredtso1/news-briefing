"""
Tests for supervisor/weekly.py — weekly pattern sweep.

Testing strategy:
- All LLM calls mocked by patching _analyze_chain
- All DB helpers mocked via unittest.mock.patch
- GmailService mocked for send_email_node
- Tests cover the full graph via run_weekly_supervisor and individual nodes

Key scenarios:
  - Happy path: data gathered → analysis → low-risk change applied → email sent
  - No data this week: empty stats + feedback → safe email with "no data" message
  - LLM analysis failure: graceful degradation, email still sent with error note
  - Low-risk key NOT in LOW_RISK_CONFIG_KEYS: silently skipped, not applied
  - DB failure during gather_data: non-fatal, empty lists used
  - DB failure during apply_changes: per-change error logged, others continue
  - Email send failure: raises (not silently swallowed)
  - mark_source_unsubscribed NOT called by weekly supervisor (that's unsubscribe.py's job)
  - _format_digest_summary: empty list, single entry, multiple entries with ack mix
  - _format_feedback_summary: empty list, events with/without applied flag
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides) -> dict:
    defaults = {
        "run_id": "run-weekly-test",
        "feedback_events": [],
        "digest_stats": [],
        "observations": [],
        "low_risk_changes": [],
        "high_risk_proposals": [],
        "changes_applied": {},
        "email_body": "",
        "email_sent": False,
        "action_taken": "",
    }
    return {**defaults, **overrides}


def _make_digest(dtype="daily_brief", acked=True, word_count=2500):
    from datetime import datetime, timezone
    return {
        "id": "digest-001",
        "type": dtype,
        "sent_at": datetime(2026, 3, 24, 8, 0, tzinfo=timezone.utc),
        "acknowledged_at": datetime(2026, 3, 24, 9, 0, tzinfo=timezone.utc) if acked else None,
        "word_count": word_count,
        "story_count": 12,
    }


def _make_feedback(raw_reply="less crypto", applied=True):
    return {
        "id": "event-001",
        "digest_id": "digest-001",
        "raw_reply": raw_reply,
        "supervisor_interpretation": "user wants less crypto coverage",
        "proposed_change": '{"key": "topic_weights", "value": {"crypto": 0.2}}',
        "applied": applied,
        "applied_at": "2026-03-24T09:01:00Z" if applied else None,
    }


# ---------------------------------------------------------------------------
# Full graph: run_weekly_supervisor
# ---------------------------------------------------------------------------


class TestRunWeeklySupervisor:
    def test_happy_path_applies_low_risk_change_and_sends_email(self):
        """Full pipeline: gather → analyze → apply one low-risk change → send email."""
        digest = _make_digest()
        feedback = _make_feedback()

        with (
            patch("supervisor.weekly.get_weekly_digest_stats", return_value=[digest]),
            patch("supervisor.weekly.get_recent_feedback", return_value=[feedback]),
            patch("supervisor.weekly._analyze_chain") as mock_chain,
            patch("supervisor.weekly.set_config") as mock_set,
            patch("supervisor.weekly.insert_feedback_event", return_value="event-log-1"),
            patch("supervisor.weekly.mark_feedback_applied"),
            patch("gmail_service.GmailService") as mock_gmail_cls,
        ):
            mock_chain.invoke.return_value = {
                "observations": ["1 of 1 digests acknowledged this week"],
                "low_risk_changes": [
                    {"key": "topic_weights", "value": {"crypto": 0.2}, "reason": "user said less crypto"}
                ],
                "high_risk_proposals": [],
            }
            mock_gmail_cls.return_value = MagicMock()

            from supervisor.weekly import run_weekly_supervisor
            result = run_weekly_supervisor("run-1")

        mock_set.assert_called_once_with("topic_weights", {"crypto": 0.2}, updated_by="supervisor")
        mock_gmail_cls.return_value.send_message.assert_called_once()
        assert result.email_sent is True
        assert result.changes_applied == {"topic_weights": {"crypto": 0.2}}
        assert "email" in result.action_taken

    def test_no_data_still_sends_email(self):
        """Empty week: no digests, no feedback → analysis returns minimal observations, email sent."""
        with (
            patch("supervisor.weekly.get_weekly_digest_stats", return_value=[]),
            patch("supervisor.weekly.get_recent_feedback", return_value=[]),
            patch("supervisor.weekly._analyze_chain") as mock_chain,
            patch("supervisor.weekly.set_config") as mock_set,
            patch("gmail_service.GmailService") as mock_gmail_cls,
        ):
            mock_chain.invoke.return_value = {
                "observations": ["Insufficient data — fewer than 3 digests sent this week"],
                "low_risk_changes": [],
                "high_risk_proposals": [],
            }
            mock_gmail_cls.return_value = MagicMock()

            from supervisor.weekly import run_weekly_supervisor
            result = run_weekly_supervisor("run-2")

        mock_set.assert_not_called()
        mock_gmail_cls.return_value.send_message.assert_called_once()
        assert result.email_sent is True
        assert result.changes_applied == {}

    def test_llm_failure_still_sends_email_with_error_note(self):
        """LLM analysis failure is non-fatal — email is sent with error observation."""
        with (
            patch("supervisor.weekly.get_weekly_digest_stats", return_value=[_make_digest()]),
            patch("supervisor.weekly.get_recent_feedback", return_value=[]),
            patch("supervisor.weekly._analyze_chain") as mock_chain,
            patch("supervisor.weekly.set_config") as mock_set,
            patch("gmail_service.GmailService") as mock_gmail_cls,
        ):
            mock_chain.invoke.side_effect = Exception("Opus API error")
            mock_gmail_cls.return_value = MagicMock()

            from supervisor.weekly import run_weekly_supervisor
            result = run_weekly_supervisor("run-3")

        mock_set.assert_not_called()
        mock_gmail_cls.return_value.send_message.assert_called_once()
        # Email body should mention the failure — send_message uses keyword args only
        call_kwargs = mock_gmail_cls.return_value.send_message.call_args
        body = call_kwargs.kwargs.get("body", "")
        assert "failed" in body.lower() or "error" in body.lower()
        assert result.email_sent is True

    def test_email_send_failure_raises(self):
        """Gmail send failure propagates — not silently swallowed."""
        with (
            patch("supervisor.weekly.get_weekly_digest_stats", return_value=[]),
            patch("supervisor.weekly.get_recent_feedback", return_value=[]),
            patch("supervisor.weekly._analyze_chain") as mock_chain,
            patch("gmail_service.GmailService") as mock_gmail_cls,
        ):
            mock_chain.invoke.return_value = {
                "observations": [],
                "low_risk_changes": [],
                "high_risk_proposals": [],
            }
            mock_gmail_cls.return_value.send_message.side_effect = Exception("Gmail API down")

            from supervisor.weekly import run_weekly_supervisor
            with pytest.raises(Exception, match="Gmail API down"):
                run_weekly_supervisor("run-4")

    def test_db_gather_failure_is_non_fatal(self):
        """DB read errors during gather_data produce empty lists — analysis still runs."""
        with (
            patch("supervisor.weekly.get_weekly_digest_stats", side_effect=Exception("DB error")),
            patch("supervisor.weekly.get_recent_feedback", side_effect=Exception("DB error")),
            patch("supervisor.weekly._analyze_chain") as mock_chain,
            patch("gmail_service.GmailService") as mock_gmail_cls,
        ):
            mock_chain.invoke.return_value = {
                "observations": ["Insufficient data"],
                "low_risk_changes": [],
                "high_risk_proposals": [],
            }
            mock_gmail_cls.return_value = MagicMock()

            from supervisor.weekly import run_weekly_supervisor
            result = run_weekly_supervisor("run-5")

        # Analysis was called with empty data — LLM should note insufficient data
        assert result.email_sent is True


# ---------------------------------------------------------------------------
# Node unit tests
# ---------------------------------------------------------------------------


class TestApplyChangesNode:
    def test_applies_low_risk_key_and_logs_feedback_event(self):
        from supervisor.weekly import apply_changes_node
        state = _make_state(low_risk_changes=[
            {"key": "topic_weights", "value": {"ai": 1.5}, "reason": "user likes AI"}
        ])
        with (
            patch("supervisor.weekly.set_config") as mock_set,
            patch("supervisor.weekly.insert_feedback_event", return_value="evt-1"),
            patch("supervisor.weekly.mark_feedback_applied") as mock_mark,
        ):
            result = apply_changes_node(state)

        mock_set.assert_called_once_with("topic_weights", {"ai": 1.5}, updated_by="supervisor")
        mock_mark.assert_called_once_with("evt-1")
        assert result["changes_applied"] == {"topic_weights": {"ai": 1.5}}

    def test_silently_skips_unsafe_config_key(self):
        """Keys not in LOW_RISK_CONFIG_KEYS must not be applied, even if LLM returned them."""
        from supervisor.weekly import apply_changes_node
        state = _make_state(low_risk_changes=[
            {"key": "prompt_edit", "value": "rewrite everything", "reason": "bad idea"}
        ])
        with (
            patch("supervisor.weekly.set_config") as mock_set,
            patch("supervisor.weekly.insert_feedback_event"),
            patch("supervisor.weekly.mark_feedback_applied"),
        ):
            result = apply_changes_node(state)

        mock_set.assert_not_called()
        assert result["changes_applied"] == {}

    def test_continues_after_single_change_failure(self):
        """A DB error on one change should not block subsequent changes."""
        from supervisor.weekly import apply_changes_node
        state = _make_state(low_risk_changes=[
            {"key": "topic_weights", "value": {"crypto": 0.1}, "reason": "first"},
            {"key": "word_budget", "value": {"daily_brief_total": 2000}, "reason": "second"},
        ])

        call_count = 0
        def flaky_set_config(key, value, updated_by):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("transient DB error")

        with (
            patch("supervisor.weekly.set_config", side_effect=flaky_set_config),
            patch("supervisor.weekly.insert_feedback_event", return_value="evt-2"),
            patch("supervisor.weekly.mark_feedback_applied"),
        ):
            result = apply_changes_node(state)

        # Second change should still be applied
        assert "word_budget" in result["changes_applied"]
        assert "topic_weights" not in result["changes_applied"]


class TestComposeEmailNode:
    def test_email_includes_all_sections(self):
        from supervisor.weekly import compose_email_node
        state = _make_state(
            changes_applied={"topic_weights": {"crypto": 0.2}},
            observations=["You read 4 of 5 daily briefs this week"],
            high_risk_proposals=[{"description": "Shorten synthesis prompts", "reason": "digests too long"}],
        )
        result = compose_email_node(state)
        body = result["email_body"]
        assert "WEEKLY DIGEST REVIEW" in body
        assert "CHANGES APPLIED" in body
        assert "topic_weights" in body
        assert "OBSERVATIONS" in body
        assert "4 of 5" in body
        assert "PROPOSED CHANGES" in body
        assert "Shorten synthesis prompts" in body

    def test_email_no_changes_section_shows_none(self):
        from supervisor.weekly import compose_email_node
        state = _make_state(changes_applied={}, observations=[], high_risk_proposals=[])
        result = compose_email_node(state)
        body = result["email_body"]
        assert "No config changes" in body
        assert "No notable patterns" in body
        # No proposed changes section when empty
        assert "PROPOSED CHANGES" not in body

    def test_email_body_is_never_empty(self):
        from supervisor.weekly import compose_email_node
        result = compose_email_node(_make_state())
        assert len(result["email_body"]) > 50


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestFormatDigestSummary:
    def test_empty_list_returns_no_digests_message(self):
        from supervisor.weekly import _format_digest_summary
        result = _format_digest_summary([])
        assert "No digests" in result

    def test_counts_acked_and_total(self):
        from supervisor.weekly import _format_digest_summary
        digests = [_make_digest(acked=True), _make_digest(acked=False), _make_digest(acked=True)]
        result = _format_digest_summary(digests)
        assert "2/3" in result or "Acknowledged: 2" in result

    def test_includes_type_breakdown(self):
        from supervisor.weekly import _format_digest_summary
        digests = [_make_digest("daily_brief"), _make_digest("weekend_catchup")]
        result = _format_digest_summary(digests)
        assert "daily_brief" in result
        assert "weekend_catchup" in result


class TestFormatFeedbackSummary:
    def test_empty_list_returns_no_feedback_message(self):
        from supervisor.weekly import _format_feedback_summary
        result = _format_feedback_summary([])
        assert "No feedback" in result

    def test_includes_reply_and_interpretation(self):
        from supervisor.weekly import _format_feedback_summary
        events = [_make_feedback(raw_reply="less crypto please")]
        result = _format_feedback_summary(events)
        assert "less crypto" in result

    def test_shows_applied_vs_pending_status(self):
        from supervisor.weekly import _format_feedback_summary
        events = [_make_feedback(applied=True), _make_feedback(applied=False)]
        result = _format_feedback_summary(events)
        assert "applied" in result
        assert "pending" in result or "queued" in result


# ---------------------------------------------------------------------------
# Tests: Branch C expansions — LOW_RISK_CONFIG_KEYS new entries (weekly)
# ---------------------------------------------------------------------------


class TestWeeklyLowRiskConfigKeysExpanded:
    """Guard the new low-risk keys in the weekly supervisor."""

    def test_synthesis_style_notes_in_low_risk_keys(self):
        from supervisor.weekly import LOW_RISK_CONFIG_KEYS
        assert "synthesis_style_notes" in LOW_RISK_CONFIG_KEYS

    def test_web_search_topics_in_low_risk_keys(self):
        from supervisor.weekly import LOW_RISK_CONFIG_KEYS
        assert "web_search_topics" in LOW_RISK_CONFIG_KEYS

    def test_original_keys_still_present(self):
        from supervisor.weekly import LOW_RISK_CONFIG_KEYS
        assert "topic_weights" in LOW_RISK_CONFIG_KEYS
        assert "word_budget" in LOW_RISK_CONFIG_KEYS
        assert "cosine_similarity_threshold" in LOW_RISK_CONFIG_KEYS


# ---------------------------------------------------------------------------
# Tests: synthesis_style_notes applied via apply_changes_node (weekly)
# ---------------------------------------------------------------------------


class TestWeeklySynthesisStyleNotesApplied:
    """synthesis_style_notes can be applied by the weekly supervisor via apply_changes_node."""

    def test_synthesis_style_notes_applied_by_apply_changes_node(self):
        """synthesis_style_notes change in low_risk_changes → set_config called."""
        from supervisor.weekly import apply_changes_node
        state = _make_state(low_risk_changes=[
            {"key": "synthesis_style_notes", "value": ["write shorter stories"], "reason": "user wants brevity"}
        ])
        with (
            patch("supervisor.weekly.set_config") as mock_set,
            patch("supervisor.weekly.insert_feedback_event", return_value="evt-wk-sn-1"),
            patch("supervisor.weekly.mark_feedback_applied"),
        ):
            result = apply_changes_node(state)

        mock_set.assert_called_once_with(
            "synthesis_style_notes",
            ["write shorter stories"],
            updated_by="supervisor",
        )
        assert result["changes_applied"] == {"synthesis_style_notes": ["write shorter stories"]}

    def test_web_search_topics_applied_by_apply_changes_node(self):
        """web_search_topics change in low_risk_changes → set_config called."""
        from supervisor.weekly import apply_changes_node
        state = _make_state(low_risk_changes=[
            {"key": "web_search_topics", "value": ["markets", "sports"], "reason": "expand coverage"}
        ])
        with (
            patch("supervisor.weekly.set_config") as mock_set,
            patch("supervisor.weekly.insert_feedback_event", return_value="evt-wk-wst-1"),
            patch("supervisor.weekly.mark_feedback_applied"),
        ):
            result = apply_changes_node(state)

        mock_set.assert_called_once_with(
            "web_search_topics",
            ["markets", "sports"],
            updated_by="supervisor",
        )
        assert result["changes_applied"] == {"web_search_topics": ["markets", "sports"]}

    def test_synthesis_style_notes_in_full_weekly_run(self):
        """Full weekly run: synthesis_style_notes in analysis output → applied, in changes_applied."""
        with (
            patch("supervisor.weekly.get_weekly_digest_stats", return_value=[_make_digest()]),
            patch("supervisor.weekly.get_recent_feedback", return_value=[]),
            patch("supervisor.weekly._analyze_chain") as mock_chain,
            patch("supervisor.weekly.set_config") as mock_set,
            patch("supervisor.weekly.insert_feedback_event", return_value="evt-wk-full-1"),
            patch("supervisor.weekly.mark_feedback_applied"),
            patch("gmail_service.GmailService") as mock_gmail_cls,
        ):
            mock_chain.invoke.return_value = {
                "observations": ["User wants shorter stories"],
                "low_risk_changes": [
                    {
                        "key": "synthesis_style_notes",
                        "value": ["write shorter stories"],
                        "reason": "user requested brevity",
                    }
                ],
                "high_risk_proposals": [],
            }
            mock_gmail_cls.return_value = MagicMock()

            from supervisor.weekly import run_weekly_supervisor
            result = run_weekly_supervisor("run-weekly-style")

        mock_set.assert_called_once_with(
            "synthesis_style_notes",
            ["write shorter stories"],
            updated_by="supervisor",
        )
        assert result.changes_applied == {"synthesis_style_notes": ["write shorter stories"]}

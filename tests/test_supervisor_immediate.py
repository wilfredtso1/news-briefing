"""
Tests for supervisor/immediate.py — immediate supervisor mode.

Testing strategy:
- All LLM calls mocked via patching _classify_chain and _extract_chain
- All DB helpers mocked via unittest.mock.patch
- Tests cover both the full graph (via run_immediate_supervisor) and individual nodes
- Coverage target: >90% of supervisor logic

Key scenarios covered:
  - acknowledge → mark digest acknowledged, no config change
  - feedback (low-risk) → extract + validate + apply immediately
  - feedback (high-risk) → extract + validate + queue, never apply
  - both → acknowledge AND process the feedback
  - irrelevant → no action, no DB writes
  - LLM classify failure → defaults to irrelevant (safe)
  - LLM extraction failure → defaults to unknown key, no action
  - Unknown config key → risk_level=none, no action (not queued either)
  - DB apply failure → raises (not silently swallowed)
  - DB acknowledge failure → non-fatal warning, graph continues
  - DB log failure → non-fatal warning, config change already applied
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Shared state builder — avoids repeating all TypedDict fields in every test
# ---------------------------------------------------------------------------

def _make_state(**overrides) -> dict:
    defaults = {
        "digest_id": "digest-uuid-1234",
        "raw_reply": "some reply",
        "thread_id": "thread-5678",
        "reply_type": "",
        "proposed_key": "",
        "proposed_value": None,
        "risk_level": "none",
        "extraction_reasoning": "",
        "command_target": "",
        "config_delta": {},
        "queued_items": [],
        "action_taken": "",
        "event_id": "",
        "command_triggered": "",
    }
    return {**defaults, **overrides}


# ---------------------------------------------------------------------------
# End-to-end tests: run_immediate_supervisor
# ---------------------------------------------------------------------------


class TestRunImmediateSupervisor:
    """Full graph tests via run_immediate_supervisor with mocked LLM + DB."""

    def test_acknowledge_marks_digest_and_returns_no_config_change(self):
        """Pure acknowledgment: mark digest acknowledged, no config change, no feedback log."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
        ):
            mock_classify.invoke.return_value = {"reply_type": "acknowledge"}

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "thanks!", "thread-1")

        mock_ack.assert_called_once_with("digest-1")
        mock_set.assert_not_called()
        mock_insert.assert_not_called()
        assert result.reply_type == "acknowledge"
        assert result.config_delta == {}
        assert result.queued_items == []
        assert "acknowledged" in result.action_taken

    def test_low_risk_feedback_applies_config_and_logs_event(self):
        """Low-risk feedback: apply config change immediately, log feedback event as applied."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
            patch("supervisor.immediate.mark_feedback_applied") as mock_mark,
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "topic_weights",
                "value": {"crypto": 0.1},
                "reasoning": "user wants less crypto",
            }
            mock_insert.return_value = "event-001"

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "less crypto please", "thread-1")

        mock_ack.assert_not_called()
        mock_set.assert_called_once_with("topic_weights", {"crypto": 0.1}, updated_by="supervisor")
        mock_insert.assert_called_once()
        mock_mark.assert_called_once_with("event-001")
        assert result.config_delta == {"topic_weights": {"crypto": 0.1}}
        assert result.queued_items == []
        assert result.reply_type == "feedback"

    def test_high_risk_feedback_queues_not_applies(self):
        """High-risk feedback: queue in feedback_events, never call set_config."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
            patch("supervisor.immediate.mark_feedback_applied") as mock_mark,
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "prompt_edit",
                "value": "make it more casual",
                "reasoning": "style change",
            }
            mock_insert.return_value = "event-002"

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "more casual tone", "thread-1")

        mock_set.assert_not_called()
        mock_mark.assert_not_called()
        mock_insert.assert_called_once()
        assert result.config_delta == {}
        assert result.queued_items == ["event-002"]
        assert "queued" in result.action_taken

    def test_both_acknowledges_and_applies_feedback(self):
        """'both' reply: acknowledge digest AND apply the feedback config change."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
            patch("supervisor.immediate.mark_feedback_applied") as mock_mark,
        ):
            mock_classify.invoke.return_value = {"reply_type": "both"}
            mock_extract.invoke.return_value = {
                "key": "topic_weights",
                "value": {"ai": 2.0},
                "reasoning": "more AI coverage",
            }
            mock_insert.return_value = "event-003"

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "got it, more AI please", "thread-1")

        mock_ack.assert_called_once_with("digest-1")
        mock_set.assert_called_once_with("topic_weights", {"ai": 2.0}, updated_by="supervisor")
        assert result.reply_type == "both"
        assert result.config_delta == {"topic_weights": {"ai": 2.0}}
        assert "acknowledged" in result.action_taken

    def test_irrelevant_reply_takes_no_action(self):
        """Irrelevant reply: no DB writes, no config changes."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
        ):
            mock_classify.invoke.return_value = {"reply_type": "irrelevant"}

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "OOO auto-reply", "thread-1")

        mock_ack.assert_not_called()
        mock_set.assert_not_called()
        mock_insert.assert_not_called()
        assert result.reply_type == "irrelevant"
        assert result.config_delta == {}
        assert result.queued_items == []

    def test_unknown_config_key_takes_no_action(self):
        """Unknown key from extractor: risk=none → no apply, no queue."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "unknown",
                "value": None,
                "reasoning": "could not parse intent",
            }

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "some vague message", "thread-1")

        mock_set.assert_not_called()
        mock_insert.assert_not_called()
        assert result.config_delta == {}
        assert result.queued_items == []

    def test_classify_llm_failure_defaults_to_irrelevant(self):
        """LLM classification failure should safely default to irrelevant — no crash."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
            patch("supervisor.immediate.set_config") as mock_set,
        ):
            mock_classify.invoke.side_effect = RuntimeError("API timeout")

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "some reply", "thread-1")

        assert result.reply_type == "irrelevant"
        mock_ack.assert_not_called()
        mock_set.assert_not_called()

    def test_acknowledge_db_failure_is_non_fatal(self):
        """mark_digest_acknowledged failure should be logged as warning, not crash the graph."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
        ):
            mock_classify.invoke.return_value = {"reply_type": "acknowledge"}
            mock_ack.side_effect = Exception("DB connection error")

            from supervisor.immediate import run_immediate_supervisor
            # Should not raise
            result = run_immediate_supervisor("digest-1", "thanks!", "thread-1")

        assert result.reply_type == "acknowledge"

    def test_apply_change_db_failure_raises(self):
        """set_config failure should propagate — silent config failure is worse than a crash."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "topic_weights",
                "value": {"ai": 1.8},
                "reasoning": "more AI",
            }
            mock_set.side_effect = Exception("DB write failed")

            from supervisor.immediate import run_immediate_supervisor
            with pytest.raises(Exception, match="DB write failed"):
                run_immediate_supervisor("digest-1", "more AI please", "thread-1")

    def test_extraction_failure_treats_as_unknown_key(self):
        """Extract chain failure defaults to unknown key → risk=none → no action."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.side_effect = RuntimeError("JSON parse error")

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "change stuff", "thread-1")

        mock_set.assert_not_called()
        mock_insert.assert_not_called()
        assert result.config_delta == {}

    def test_classify_unexpected_type_normalised_to_irrelevant(self):
        """LLM returning an unrecognised reply_type is normalised to irrelevant."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
        ):
            mock_classify.invoke.return_value = {"reply_type": "HACK_THE_PLANET"}

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "some reply", "thread-1")

        assert result.reply_type == "irrelevant"
        mock_ack.assert_not_called()

    def test_result_is_supervisor_result_dataclass(self):
        """run_immediate_supervisor always returns a SupervisorResult with all fields."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate.mark_digest_acknowledged"),
        ):
            mock_classify.invoke.return_value = {"reply_type": "acknowledge"}

            from supervisor.immediate import run_immediate_supervisor, SupervisorResult
            result = run_immediate_supervisor("digest-1", "thanks!", "thread-1")

        assert isinstance(result, SupervisorResult)
        assert isinstance(result.action_taken, str) and result.action_taken
        assert isinstance(result.config_delta, dict)
        assert isinstance(result.queued_items, list)
        assert isinstance(result.reply_type, str)

    def test_word_budget_change_is_low_risk(self):
        """word_budget is a low-risk key and should be applied immediately."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
            patch("supervisor.immediate.mark_feedback_applied"),
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "word_budget",
                "value": {"daily_brief_total": 2000},
                "reasoning": "shorter digest",
            }
            mock_insert.return_value = "event-004"

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "shorter please", "thread-1")

        mock_set.assert_called_once_with(
            "word_budget", {"daily_brief_total": 2000}, updated_by="supervisor"
        )
        assert "word_budget" in result.config_delta

    def test_cosine_similarity_threshold_change_is_low_risk(self):
        """cosine_similarity_threshold is a low-risk key and should be applied immediately."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
            patch("supervisor.immediate.mark_feedback_applied"),
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "cosine_similarity_threshold",
                "value": 0.85,
                "reasoning": "stricter dedup",
            }
            mock_insert.return_value = "event-005"

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "too many duplicates", "thread-1")

        mock_set.assert_called_once_with(
            "cosine_similarity_threshold", 0.85, updated_by="supervisor"
        )
        assert result.config_delta.get("cosine_similarity_threshold") == 0.85

    def test_unsubscribe_is_high_risk(self):
        """unsubscribe key is high-risk: must be queued, never auto-applied."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
            patch("supervisor.immediate.mark_feedback_applied") as mock_mark,
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "unsubscribe",
                "value": "spam@newsletter.com",
                "reasoning": "user wants to unsubscribe",
            }
            mock_insert.return_value = "event-006"

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "unsubscribe from spam newsletter", "thread-1")

        mock_set.assert_not_called()
        mock_mark.assert_not_called()
        assert result.queued_items == ["event-006"]


# ---------------------------------------------------------------------------
# Unit tests: individual node functions
# ---------------------------------------------------------------------------


class TestClassifyReplyNode:
    """classify_reply_node in isolation."""

    def test_returns_correct_reply_type(self):
        with patch("supervisor.immediate._classify_chain") as mock_chain:
            mock_chain.invoke.return_value = {"reply_type": "feedback"}
            from supervisor.immediate import classify_reply_node
            result = classify_reply_node(_make_state())
        assert result["reply_type"] == "feedback"

    def test_llm_failure_defaults_to_irrelevant(self):
        with patch("supervisor.immediate._classify_chain") as mock_chain:
            mock_chain.invoke.side_effect = RuntimeError("network error")
            from supervisor.immediate import classify_reply_node
            result = classify_reply_node(_make_state())
        assert result["reply_type"] == "irrelevant"

    def test_unexpected_reply_type_normalised_to_irrelevant(self):
        with patch("supervisor.immediate._classify_chain") as mock_chain:
            mock_chain.invoke.return_value = {"reply_type": "INVALID_TYPE"}
            from supervisor.immediate import classify_reply_node
            result = classify_reply_node(_make_state())
        assert result["reply_type"] == "irrelevant"

    @pytest.mark.parametrize("reply_type", ["acknowledge", "feedback", "both", "irrelevant"])
    def test_all_valid_types_pass_through(self, reply_type):
        with patch("supervisor.immediate._classify_chain") as mock_chain:
            mock_chain.invoke.return_value = {"reply_type": reply_type}
            from supervisor.immediate import classify_reply_node
            result = classify_reply_node(_make_state())
        assert result["reply_type"] == reply_type


class TestMaybeAcknowledgeNode:
    """maybe_acknowledge_node in isolation."""

    def test_acknowledges_for_acknowledge_type(self):
        with patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack:
            from supervisor.immediate import maybe_acknowledge_node
            result = maybe_acknowledge_node(_make_state(digest_id="d1", reply_type="acknowledge"))
        mock_ack.assert_called_once_with("d1")
        assert "acknowledged" in result["action_taken"]

    def test_acknowledges_for_both_type(self):
        with patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack:
            from supervisor.immediate import maybe_acknowledge_node
            result = maybe_acknowledge_node(_make_state(digest_id="d1", reply_type="both"))
        mock_ack.assert_called_once_with("d1")

    def test_no_op_for_feedback_type(self):
        with patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack:
            from supervisor.immediate import maybe_acknowledge_node
            result = maybe_acknowledge_node(_make_state(reply_type="feedback"))
        mock_ack.assert_not_called()
        assert result["action_taken"] == ""

    def test_no_op_for_irrelevant_type(self):
        with patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack:
            from supervisor.immediate import maybe_acknowledge_node
            result = maybe_acknowledge_node(_make_state(reply_type="irrelevant"))
        mock_ack.assert_not_called()

    def test_db_failure_is_non_fatal(self):
        with patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack:
            mock_ack.side_effect = Exception("DB error")
            from supervisor.immediate import maybe_acknowledge_node
            # Should not raise
            result = maybe_acknowledge_node(_make_state(digest_id="d1", reply_type="acknowledge"))
        assert isinstance(result, dict)


class TestValidateChangeNode:
    """validate_change_node — pure logic, no mocks needed."""

    @pytest.mark.parametrize("key,expected_risk", [
        ("topic_weights", "low"),
        ("word_budget", "low"),
        ("cosine_similarity_threshold", "low"),
        ("prompt_edit", "high"),
        ("unsubscribe", "high"),
        ("source_change", "high"),
        ("unknown", "none"),
        ("some_new_key", "high"),  # Any unknown key not in LOW_RISK_CONFIG_KEYS is high
    ])
    def test_risk_classification(self, key, expected_risk):
        from supervisor.immediate import validate_change_node
        result = validate_change_node(_make_state(proposed_key=key))
        assert result["risk_level"] == expected_risk, (
            f"key={key!r} should be {expected_risk!r} risk, got {result['risk_level']!r}"
        )


class TestRouteAfterAcknowledge:
    """route_after_acknowledge routing function."""

    def test_feedback_routes_to_extract_change(self):
        from supervisor.immediate import route_after_acknowledge
        result = route_after_acknowledge(_make_state(reply_type="feedback"))
        assert result == "extract_change"

    def test_both_routes_to_extract_change(self):
        from supervisor.immediate import route_after_acknowledge
        result = route_after_acknowledge(_make_state(reply_type="both"))
        assert result == "extract_change"

    def test_acknowledge_routes_to_end(self):
        from langgraph.graph import END
        from supervisor.immediate import route_after_acknowledge
        result = route_after_acknowledge(_make_state(reply_type="acknowledge"))
        assert result == END

    def test_irrelevant_routes_to_no_op(self):
        from supervisor.immediate import route_after_acknowledge
        result = route_after_acknowledge(_make_state(reply_type="irrelevant"))
        assert result == "no_op"

    def test_command_routes_to_extract_command(self):
        from supervisor.immediate import route_after_acknowledge
        result = route_after_acknowledge(_make_state(reply_type="command"))
        assert result == "extract_command"


class TestRouteAfterValidate:
    """route_after_validate routing function."""

    def test_low_risk_routes_to_apply(self):
        from supervisor.immediate import route_after_validate
        assert route_after_validate(_make_state(risk_level="low")) == "apply_change"

    def test_high_risk_routes_to_queue(self):
        from supervisor.immediate import route_after_validate
        assert route_after_validate(_make_state(risk_level="high")) == "queue_change"

    def test_none_routes_to_no_op(self):
        from supervisor.immediate import route_after_validate
        assert route_after_validate(_make_state(risk_level="none")) == "no_op"


class TestApplyChangeNode:
    """apply_change_node in isolation."""

    def test_calls_set_config_and_updates_config_delta(self):
        with patch("supervisor.immediate.set_config") as mock_set:
            from supervisor.immediate import apply_change_node
            state = _make_state(
                proposed_key="topic_weights",
                proposed_value={"crypto": 0.2},
                extraction_reasoning="less crypto",
            )
            result = apply_change_node(state)

        mock_set.assert_called_once_with("topic_weights", {"crypto": 0.2}, updated_by="supervisor")
        assert result["config_delta"] == {"topic_weights": {"crypto": 0.2}}
        assert "applied" in result["action_taken"]
        assert "topic_weights" in result["action_taken"]

    def test_accumulates_into_existing_config_delta(self):
        """If config_delta already has entries, new key is added, not replaced."""
        with patch("supervisor.immediate.set_config"):
            from supervisor.immediate import apply_change_node
            state = _make_state(
                proposed_key="word_budget",
                proposed_value={"daily_brief_total": 2000},
                config_delta={"topic_weights": {"ai": 1.5}},
            )
            result = apply_change_node(state)

        assert "topic_weights" in result["config_delta"]
        assert "word_budget" in result["config_delta"]

    def test_db_failure_raises(self):
        with patch("supervisor.immediate.set_config") as mock_set:
            mock_set.side_effect = Exception("write failed")
            from supervisor.immediate import apply_change_node
            with pytest.raises(Exception, match="write failed"):
                apply_change_node(_make_state(proposed_key="topic_weights", proposed_value={}))


class TestQueueChangeNode:
    """queue_change_node in isolation."""

    def test_inserts_feedback_event_and_updates_queued_items(self):
        with patch("supervisor.immediate.insert_feedback_event") as mock_insert:
            mock_insert.return_value = "event-abc"
            from supervisor.immediate import queue_change_node
            state = _make_state(
                digest_id="d1",
                raw_reply="change tone",
                proposed_key="prompt_edit",
                proposed_value="casual",
                extraction_reasoning="style change",
            )
            result = queue_change_node(state)

        mock_insert.assert_called_once()
        assert result["queued_items"] == ["event-abc"]
        assert "queued" in result["action_taken"]
        assert result["event_id"] == "event-abc"

    def test_accumulates_into_existing_queued_items(self):
        with patch("supervisor.immediate.insert_feedback_event") as mock_insert:
            mock_insert.return_value = "event-new"
            from supervisor.immediate import queue_change_node
            state = _make_state(
                proposed_key="prompt_edit",
                proposed_value="formal",
                queued_items=["event-old"],
            )
            result = queue_change_node(state)

        assert "event-old" in result["queued_items"]
        assert "event-new" in result["queued_items"]

    def test_db_failure_raises(self):
        with patch("supervisor.immediate.insert_feedback_event") as mock_insert:
            mock_insert.side_effect = Exception("DB gone")
            from supervisor.immediate import queue_change_node
            with pytest.raises(Exception, match="DB gone"):
                queue_change_node(_make_state(proposed_key="prompt_edit"))

    def test_proposed_change_serialised_as_json(self):
        """The proposed_change field stored in DB should be valid JSON."""
        with patch("supervisor.immediate.insert_feedback_event") as mock_insert:
            mock_insert.return_value = "event-xyz"
            from supervisor.immediate import queue_change_node
            queue_change_node(_make_state(
                proposed_key="unsubscribe",
                proposed_value="spam@foo.com",
            ))

        call_kwargs = mock_insert.call_args.kwargs
        proposed_change_str = call_kwargs.get("proposed_change", "")
        parsed = json.loads(proposed_change_str)
        assert parsed["key"] == "unsubscribe"
        assert parsed["value"] == "spam@foo.com"


class TestLogFeedbackEventNode:
    """log_feedback_event_node in isolation."""

    def test_logs_and_marks_applied_for_low_risk_with_delta(self):
        with (
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
            patch("supervisor.immediate.mark_feedback_applied") as mock_mark,
        ):
            mock_insert.return_value = "event-log"
            from supervisor.immediate import log_feedback_event_node
            state = _make_state(
                risk_level="low",
                config_delta={"topic_weights": {"ai": 1.5}},
                proposed_key="topic_weights",
                proposed_value={"ai": 1.5},
            )
            result = log_feedback_event_node(state)

        mock_insert.assert_called_once()
        mock_mark.assert_called_once_with("event-log")
        assert result["event_id"] == "event-log"

    def test_skips_for_high_risk(self):
        """High-risk events are already logged in queue_change_node."""
        with patch("supervisor.immediate.insert_feedback_event") as mock_insert:
            from supervisor.immediate import log_feedback_event_node
            log_feedback_event_node(_make_state(
                risk_level="high",
                config_delta={},
                queued_items=["event-queued"],
            ))
        mock_insert.assert_not_called()

    def test_skips_for_empty_config_delta(self):
        """If no config was actually changed (e.g. risk=low but apply failed), skip logging."""
        with patch("supervisor.immediate.insert_feedback_event") as mock_insert:
            from supervisor.immediate import log_feedback_event_node
            log_feedback_event_node(_make_state(risk_level="low", config_delta={}))
        mock_insert.assert_not_called()

    def test_db_failure_is_non_fatal(self):
        """Failure to log should not crash — config change already happened."""
        with (
            patch("supervisor.immediate.insert_feedback_event") as mock_insert,
        ):
            mock_insert.side_effect = Exception("DB gone")
            from supervisor.immediate import log_feedback_event_node
            # Should not raise
            result = log_feedback_event_node(_make_state(
                risk_level="low",
                config_delta={"topic_weights": {"ai": 1.5}},
            ))
        assert isinstance(result, dict)


class TestNoOpNode:
    """no_op_node in isolation."""

    def test_sets_action_taken_if_empty(self):
        from supervisor.immediate import no_op_node
        result = no_op_node(_make_state(reply_type="irrelevant", action_taken=""))
        assert "no action" in result["action_taken"]

    def test_preserves_existing_action_taken(self):
        from supervisor.immediate import no_op_node
        result = no_op_node(_make_state(action_taken="acknowledged digest"))
        assert result["action_taken"] == "acknowledged digest"


class TestExtractChangeNode:
    """extract_change_node in isolation."""

    def test_extracts_key_value_reasoning(self):
        with patch("supervisor.immediate._extract_chain") as mock_chain:
            mock_chain.invoke.return_value = {
                "key": "topic_weights",
                "value": {"sports": 0.1},
                "reasoning": "less sports",
            }
            from supervisor.immediate import extract_change_node
            result = extract_change_node(_make_state(raw_reply="less sports please"))

        assert result["proposed_key"] == "topic_weights"
        assert result["proposed_value"] == {"sports": 0.1}
        assert result["extraction_reasoning"] == "less sports"

    def test_failure_defaults_to_unknown_key(self):
        with patch("supervisor.immediate._extract_chain") as mock_chain:
            mock_chain.invoke.side_effect = RuntimeError("parse error")
            from supervisor.immediate import extract_change_node
            result = extract_change_node(_make_state())

        assert result["proposed_key"] == "unknown"
        assert result["proposed_value"] is None


# ---------------------------------------------------------------------------
# Tests: SupervisorResult dataclass
# ---------------------------------------------------------------------------


class TestSupervisorResult:
    """SupervisorResult dataclass contract."""

    def test_default_fields_are_empty(self):
        from supervisor.immediate import SupervisorResult
        result = SupervisorResult(action_taken="test")
        assert result.config_delta == {}
        assert result.queued_items == []
        assert result.reply_type == "irrelevant"
        assert result.command_triggered == ""

    def test_all_fields_settable(self):
        from supervisor.immediate import SupervisorResult
        result = SupervisorResult(
            action_taken="applied topic_weights",
            config_delta={"topic_weights": {"ai": 1.5}},
            queued_items=["event-001"],
            reply_type="feedback",
        )
        assert result.action_taken == "applied topic_weights"
        assert result.config_delta == {"topic_weights": {"ai": 1.5}}
        assert result.queued_items == ["event-001"]
        assert result.reply_type == "feedback"


# ---------------------------------------------------------------------------
# Tests: LOW_RISK_CONFIG_KEYS constant
# ---------------------------------------------------------------------------


class TestLowRiskConfigKeys:
    """Guard the risk boundary — any accidental change should break a test."""

    def test_expected_low_risk_keys_present(self):
        from supervisor.immediate import LOW_RISK_CONFIG_KEYS
        assert "topic_weights" in LOW_RISK_CONFIG_KEYS
        assert "word_budget" in LOW_RISK_CONFIG_KEYS
        assert "cosine_similarity_threshold" in LOW_RISK_CONFIG_KEYS

    def test_high_risk_keys_absent(self):
        from supervisor.immediate import LOW_RISK_CONFIG_KEYS
        assert "prompt_edit" not in LOW_RISK_CONFIG_KEYS
        assert "unsubscribe" not in LOW_RISK_CONFIG_KEYS
        assert "source_change" not in LOW_RISK_CONFIG_KEYS

    def test_unknown_absent(self):
        from supervisor.immediate import LOW_RISK_CONFIG_KEYS
        assert "unknown" not in LOW_RISK_CONFIG_KEYS


# ---------------------------------------------------------------------------
# Tests: package exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    """supervisor/__init__.py exports the correct symbols."""

    def test_imports_from_package(self):
        from supervisor import SupervisorResult, run_immediate_supervisor
        assert callable(run_immediate_supervisor)
        assert SupervisorResult is not None

    def test_supervisor_result_importable_directly(self):
        from supervisor.immediate import SupervisorResult
        r = SupervisorResult(action_taken="test")
        assert r.action_taken == "test"


# ---------------------------------------------------------------------------
# Tests: command reply type (full graph)
# ---------------------------------------------------------------------------


class TestCommandReplyType:
    """Full graph tests for on-demand pipeline trigger via 'command' reply type."""

    def test_command_reply_triggers_daily_brief(self):
        """'send brief' classified as command → daily_brief pipeline called."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_command_chain") as mock_extract,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            mock_classify.invoke.return_value = {"reply_type": "command"}
            mock_extract.invoke.return_value = {"pipeline": "daily_brief", "reasoning": "wants news"}

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "send brief", "thread-1")

        mock_ack.assert_not_called()
        mock_run.assert_called_once()
        assert result.reply_type == "command"
        assert result.command_triggered == "daily_brief"
        assert result.config_delta == {}
        assert result.queued_items == []

    def test_command_reply_triggers_deep_read(self):
        """'send me a deep read' classified as command → deep_read pipeline called with force=True."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_command_chain") as mock_extract,
            patch("supervisor.immediate.mark_digest_acknowledged") as mock_ack,
            patch("pipeline.deep_read.run_deep_read") as mock_run,
        ):
            mock_classify.invoke.return_value = {"reply_type": "command"}
            mock_extract.invoke.return_value = {"pipeline": "deep_read", "reasoning": "wants long-form"}

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "send me a deep read", "thread-1")

        mock_ack.assert_not_called()
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("force") is True
        assert result.reply_type == "command"
        assert result.command_triggered == "deep_read"

    def test_ambiguous_command_defaults_to_daily_brief(self):
        """Ambiguous 'send it' → extract_command defaults to daily_brief."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_command_chain") as mock_extract,
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            mock_classify.invoke.return_value = {"reply_type": "command"}
            # LLM returns unknown pipeline value — should be normalised to daily_brief
            mock_extract.invoke.return_value = {"pipeline": "unknown_pipeline", "reasoning": "unclear"}

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "send it", "thread-1")

        mock_run.assert_called_once()
        assert result.command_triggered == "daily_brief"

    def test_command_does_not_call_set_config(self):
        """Command replies must never touch agent_config."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_command_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("pipeline.daily_brief.run"),
        ):
            mock_classify.invoke.return_value = {"reply_type": "command"}
            mock_extract.invoke.return_value = {"pipeline": "daily_brief", "reasoning": "wants news"}

            from supervisor.immediate import run_immediate_supervisor
            run_immediate_supervisor("digest-1", "send brief please", "thread-1")

        mock_set.assert_not_called()

    def test_command_extract_failure_defaults_to_daily_brief(self):
        """LLM failure in extract_command_node → safe default of daily_brief, no raise."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_command_chain") as mock_extract,
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            mock_classify.invoke.return_value = {"reply_type": "command"}
            mock_extract.invoke.side_effect = RuntimeError("LLM timeout")

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "brief", "thread-1")

        # Should still trigger daily_brief (safe fallback) and not raise
        mock_run.assert_called_once()
        assert result.command_triggered == "daily_brief"


# ---------------------------------------------------------------------------
# Tests: extract_command_node and execute_command_node in isolation
# ---------------------------------------------------------------------------


class TestExtractCommandNode:
    """extract_command_node in isolation."""

    def test_extracts_daily_brief(self):
        with patch("supervisor.immediate._extract_command_chain") as mock_chain:
            mock_chain.invoke.return_value = {"pipeline": "daily_brief", "reasoning": "morning news"}
            from supervisor.immediate import extract_command_node
            result = extract_command_node(_make_state(raw_reply="send brief"))
        assert result["command_target"] == "daily_brief"

    def test_extracts_deep_read(self):
        with patch("supervisor.immediate._extract_command_chain") as mock_chain:
            mock_chain.invoke.return_value = {"pipeline": "deep_read", "reasoning": "long form"}
            from supervisor.immediate import extract_command_node
            result = extract_command_node(_make_state(raw_reply="deep read please"))
        assert result["command_target"] == "deep_read"

    def test_unexpected_pipeline_value_defaults_to_daily_brief(self):
        with patch("supervisor.immediate._extract_command_chain") as mock_chain:
            mock_chain.invoke.return_value = {"pipeline": "weekly_report"}
            from supervisor.immediate import extract_command_node
            result = extract_command_node(_make_state())
        assert result["command_target"] == "daily_brief"

    def test_llm_failure_defaults_to_daily_brief(self):
        with patch("supervisor.immediate._extract_command_chain") as mock_chain:
            mock_chain.invoke.side_effect = RuntimeError("API error")
            from supervisor.immediate import extract_command_node
            # Should not raise
            result = extract_command_node(_make_state())
        assert result["command_target"] == "daily_brief"


class TestExecuteCommandNode:
    """execute_command_node in isolation."""

    def test_calls_daily_brief_run_with_run_id(self):
        with patch("pipeline.daily_brief.run") as mock_run:
            from supervisor.immediate import execute_command_node
            result = execute_command_node(_make_state(command_target="daily_brief"))

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert "run_id" in call_kwargs
        assert result["command_triggered"] == "daily_brief"
        assert "triggered daily_brief" in result["action_taken"]

    def test_calls_deep_read_with_force_true(self):
        with patch("pipeline.deep_read.run_deep_read") as mock_run:
            from supervisor.immediate import execute_command_node
            result = execute_command_node(_make_state(command_target="deep_read"))

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("force") is True
        assert result["command_triggered"] == "deep_read"

    def test_pipeline_failure_does_not_raise(self):
        """execute_command_node must not propagate pipeline exceptions."""
        with patch("pipeline.daily_brief.run") as mock_run:
            mock_run.side_effect = Exception("pipeline crashed")
            from supervisor.immediate import execute_command_node
            # Should not raise
            result = execute_command_node(_make_state(command_target="daily_brief"))

        assert "command failed" in result["action_taken"]
        assert result["command_triggered"] == "daily_brief"

    def test_unknown_target_defaults_to_daily_brief(self):
        """Empty or missing command_target falls back to daily_brief."""
        with patch("pipeline.daily_brief.run") as mock_run:
            from supervisor.immediate import execute_command_node
            result = execute_command_node(_make_state(command_target=""))

        mock_run.assert_called_once()
        assert result["command_triggered"] == "daily_brief"


# ---------------------------------------------------------------------------
# Tests: Branch C expansions — LOW_RISK_CONFIG_KEYS new entries
# ---------------------------------------------------------------------------


class TestLowRiskConfigKeysExpanded:
    """Guard the new low-risk keys added in Branch C."""

    def test_synthesis_style_notes_in_low_risk_keys(self):
        from supervisor.immediate import LOW_RISK_CONFIG_KEYS
        assert "synthesis_style_notes" in LOW_RISK_CONFIG_KEYS

    def test_web_search_topics_in_low_risk_keys(self):
        from supervisor.immediate import LOW_RISK_CONFIG_KEYS
        assert "web_search_topics" in LOW_RISK_CONFIG_KEYS


# ---------------------------------------------------------------------------
# Tests: synthesis_style_notes and web_search_topics feedback flows
# ---------------------------------------------------------------------------


class TestSynthesisStyleNotesFeedback:
    """synthesis_style_notes feedback → set_config called, returned in config_delta."""

    def test_synthesis_style_notes_applied_immediately(self):
        """synthesis_style_notes is low-risk — applied immediately, returned in config_delta."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event", return_value="evt-sn-1"),
            patch("supervisor.immediate.mark_feedback_applied"),
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "synthesis_style_notes",
                "value": ["write shorter stories", "use bullet points"],
                "reasoning": "user wants shorter stories",
            }

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "write shorter stories please", "thread-1")

        mock_set.assert_called_once_with(
            "synthesis_style_notes",
            ["write shorter stories", "use bullet points"],
            updated_by="supervisor",
        )
        assert "synthesis_style_notes" in result.config_delta
        assert result.config_delta["synthesis_style_notes"] == ["write shorter stories", "use bullet points"]

    def test_synthesis_style_notes_validate_as_low_risk(self):
        """validate_change_node returns risk_level=low for synthesis_style_notes."""
        from supervisor.immediate import validate_change_node
        result = validate_change_node(_make_state(proposed_key="synthesis_style_notes"))
        assert result["risk_level"] == "low"


class TestWebSearchTopicsFeedback:
    """web_search_topics feedback → set_config called."""

    def test_web_search_topics_applied_immediately(self):
        """web_search_topics is low-risk — applied immediately."""
        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("supervisor.immediate._extract_chain") as mock_extract,
            patch("supervisor.immediate.set_config") as mock_set,
            patch("supervisor.immediate.insert_feedback_event", return_value="evt-wst-1"),
            patch("supervisor.immediate.mark_feedback_applied"),
        ):
            mock_classify.invoke.return_value = {"reply_type": "feedback"}
            mock_extract.invoke.return_value = {
                "key": "web_search_topics",
                "value": ["markets", "sports"],
                "reasoning": "user wants markets and sports coverage",
            }

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "add sports headlines", "thread-1")

        mock_set.assert_called_once_with(
            "web_search_topics",
            ["markets", "sports"],
            updated_by="supervisor",
        )
        assert "web_search_topics" in result.config_delta

    def test_web_search_topics_validate_as_low_risk(self):
        """validate_change_node returns risk_level=low for web_search_topics."""
        from supervisor.immediate import validate_change_node
        result = validate_change_node(_make_state(proposed_key="web_search_topics"))
        assert result["risk_level"] == "low"


# ---------------------------------------------------------------------------
# Tests: reclassify_source_node
# ---------------------------------------------------------------------------


class TestReclassifySourceNode:
    """reclassify_source_node in isolation."""

    def test_valid_reclassify_calls_update_source_type(self):
        """source_reclassify with valid type → update_source_type called, action_taken set."""
        # Use create=True because update_source_type is owned by Branch A and may not exist yet
        with (
            patch("tools.db.update_source_type", create=True) as mock_update,
            patch("supervisor.immediate.insert_feedback_event", return_value="evt-rc-1"),
            patch("supervisor.immediate.mark_feedback_applied"),
        ):
            from supervisor.immediate import reclassify_source_node
            state = _make_state(
                proposed_value={"email": "crew@morningbrew.com", "type": "news_brief"},
                raw_reply="include Morning Brew in daily brief",
            )
            result = reclassify_source_node(state)

        mock_update.assert_called_once_with("crew@morningbrew.com", "news_brief")
        assert result["action_taken"] == "reclassified crew@morningbrew.com as news_brief"

    def test_invalid_type_skips_db_call_no_raise(self):
        """source_reclassify with invalid type → no DB call, no raise, action_taken indicates skip."""
        # No DB call happens (returns early), so no patch needed for update_source_type
        from supervisor.immediate import reclassify_source_node
        state = _make_state(
            proposed_value={"email": "test@example.com", "type": "invalid_type"},
            raw_reply="move to daily brief",
        )
        result = reclassify_source_node(state)

        assert result["action_taken"] == "reclassify_skipped_invalid_type"
        # No exception raised

    def test_long_form_type_is_valid(self):
        """long_form is a valid type for source_reclassify."""
        with (
            patch("tools.db.update_source_type", create=True) as mock_update,
            patch("supervisor.immediate.insert_feedback_event", return_value="evt-rc-2"),
            patch("supervisor.immediate.mark_feedback_applied"),
        ):
            from supervisor.immediate import reclassify_source_node
            state = _make_state(
                proposed_value={"email": "test@long.com", "type": "long_form"},
                raw_reply="move to deep read",
            )
            result = reclassify_source_node(state)

        mock_update.assert_called_once_with("test@long.com", "long_form")
        assert "long_form" in result["action_taken"]

    def test_reclassify_routes_from_validate_change(self):
        """validate_change_node assigns risk_level=source for source_reclassify key."""
        from supervisor.immediate import validate_change_node
        result = validate_change_node(_make_state(proposed_key="source_reclassify"))
        assert result["risk_level"] == "source"

    def test_route_after_validate_source_goes_to_reclassify(self):
        """route_after_validate returns 'reclassify_source' for source risk level."""
        from supervisor.immediate import route_after_validate
        assert route_after_validate(_make_state(risk_level="source")) == "reclassify_source"


# ---------------------------------------------------------------------------
# Tests: unknown key + reply length → code_change trigger logic
# ---------------------------------------------------------------------------


class TestUnknownKeyCodeChangeTrigger:
    """Unknown key with long reply → code_change; with short reply → no action."""

    def test_unknown_key_short_reply_no_code_change(self):
        """Unknown key + reply ≤50 chars → risk_level=none, no code change triggered."""
        from supervisor.immediate import validate_change_node
        result = validate_change_node(_make_state(
            proposed_key="unknown",
            raw_reply="short",  # ≤50 chars
        ))
        assert result["risk_level"] == "none"

    def test_unknown_key_long_reply_triggers_code_change(self):
        """Unknown key + reply >50 chars → risk_level=code_change."""
        from supervisor.immediate import validate_change_node
        long_reply = "x" * 51  # definitely >50 chars
        result = validate_change_node(_make_state(
            proposed_key="unknown",
            raw_reply=long_reply,
        ))
        assert result["risk_level"] == "code_change"

    def test_unknown_key_exactly_50_chars_no_code_change(self):
        """Unknown key + reply exactly 50 chars → risk_level=none (boundary: >50 required)."""
        from supervisor.immediate import validate_change_node
        result = validate_change_node(_make_state(
            proposed_key="unknown",
            raw_reply="x" * 50,
        ))
        assert result["risk_level"] == "none"

    def test_route_after_validate_code_change_goes_to_trigger(self):
        """route_after_validate returns 'trigger_code_change' for code_change risk."""
        from supervisor.immediate import route_after_validate
        assert route_after_validate(_make_state(risk_level="code_change")) == "trigger_code_change"

    def test_validate_change_node_long_unknown_is_code_change(self):
        """Unknown key + long reply > 50 chars → risk_level=code_change, not none."""
        from supervisor.immediate import validate_change_node
        long_reply = "I want to completely restructure the briefing format with new sections and categories"
        result = validate_change_node(_make_state(
            proposed_key="unknown",
            raw_reply=long_reply,
        ))
        assert result["risk_level"] == "code_change", (
            f"Expected code_change risk for long unknown reply, got {result['risk_level']!r}"
        )

    def test_trigger_code_change_node_spawns_daemon_thread(self):
        """trigger_code_change_node spawns a daemon thread with run_code_change_agent."""
        from unittest.mock import MagicMock
        import sys
        import types

        mock_thread = MagicMock()
        mock_agent = MagicMock()

        # Inject a fake supervisor.code_change_agent module for the lazy import
        fake_module = types.ModuleType("supervisor.code_change_agent")
        fake_module.run_code_change_agent = mock_agent
        sys.modules["supervisor.code_change_agent"] = fake_module

        try:
            with patch("threading.Thread", return_value=mock_thread) as mock_thread_cls:
                from supervisor.immediate import trigger_code_change_node
                state = _make_state(raw_reply="x" * 100, digest_id="digest-code")
                result = trigger_code_change_node(state)
        finally:
            # Clean up the fake module
            sys.modules.pop("supervisor.code_change_agent", None)

        # A thread was created and started
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()
        assert result["action_taken"] == "triggered code_change_agent"
        # Verify it was a daemon thread
        call_kwargs = mock_thread_cls.call_args
        assert call_kwargs.kwargs.get("daemon") is True


# ---------------------------------------------------------------------------
# Tests: code_change_approval → approve_code_change_node
# ---------------------------------------------------------------------------


class TestCodeChangeApproval:
    """code_change_approval reply → git push subprocess called."""

    def test_code_change_approval_routes_to_approve(self):
        """route_after_acknowledge returns 'approve_code_change' for code_change_approval."""
        from supervisor.immediate import route_after_acknowledge
        assert route_after_acknowledge(_make_state(reply_type="code_change_approval")) == "approve_code_change"

    def test_approve_code_change_node_calls_git_push(self):
        """approve_code_change_node runs git push subprocess."""
        import subprocess

        mock_result = subprocess.CompletedProcess(
            args=["git", "push"],
            returncode=0,
            stdout="Everything up-to-date",
            stderr="",
        )

        with patch("subprocess.run", return_value=mock_result) as mock_sub:
            from supervisor.immediate import approve_code_change_node
            state = _make_state(digest_id="digest-approve")
            result = approve_code_change_node(state)

        mock_sub.assert_called_once()
        call_args = mock_sub.call_args
        assert call_args.args[0] == ["git", "push"]
        assert result["action_taken"] == "git push succeeded"

    def test_approve_code_change_node_handles_git_failure(self):
        """approve_code_change_node captures git push failure without raising."""
        import subprocess

        mock_result = subprocess.CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="Permission denied",
        )

        with patch("subprocess.run", return_value=mock_result):
            from supervisor.immediate import approve_code_change_node
            state = _make_state(digest_id="digest-approve-fail")
            result = approve_code_change_node(state)

        assert "git push failed" in result["action_taken"]
        assert "Permission denied" in result["action_taken"]

    def test_full_graph_code_change_approval_calls_git_push(self):
        """Full graph: code_change_approval reply type → approve_code_change_node runs git push."""
        import subprocess

        mock_result = subprocess.CompletedProcess(
            args=["git", "push"], returncode=0, stdout="", stderr=""
        )

        with (
            patch("supervisor.immediate._classify_chain") as mock_classify,
            patch("subprocess.run", return_value=mock_result) as mock_sub,
        ):
            mock_classify.invoke.return_value = {"reply_type": "code_change_approval"}

            from supervisor.immediate import run_immediate_supervisor
            result = run_immediate_supervisor("digest-1", "approved", "thread-1")

        mock_sub.assert_called_once()
        assert mock_sub.call_args.args[0] == ["git", "push"]
        assert result.reply_type == "code_change_approval"

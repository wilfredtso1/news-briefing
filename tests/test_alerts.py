"""
Tests for tools/alerts.py

Covers:
- send_alert sends correctly formatted email (pipeline name, run_id, error type, timestamp, traceback tail)
- send_alert skips silently when ALERT_EMAIL is not set
- send_alert catches and logs (does not re-raise) gmail_service.send_message() failures
- Email body is plain text only
- Traceback tail is capped at 500 chars
- Timestamp is ISO 8601 format
- _build_body includes all required fields
"""

from __future__ import annotations

import re
import traceback
from datetime import timezone
from unittest.mock import MagicMock, patch

import pytest

from tools.alerts import _build_body, send_alert


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_gmail_mock(raise_on_send: Exception | None = None) -> MagicMock:
    """Return a mock GmailService. If raise_on_send is set, send_message raises it."""
    mock = MagicMock()
    if raise_on_send is not None:
        mock.send_message.side_effect = raise_on_send
    return mock


def _sample_error() -> Exception:
    """Return a real Exception with a traceback attached via raise/catch."""
    try:
        raise RuntimeError("test pipeline failure")
    except RuntimeError as exc:
        return exc


# ---------------------------------------------------------------------------
# Tests: send_alert skips when ALERT_EMAIL not configured
# ---------------------------------------------------------------------------

class TestSendAlertNoRecipient:
    def test_returns_silently_when_alert_email_not_set(self, monkeypatch):
        """send_alert is a silent no-op when ALERT_EMAIL env var is absent."""
        monkeypatch.delenv("ALERT_EMAIL", raising=False)
        gmail = _make_gmail_mock()
        error = _sample_error()

        send_alert("daily_brief", error, "run-123", _gmail_service=gmail)

        gmail.send_message.assert_not_called()

    def test_returns_silently_when_alert_email_empty_string(self, monkeypatch):
        """send_alert is a silent no-op when ALERT_EMAIL is an empty string."""
        monkeypatch.setenv("ALERT_EMAIL", "")
        gmail = _make_gmail_mock()
        error = _sample_error()

        send_alert("daily_brief", error, "run-456", _gmail_service=gmail)

        gmail.send_message.assert_not_called()

    def test_does_not_raise_when_alert_email_not_set(self, monkeypatch):
        """send_alert never raises, even when ALERT_EMAIL is missing."""
        monkeypatch.delenv("ALERT_EMAIL", raising=False)
        error = _sample_error()

        # Should not raise anything
        send_alert("weekend_catchup", error, "run-789")


# ---------------------------------------------------------------------------
# Tests: send_alert calls gmail_service correctly
# ---------------------------------------------------------------------------

class TestSendAlertEmailDelivery:
    def test_send_message_called_with_correct_recipient(self, monkeypatch):
        """send_alert calls gmail_service.send_message with the ALERT_EMAIL recipient."""
        monkeypatch.setenv("ALERT_EMAIL", "admin@example.com")
        gmail = _make_gmail_mock()
        error = _sample_error()

        send_alert("daily_brief", error, "run-001", _gmail_service=gmail)

        gmail.send_message.assert_called_once()
        call_kwargs = gmail.send_message.call_args[1]
        assert call_kwargs["to"] == "admin@example.com"

    def test_send_message_called_with_pipeline_name_in_subject(self, monkeypatch):
        """Email subject includes the pipeline name."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock()
        error = _sample_error()

        send_alert("deep_read", error, "run-002", _gmail_service=gmail)

        call_kwargs = gmail.send_message.call_args[1]
        assert "deep_read" in call_kwargs["subject"]

    def test_send_message_called_with_plain_text_body(self, monkeypatch):
        """Email body is plain text — no HTML tags."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock()
        error = _sample_error()

        send_alert("daily_brief", error, "run-003", _gmail_service=gmail)

        call_kwargs = gmail.send_message.call_args[1]
        body = call_kwargs["body"]

        # No HTML tags in plain text body
        assert "<html" not in body.lower()
        assert "<body" not in body.lower()
        assert "<p>" not in body.lower()


# ---------------------------------------------------------------------------
# Tests: email body content
# ---------------------------------------------------------------------------

class TestSendAlertBodyContent:
    def test_body_includes_pipeline_name(self, monkeypatch):
        """Alert body contains the pipeline name."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock()
        error = _sample_error()

        send_alert("weekend_catchup", error, "run-010", _gmail_service=gmail)

        body = gmail.send_message.call_args[1]["body"]
        assert "weekend_catchup" in body

    def test_body_includes_run_id(self, monkeypatch):
        """Alert body contains the run_id."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock()
        error = _sample_error()
        run_id = "run-unique-xyz-456"

        send_alert("daily_brief", error, run_id, _gmail_service=gmail)

        body = gmail.send_message.call_args[1]["body"]
        assert run_id in body

    def test_body_includes_error_type(self, monkeypatch):
        """Alert body includes the exception class name."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock()
        error = _sample_error()  # RuntimeError

        send_alert("daily_brief", error, "run-011", _gmail_service=gmail)

        body = gmail.send_message.call_args[1]["body"]
        assert "RuntimeError" in body

    def test_body_includes_iso8601_timestamp(self, monkeypatch):
        """Alert body includes a UTC ISO 8601 timestamp."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock()
        error = _sample_error()

        send_alert("daily_brief", error, "run-012", _gmail_service=gmail)

        body = gmail.send_message.call_args[1]["body"]
        # ISO 8601 pattern: YYYY-MM-DDTHH:MM:SS...+00:00 or ...Z or ...-00:00
        iso_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        assert re.search(iso_pattern, body), f"No ISO 8601 timestamp found in body:\n{body}"


# ---------------------------------------------------------------------------
# Tests: traceback tail
# ---------------------------------------------------------------------------

class TestSendAlertTraceback:
    def test_body_includes_traceback_content(self, monkeypatch):
        """Alert body contains traceback information."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock()
        error = _sample_error()

        send_alert("daily_brief", error, "run-020", _gmail_service=gmail)

        body = gmail.send_message.call_args[1]["body"]
        # Body should reference traceback section
        assert "Traceback" in body or "traceback" in body.lower() or "500" in body

    def test_build_body_traceback_capped_at_500_chars(self):
        """_build_body caps the traceback tail at 500 chars when traceback is longer."""
        error = ValueError("something went wrong")
        # Inject a very long traceback via the traceback module context
        long_tb = "x" * 2000

        with patch("tools.alerts.traceback.format_exc", return_value=long_tb):
            body = _build_body("daily_brief", error, "run-021")

        # The last 500 chars of long_tb are all 'x' — confirm they appear
        assert "x" * 500 in body
        # Confirm we didn't include more than 500 x's from the mock traceback
        x_section_start = body.find("x" * 500)
        x_section = body[x_section_start:]
        # After 500 x's the body ends (or has very little trailing content)
        assert len(x_section) <= 502  # 500 x's + possible newline

    def test_build_body_short_traceback_not_truncated(self):
        """_build_body includes full traceback when it is under 500 chars."""
        error = ValueError("small error")
        short_tb = "Traceback (most recent call last):\n  short\nValueError: small error"

        with patch("tools.alerts.traceback.format_exc", return_value=short_tb):
            body = _build_body("daily_brief", error, "run-022")

        assert short_tb in body


# ---------------------------------------------------------------------------
# Tests: _build_body unit tests
# ---------------------------------------------------------------------------

class TestBuildBody:
    def test_build_body_contains_all_required_fields(self):
        """_build_body output contains pipeline_name, run_id, error type, timestamp."""
        with patch("tools.alerts.traceback.format_exc", return_value="Traceback info here"):
            body = _build_body("test_pipeline", ValueError("bad"), "run-abc")

        assert "test_pipeline" in body
        assert "run-abc" in body
        assert "ValueError" in body
        # Timestamp: basic ISO date check
        assert re.search(r"\d{4}-\d{2}-\d{2}", body)

    def test_build_body_timestamp_is_utc(self):
        """_build_body timestamp includes UTC offset (+00:00)."""
        with patch("tools.alerts.traceback.format_exc", return_value="tb"):
            body = _build_body("p", RuntimeError("e"), "r")

        # UTC offset present in ISO 8601 output
        assert "+00:00" in body or "Z" in body


# ---------------------------------------------------------------------------
# Tests: gmail_service failure handling
# ---------------------------------------------------------------------------

class TestSendAlertGmailFailure:
    def test_does_not_raise_when_send_message_fails(self, monkeypatch):
        """send_alert does not propagate exceptions from gmail_service.send_message()."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock(raise_on_send=RuntimeError("Gmail API down"))
        error = _sample_error()

        # This must not raise even though send_message will raise
        send_alert("daily_brief", error, "run-030", _gmail_service=gmail)

    def test_logs_error_when_send_message_fails(self, monkeypatch):
        """send_alert logs an error when gmail_service.send_message() raises."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock(raise_on_send=ConnectionError("network issue"))
        error = _sample_error()

        with patch("tools.alerts.log") as mock_log:
            send_alert("daily_brief", error, "run-031", _gmail_service=gmail)

        mock_log.error.assert_called_once()
        error_call_kwargs = mock_log.error.call_args[1]
        assert error_call_kwargs.get("error_type") == "ConnectionError"

    def test_does_not_raise_when_gmail_service_instantiation_fails(self, monkeypatch):
        """send_alert does not raise even if building a GmailService instance fails."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        error = _sample_error()

        with patch("tools.alerts._get_gmail_service", side_effect=EnvironmentError("no creds")):
            # Must not raise
            send_alert("daily_brief", error, "run-032")


# ---------------------------------------------------------------------------
# Tests: integration — multiple error types
# ---------------------------------------------------------------------------

class TestSendAlertVariousErrors:
    @pytest.mark.parametrize("exc_type,msg", [
        (ValueError, "schema validation failed"),
        (KeyError, "missing field"),
        (OSError, "disk full"),
        (TimeoutError, "LLM call timed out"),
    ])
    def test_send_alert_works_with_various_exception_types(self, monkeypatch, exc_type, msg):
        """send_alert correctly logs error type for various exception classes."""
        monkeypatch.setenv("ALERT_EMAIL", "ops@example.com")
        gmail = _make_gmail_mock()
        error = exc_type(msg)

        send_alert("daily_brief", error, "run-040", _gmail_service=gmail)

        body = gmail.send_message.call_args[1]["body"]
        assert exc_type.__name__ in body

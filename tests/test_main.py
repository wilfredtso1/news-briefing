"""
Tests for main.py — specifically the _check_inbox_commands helper.

Testing strategy:
- GmailService is mocked to avoid real API calls
- classify_command and pipeline runs are mocked
- Verifies that command emails trigger pipelines and are archived afterwards
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from gmail_service import EmailMessage


def _make_email(
    message_id: str = "msg-cmd-1",
    subject: str = "send brief",
    body_text: str = "",
    sender_email: str = "user@gmail.com",
) -> EmailMessage:
    return EmailMessage(
        message_id=message_id,
        thread_id="thread-cmd-1",
        subject=subject,
        sender=f"User <{sender_email}>",
        sender_email=sender_email,
        body_text=body_text,
        body_html="",
        list_unsubscribe=None,
        list_id=None,
        date="Wed, 26 Mar 2026 09:00:00 -0500",
        labels=["INBOX", "UNREAD"],
    )


class TestCheckInboxCommands:
    """_check_inbox_commands helper in main.py."""

    def test_self_addressed_email_triggers_daily_brief(self):
        """A self-addressed 'send brief' email triggers daily_brief and is archived."""
        gmail = MagicMock()
        gmail.list_messages_with_query.return_value = [_make_email(subject="send brief")]

        with (
            patch("supervisor.immediate.classify_command", return_value="daily_brief") as mock_classify,
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            from main import _check_inbox_commands
            _check_inbox_commands("run-001", gmail)

        mock_classify.assert_called_once()
        mock_run.assert_called_once()
        gmail.archive_messages.assert_called_once_with(["msg-cmd-1"])

    def test_self_addressed_email_triggers_deep_read(self):
        """A self-addressed 'deep read' email triggers deep_read with force=True."""
        gmail = MagicMock()
        gmail.list_messages_with_query.return_value = [_make_email(subject="deep read")]

        with (
            patch("supervisor.immediate.classify_command", return_value="deep_read"),
            patch("pipeline.deep_read.run_deep_read") as mock_run,
        ):
            from main import _check_inbox_commands
            _check_inbox_commands("run-001", gmail)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("force") is True
        gmail.archive_messages.assert_called_once_with(["msg-cmd-1"])

    def test_email_archived_even_when_pipeline_fails(self):
        """Archive must happen in finally block — even if the pipeline crashes."""
        gmail = MagicMock()
        gmail.list_messages_with_query.return_value = [_make_email(subject="send brief")]

        with (
            patch("supervisor.immediate.classify_command", return_value="daily_brief"),
            patch("pipeline.daily_brief.run", side_effect=Exception("pipeline crashed")),
            patch("tools.alerts.send_alert"),
        ):
            from main import _check_inbox_commands
            # Should not raise
            _check_inbox_commands("run-001", gmail)

        # Email still archived despite pipeline failure
        gmail.archive_messages.assert_called_once_with(["msg-cmd-1"])

    def test_no_command_emails_does_nothing(self):
        """Empty inbox query → no pipeline calls, no archive calls."""
        gmail = MagicMock()
        gmail.list_messages_with_query.return_value = []

        with patch("pipeline.daily_brief.run") as mock_run:
            from main import _check_inbox_commands
            _check_inbox_commands("run-001", gmail)

        mock_run.assert_not_called()
        gmail.archive_messages.assert_not_called()

    def test_gmail_scan_failure_is_non_fatal(self):
        """If the inbox query throws, the function logs and returns without crashing."""
        gmail = MagicMock()
        gmail.list_messages_with_query.side_effect = Exception("Gmail API error")

        with patch("pipeline.daily_brief.run") as mock_run:
            from main import _check_inbox_commands
            # Should not raise
            _check_inbox_commands("run-001", gmail)

        mock_run.assert_not_called()

    def test_classify_failure_still_archives_email(self):
        """If classify_command raises, email is archived to prevent infinite retry."""
        gmail = MagicMock()
        gmail.list_messages_with_query.return_value = [_make_email(subject="send brief")]

        with (
            patch("supervisor.immediate.classify_command", side_effect=Exception("classify failed")),
            patch("pipeline.daily_brief.run") as mock_run,
        ):
            from main import _check_inbox_commands
            _check_inbox_commands("run-001", gmail)

        mock_run.assert_not_called()
        gmail.archive_messages.assert_called_once_with(["msg-cmd-1"])

    def test_multiple_command_emails_processed_in_order(self):
        """Multiple command emails → each triggers a pipeline and is archived."""
        gmail = MagicMock()
        gmail.list_messages_with_query.return_value = [
            _make_email(message_id="cmd-1", subject="send brief"),
            _make_email(message_id="cmd-2", subject="deep read"),
        ]

        with (
            patch("supervisor.immediate.classify_command", side_effect=["daily_brief", "deep_read"]),
            patch("pipeline.daily_brief.run") as mock_brief,
            patch("pipeline.deep_read.run_deep_read") as mock_deep,
        ):
            from main import _check_inbox_commands
            _check_inbox_commands("run-001", gmail)

        mock_brief.assert_called_once()
        mock_deep.assert_called_once()
        assert gmail.archive_messages.call_count == 2

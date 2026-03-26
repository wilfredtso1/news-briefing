"""
Tests for supervisor/code_change_agent.py

Covers:
- write_file raises for disallowed paths (schema.sql, main.py, migrations/)
- write_file succeeds for allowed paths (pipeline/)
- run_bash raises for any command other than 'pytest tests/'
- run_bash calls subprocess correctly for 'pytest tests/'
- run_code_change_agent does NOT send email when tests fail
- run_code_change_agent sends email with exact subject when tests pass
- send_diff_email raises when code_change_notify_email is None
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# write_file validation
# ---------------------------------------------------------------------------

class TestWriteFileValidation:
    def test_write_file_raises_for_schema_sql(self):
        """write_file must raise ValueError for schema.sql."""
        from supervisor.code_change_agent import write_file

        with pytest.raises(ValueError, match="not permitted"):
            write_file.invoke({"path": "schema.sql", "content": "-- bad"})

    def test_write_file_raises_for_main_py(self):
        """write_file must raise ValueError for main.py."""
        from supervisor.code_change_agent import write_file

        with pytest.raises(ValueError, match="not permitted"):
            write_file.invoke({"path": "main.py", "content": "# bad"})

    def test_write_file_raises_for_migrations_path(self):
        """write_file must raise ValueError for any path under migrations/."""
        from supervisor.code_change_agent import write_file

        with pytest.raises(ValueError, match="not permitted"):
            write_file.invoke({"path": "migrations/004.sql", "content": "-- bad"})

    def test_write_file_raises_for_config_py(self):
        """write_file must raise ValueError for config.py."""
        from supervisor.code_change_agent import write_file

        with pytest.raises(ValueError, match="not permitted"):
            write_file.invoke({"path": "config.py", "content": "# bad"})

    def test_write_file_raises_for_disallowed_prefix(self):
        """write_file raises for paths not under pipeline/, supervisor/, or tools/."""
        from supervisor.code_change_agent import write_file

        with pytest.raises(ValueError, match="not allowed"):
            write_file.invoke({"path": "some_other_module.py", "content": "# bad"})

    def test_write_file_succeeds_for_pipeline_path(self, tmp_path, monkeypatch):
        """write_file succeeds for pipeline/topic_gap_fill.py."""
        from supervisor import code_change_agent

        # Point PROJECT_ROOT at tmp_path so no real files are touched
        monkeypatch.setattr(code_change_agent, "PROJECT_ROOT", tmp_path)
        (tmp_path / "pipeline").mkdir(parents=True, exist_ok=True)

        result = code_change_agent.write_file.invoke({
            "path": "pipeline/topic_gap_fill.py",
            "content": "# stub\n",
        })

        assert "pipeline/topic_gap_fill.py" in result
        assert (tmp_path / "pipeline" / "topic_gap_fill.py").read_text() == "# stub\n"

    def test_write_file_succeeds_for_supervisor_path(self, tmp_path, monkeypatch):
        """write_file succeeds for supervisor/ paths."""
        from supervisor import code_change_agent

        monkeypatch.setattr(code_change_agent, "PROJECT_ROOT", tmp_path)
        (tmp_path / "supervisor").mkdir(parents=True, exist_ok=True)

        result = code_change_agent.write_file.invoke({
            "path": "supervisor/new_helper.py",
            "content": "# helper\n",
        })

        assert "supervisor/new_helper.py" in result

    def test_write_file_succeeds_for_tools_path(self, tmp_path, monkeypatch):
        """write_file succeeds for tools/ paths."""
        from supervisor import code_change_agent

        monkeypatch.setattr(code_change_agent, "PROJECT_ROOT", tmp_path)
        (tmp_path / "tools").mkdir(parents=True, exist_ok=True)

        result = code_change_agent.write_file.invoke({
            "path": "tools/new_util.py",
            "content": "# util\n",
        })

        assert "tools/new_util.py" in result


# ---------------------------------------------------------------------------
# run_bash validation
# ---------------------------------------------------------------------------

class TestRunBashValidation:
    def test_run_bash_raises_for_arbitrary_command(self):
        """run_bash raises ValueError for any command other than 'pytest tests/'."""
        from supervisor.code_change_agent import run_bash

        with pytest.raises(ValueError, match="Only 'pytest tests/' is permitted"):
            run_bash.invoke({"command": "rm -rf /"})

    def test_run_bash_raises_for_ls_command(self):
        """run_bash raises ValueError for 'ls'."""
        from supervisor.code_change_agent import run_bash

        with pytest.raises(ValueError, match="Only 'pytest tests/' is permitted"):
            run_bash.invoke({"command": "ls"})

    def test_run_bash_raises_for_git_command(self):
        """run_bash raises ValueError for git commands."""
        from supervisor.code_change_agent import run_bash

        with pytest.raises(ValueError, match="Only 'pytest tests/' is permitted"):
            run_bash.invoke({"command": "git push"})

    def test_run_bash_raises_for_pytest_with_different_path(self):
        """run_bash raises ValueError for 'pytest .' (not exactly 'pytest tests/')."""
        from supervisor.code_change_agent import run_bash

        with pytest.raises(ValueError, match="Only 'pytest tests/' is permitted"):
            run_bash.invoke({"command": "pytest ."})

    def test_run_bash_calls_subprocess_for_pytest_tests(self):
        """run_bash calls subprocess.run with ['pytest', 'tests/'] for the permitted command."""
        from supervisor import code_change_agent

        mock_result = MagicMock()
        mock_result.stdout = "5 passed"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("supervisor.code_change_agent.subprocess.run", return_value=mock_result) as mock_run:
            output = code_change_agent.run_bash.invoke({"command": "pytest tests/"})

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["pytest", "tests/"]
        assert "5 passed" in output

    def test_run_bash_allows_whitespace_around_command(self):
        """run_bash permits 'pytest tests/' with leading/trailing whitespace."""
        from supervisor import code_change_agent

        mock_result = MagicMock()
        mock_result.stdout = "passed"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("supervisor.code_change_agent.subprocess.run", return_value=mock_result):
            # Should NOT raise — strip() is applied before comparison
            output = code_change_agent.run_bash.invoke({"command": "  pytest tests/  "})

        assert "passed" in output


# ---------------------------------------------------------------------------
# send_diff_email validation
# ---------------------------------------------------------------------------

class TestSendDiffEmailValidation:
    def test_send_diff_email_raises_when_notify_email_is_none(self, monkeypatch):
        """send_diff_email raises ValueError when code_change_notify_email is None."""
        import config

        mock_settings = MagicMock()
        mock_settings.code_change_notify_email = None
        monkeypatch.setattr(config, "settings", mock_settings)

        from supervisor.code_change_agent import send_diff_email

        with pytest.raises(ValueError, match="CODE_CHANGE_NOTIFY_EMAIL"):
            send_diff_email.invoke({"body": "some diff"})

    def test_send_diff_email_calls_gmail_when_email_set(self, monkeypatch):
        """send_diff_email calls GmailService.send_message with correct subject."""
        import config

        mock_settings = MagicMock()
        mock_settings.code_change_notify_email = "user@example.com"
        monkeypatch.setattr(config, "settings", mock_settings)

        mock_gmail_instance = MagicMock()

        with patch("gmail_service.GmailService", return_value=mock_gmail_instance):
            from supervisor.code_change_agent import send_diff_email
            send_diff_email.invoke({"body": "my diff"})

        mock_gmail_instance.send_message.assert_called_once()
        kwargs = mock_gmail_instance.send_message.call_args[1]
        assert kwargs["subject"] == "product input required for news briefing"
        assert kwargs["to"] == "user@example.com"


# ---------------------------------------------------------------------------
# run_code_change_agent integration tests (mocked graph)
# ---------------------------------------------------------------------------

class TestRunCodeChangeAgent:
    """
    Tests for the public entry point.  The LangGraph _graph is mocked so no
    real LLM or subprocess calls are made.
    """

    def test_does_not_send_email_when_tests_fail(self, monkeypatch):
        """run_code_change_agent must NOT send an approval email when tests fail.

        The graph is mocked to return a final state with tests_passed=False.
        We verify that no send_message call with the approval subject is made.
        """
        from supervisor import code_change_agent

        failing_state = {
            "raw_reply": "add sports headlines",
            "digest_id": "digest-002",
            "run_id": "run-002",
            "planned_changes": [],
            "files_modified": [],
            "test_result": "2 failed",
            "tests_passed": False,
            "diff": "",
            "attempts": 3,
            "messages": [],
        }

        mock_gmail_instance = MagicMock()
        monkeypatch.setattr(code_change_agent, "_graph", MagicMock(invoke=MagicMock(return_value=failing_state)))

        with patch("gmail_service.GmailService", return_value=mock_gmail_instance):
            code_change_agent.run_code_change_agent("feedback", "digest-002", "run-002")

        # Confirm send_message was NOT called with the approval subject
        for c in mock_gmail_instance.send_message.call_args_list:
            subject = (c[1] if c[1] else {}).get("subject", "")
            assert subject != "product input required for news briefing", (
                "Approval email must not be sent when tests fail"
            )

    def test_sends_email_with_correct_subject_when_tests_pass(self, monkeypatch):
        """run_code_change_agent graph sends email with exact subject when tests pass.

        We invoke the real send_diff node (bypassing the full graph) by making
        _graph.invoke call send_diff directly.
        """
        import config
        from supervisor import code_change_agent

        mock_settings = MagicMock()
        mock_settings.code_change_notify_email = "user@example.com"
        monkeypatch.setattr(config, "settings", mock_settings)

        mock_gmail_instance = MagicMock()

        # Make _graph.invoke call the real send_diff node so we exercise the email path
        passing_state = {
            "raw_reply": "add sports headlines",
            "digest_id": "digest-001",
            "run_id": "run-001",
            "planned_changes": ["modify pipeline/topic_gap_fill.py"],
            "files_modified": ["pipeline/topic_gap_fill.py"],
            "test_result": "5 passed",
            "tests_passed": True,
            "diff": "",
            "attempts": 1,
            "messages": [],
        }

        def fake_invoke(initial_state):
            # Simulate what the graph does when tests pass: call send_diff node
            code_change_agent.send_diff(passing_state)
            return passing_state

        monkeypatch.setattr(code_change_agent, "_graph", MagicMock(invoke=fake_invoke))

        with patch("gmail_service.GmailService", return_value=mock_gmail_instance):
            code_change_agent.run_code_change_agent("add sports headlines", "digest-001", "run-001")

        # Confirm send_message was called with the exact approval subject
        subjects = [
            c[1].get("subject", "") if c[1] else ""
            for c in mock_gmail_instance.send_message.call_args_list
        ]
        assert "product input required for news briefing" in subjects, (
            f"Expected approval email subject not found. Got subjects: {subjects}"
        )

    def test_logs_error_and_sends_failure_on_exception(self, monkeypatch):
        """run_code_change_agent logs errors and calls _send_failure_email on exception."""
        from supervisor import code_change_agent

        def boom(_):
            raise RuntimeError("graph exploded")

        monkeypatch.setattr(code_change_agent, "_graph", MagicMock(invoke=boom))

        with patch.object(code_change_agent, "_send_failure_email") as mock_fail:
            code_change_agent.run_code_change_agent("feedback", "digest-x", "run-x")

        mock_fail.assert_called_once()
        args = mock_fail.call_args[0]
        assert args[0] == "feedback"
        assert isinstance(args[1], RuntimeError)
        assert args[2] == "run-x"

    def test_graph_invoked_with_correct_initial_state(self, monkeypatch):
        """run_code_change_agent passes correct initial state dict to _graph.invoke."""
        from supervisor import code_change_agent

        captured = {}

        def capture_invoke(state):
            captured.update(state)
            return state

        monkeypatch.setattr(code_change_agent, "_graph", MagicMock(invoke=capture_invoke))

        code_change_agent.run_code_change_agent("user reply", "d-100", "r-200")

        assert captured["raw_reply"] == "user reply"
        assert captured["digest_id"] == "d-100"
        assert captured["run_id"] == "r-200"
        assert captured["tests_passed"] is False
        assert captured["attempts"] == 0
        assert captured["planned_changes"] == []
        assert captured["files_modified"] == []

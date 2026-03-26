"""
Tests for tools/unsubscribe.py.

Testing strategy:
- All external calls (Gmail, HTTP, DB) mocked
- Tests cover: mailto execution, URL execution, header parsing edge cases,
  error cases, and DB update sequencing (only after successful action)

Key scenarios:
  - mailto preferred over URL when both are present
  - mailto-only header → sends email
  - URL-only header → sends HTTP GET
  - No source in DB → UnsubscribeError before any action
  - No unsubscribe_header stored → UnsubscribeError before any action
  - Unparseable header (no valid URIs) → UnsubscribeError before any action
  - HTTP timeout → UnsubscribeError, source NOT marked unsubscribed
  - HTTP non-2xx → UnsubscribeError, source NOT marked unsubscribed
  - DB mark failure → raises after action already taken (acceptable — unsubscribe executed)
  - mark_source_unsubscribed called exactly once on success
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from tools.unsubscribe import (
    UnsubscribeError,
    _execute_mailto,
    _execute_url,
    _parse_unsubscribe_header,
    execute_unsubscribe,
)


# ---------------------------------------------------------------------------
# _parse_unsubscribe_header — pure function, no mocks needed
# ---------------------------------------------------------------------------


class TestParseUnsubscribeHeader:
    def test_both_mailto_and_url_extracted(self):
        header = "<mailto:unsub@example.com?subject=unsubscribe>, <https://example.com/unsub>"
        result = _parse_unsubscribe_header(header)
        assert result["mailto"] == "mailto:unsub@example.com?subject=unsubscribe"
        assert result["url"] == "https://example.com/unsub"

    def test_mailto_only_header(self):
        header = "<mailto:list-unsub@newsletters.io>"
        result = _parse_unsubscribe_header(header)
        assert result["mailto"] == "mailto:list-unsub@newsletters.io"
        assert result["url"] is None

    def test_url_only_header(self):
        header = "<https://example.com/unsubscribe?token=abc123>"
        result = _parse_unsubscribe_header(header)
        assert result["mailto"] is None
        assert result["url"] == "https://example.com/unsubscribe?token=abc123"

    def test_http_url_also_extracted(self):
        header = "<http://example.com/unsub>"
        result = _parse_unsubscribe_header(header)
        assert result["url"] == "http://example.com/unsub"

    def test_only_first_mailto_returned(self):
        """If header has two mailto URIs, only the first is returned."""
        header = "<mailto:first@example.com>, <mailto:second@example.com>"
        result = _parse_unsubscribe_header(header)
        assert result["mailto"] == "mailto:first@example.com"

    def test_empty_header_returns_nones(self):
        result = _parse_unsubscribe_header("")
        assert result["mailto"] is None
        assert result["url"] is None

    def test_header_with_no_angle_brackets_returns_nones(self):
        result = _parse_unsubscribe_header("mailto:unsub@example.com")
        assert result["mailto"] is None
        assert result["url"] is None

    def test_case_insensitive_scheme_matching(self):
        header = "<MAILTO:unsub@example.com>, <HTTPS://example.com/unsub>"
        result = _parse_unsubscribe_header(header)
        assert result["mailto"] is not None
        assert result["url"] is not None


# ---------------------------------------------------------------------------
# _execute_mailto — unit tests with mocked GmailService
# ---------------------------------------------------------------------------


class TestExecuteMailto:
    def test_sends_to_parsed_address_with_subject(self):
        mock_gmail = MagicMock()
        result = _execute_mailto("mailto:unsub@example.com?subject=unsubscribe+me", mock_gmail)
        mock_gmail.send_message.assert_called_once_with(
            to="unsub@example.com",
            subject="unsubscribe me",
            body="",
        )
        assert "unsub@example.com" in result

    def test_defaults_subject_to_unsubscribe_when_missing(self):
        mock_gmail = MagicMock()
        _execute_mailto("mailto:unsub@example.com", mock_gmail)
        mock_gmail.send_message.assert_called_once_with(
            to="unsub@example.com",
            subject="unsubscribe",
            body="",
        )

    def test_raises_unsubscribe_error_when_no_address(self):
        mock_gmail = MagicMock()
        with pytest.raises(UnsubscribeError, match="no address"):
            _execute_mailto("mailto:", mock_gmail)

    def test_creates_gmail_service_when_none_provided(self):
        # GmailService is imported lazily inside _execute_mailto; patch at the source module
        with patch("gmail_service.GmailService") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            _execute_mailto("mailto:test@example.com", None)
            mock_cls.assert_called_once()
            mock_instance.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# _execute_url — unit tests with mocked httpx
# ---------------------------------------------------------------------------


class TestExecuteUrl:
    def test_successful_get_returns_description(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        with patch("tools.unsubscribe.httpx.get", return_value=mock_response) as mock_get:
            result = _execute_url("https://example.com/unsub")
            mock_get.assert_called_once_with(
                "https://example.com/unsub",
                follow_redirects=True,
                timeout=15,
            )
        assert "200" in result

    def test_timeout_raises_unsubscribe_error(self):
        with patch("tools.unsubscribe.httpx.get", side_effect=httpx.TimeoutException("timeout")):
            with pytest.raises(UnsubscribeError, match="timed out"):
                _execute_url("https://example.com/unsub")

    def test_http_error_raises_unsubscribe_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
        with patch("tools.unsubscribe.httpx.get", side_effect=error):
            with pytest.raises(UnsubscribeError, match="404"):
                _execute_url("https://example.com/unsub")

    def test_request_error_raises_unsubscribe_error(self):
        with patch("tools.unsubscribe.httpx.get", side_effect=httpx.RequestError("conn refused")):
            with pytest.raises(UnsubscribeError, match="request error"):
                _execute_url("https://example.com/unsub")


# ---------------------------------------------------------------------------
# execute_unsubscribe — integration tests with all externals mocked
# ---------------------------------------------------------------------------


class TestExecuteUnsubscribe:
    def _make_source(self, unsubscribe_header: str | None = "<mailto:unsub@example.com>") -> dict:
        return {
            "id": "source-1",
            "sender_email": "newsletter@example.com",
            "name": "Example Newsletter",
            "unsubscribe_header": unsubscribe_header,
            "status": "active",
        }

    def test_mailto_preferred_over_url_when_both_present(self):
        source = self._make_source(
            "<mailto:unsub@example.com?subject=unsubscribe>, <https://example.com/unsub>"
        )
        mock_gmail = MagicMock()
        with (
            patch("tools.unsubscribe.get_source_by_email", return_value=source),
            patch("tools.unsubscribe.mark_source_unsubscribed") as mock_mark,
        ):
            result = execute_unsubscribe("newsletter@example.com", gmail=mock_gmail)

        mock_gmail.send_message.assert_called_once()
        mock_mark.assert_called_once_with("newsletter@example.com")
        assert "mailto" in result

    def test_url_used_when_no_mailto(self):
        source = self._make_source("<https://example.com/unsub>")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        with (
            patch("tools.unsubscribe.get_source_by_email", return_value=source),
            patch("tools.unsubscribe.mark_source_unsubscribed") as mock_mark,
            patch("tools.unsubscribe.httpx.get", return_value=mock_response),
        ):
            result = execute_unsubscribe("newsletter@example.com")

        mock_mark.assert_called_once_with("newsletter@example.com")
        assert "200" in result

    def test_raises_when_source_not_found(self):
        with patch("tools.unsubscribe.get_source_by_email", return_value=None):
            with pytest.raises(UnsubscribeError, match="No newsletter source found"):
                execute_unsubscribe("unknown@example.com")

    def test_raises_when_no_unsubscribe_header(self):
        source = self._make_source(unsubscribe_header=None)
        with patch("tools.unsubscribe.get_source_by_email", return_value=source):
            with pytest.raises(UnsubscribeError, match="no List-Unsubscribe header"):
                execute_unsubscribe("newsletter@example.com")

    def test_raises_when_header_has_no_parseable_uri(self):
        source = self._make_source(unsubscribe_header="no-angle-brackets-at-all")
        with patch("tools.unsubscribe.get_source_by_email", return_value=source):
            with pytest.raises(UnsubscribeError, match="no parseable mailto"):
                execute_unsubscribe("newsletter@example.com")

    def test_source_not_marked_unsubscribed_on_http_failure(self):
        """DB mark must NOT be called if the HTTP action fails."""
        source = self._make_source("<https://example.com/unsub>")
        with (
            patch("tools.unsubscribe.get_source_by_email", return_value=source),
            patch("tools.unsubscribe.mark_source_unsubscribed") as mock_mark,
            patch("tools.unsubscribe.httpx.get", side_effect=httpx.TimeoutException("timeout")),
        ):
            with pytest.raises(UnsubscribeError):
                execute_unsubscribe("newsletter@example.com")

        mock_mark.assert_not_called()

    def test_source_not_marked_unsubscribed_on_gmail_failure(self):
        """DB mark must NOT be called if the mailto send fails."""
        source = self._make_source("<mailto:unsub@example.com>")
        mock_gmail = MagicMock()
        mock_gmail.send_message.side_effect = Exception("Gmail API error")
        with (
            patch("tools.unsubscribe.get_source_by_email", return_value=source),
            patch("tools.unsubscribe.mark_source_unsubscribed") as mock_mark,
        ):
            with pytest.raises(Exception, match="Gmail API error"):
                execute_unsubscribe("newsletter@example.com", gmail=mock_gmail)

        mock_mark.assert_not_called()

    def test_mark_unsubscribed_called_exactly_once_on_success(self):
        source = self._make_source("<mailto:unsub@example.com>")
        mock_gmail = MagicMock()
        with (
            patch("tools.unsubscribe.get_source_by_email", return_value=source),
            patch("tools.unsubscribe.mark_source_unsubscribed") as mock_mark,
        ):
            execute_unsubscribe("newsletter@example.com", gmail=mock_gmail)

        mock_mark.assert_called_once_with("newsletter@example.com")

"""
Unit tests for gmail_service.py pure helper functions.

Only _extract_email and _extract_body are tested here — they are pure functions
with no external dependencies. GmailService itself requires a live Google auth
token and is covered by manual smoke tests, not automated unit tests.
"""

import pytest

from gmail_service import _extract_email, _extract_body


# ---------------------------------------------------------------------------
# _extract_email
# ---------------------------------------------------------------------------

class TestExtractEmail:
    def test_extracts_email_from_angle_bracket_format(self):
        assert _extract_email("Morning Brew <morningbrew@morningbrew.com>") == "morningbrew@morningbrew.com"

    def test_lowercases_result(self):
        assert _extract_email("Sender <Hello@Example.COM>") == "hello@example.com"

    def test_plain_email_unchanged(self):
        assert _extract_email("axiosam@axios.com") == "axiosam@axios.com"

    def test_plain_email_lowercased(self):
        assert _extract_email("AXIOSAM@AXIOS.COM") == "axiosam@axios.com"

    def test_strips_whitespace(self):
        assert _extract_email("  sender@example.com  ") == "sender@example.com"

    def test_quoted_name_with_angle_brackets(self):
        assert _extract_email('"The Hustle" <hello@thehustle.co>') == "hello@thehustle.co"

    def test_empty_string(self):
        assert _extract_email("") == ""


# ---------------------------------------------------------------------------
# _extract_body
# ---------------------------------------------------------------------------

class TestExtractBody:
    def _make_payload(self, mime_type: str, data_str: str) -> dict:
        """Helper: build a minimal Gmail payload dict with base64-encoded body."""
        import base64
        encoded = base64.urlsafe_b64encode(data_str.encode()).decode()
        return {"mimeType": mime_type, "body": {"data": encoded}, "parts": []}

    def test_extracts_plain_text(self):
        payload = self._make_payload("text/plain", "Hello plain world")
        text, html = _extract_body(payload)
        assert text == "Hello plain world"
        assert html == ""

    def test_extracts_html(self):
        payload = self._make_payload("text/html", "<p>Hello HTML</p>")
        text, html = _extract_body(payload)
        assert text == ""
        assert html == "<p>Hello HTML</p>"

    def test_prefers_parts_over_top_level(self):
        """Multipart messages store content in parts, not the top-level body."""
        import base64
        plain_data = base64.urlsafe_b64encode(b"Plain content").decode()
        html_data = base64.urlsafe_b64encode(b"<p>HTML content</p>").decode()
        payload = {
            "mimeType": "multipart/alternative",
            "body": {},
            "parts": [
                {"mimeType": "text/plain", "body": {"data": plain_data}, "parts": []},
                {"mimeType": "text/html", "body": {"data": html_data}, "parts": []},
            ],
        }
        text, html = _extract_body(payload)
        assert text == "Plain content"
        assert html == "<p>HTML content</p>"

    def test_empty_payload_returns_empty_strings(self):
        text, html = _extract_body({})
        assert text == ""
        assert html == ""

    def test_handles_missing_body_data(self):
        payload = {"mimeType": "text/plain", "body": {}, "parts": []}
        text, html = _extract_body(payload)
        assert text == ""
        assert html == ""

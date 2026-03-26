"""
Tests for pipeline/extractor.py

LLM calls use FakeListChatModel — never calls real Anthropic API.
"""

import json
from unittest.mock import patch

import pytest
from langchain_community.chat_models.fake import FakeListChatModel

from pipeline.extractor import (
    ExtractedStory,
    extract_stories,
    _prepare_content,
    _strip_html,
    _normalise_whitespace,
    MAX_CONTENT_CHARS,
)


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------

class TestStripHtml:
    def test_strip_html_removes_tags(self):
        html = "<p>Hello <b>world</b></p>"
        result = _strip_html(html)
        assert "Hello" in result
        assert "world" in result
        assert "<b>" not in result
        assert "<p>" not in result

    def test_strip_html_removes_script_block(self):
        html = "<script>alert('xss')</script><p>Safe content</p>"
        result = _strip_html(html)
        assert "alert" not in result
        assert "Safe content" in result

    def test_strip_html_removes_style_block(self):
        html = "<style>.foo { color: red }</style><p>Text</p>"
        result = _strip_html(html)
        assert ".foo" not in result
        assert "Text" in result

    def test_strip_html_decodes_entities(self):
        html = "&amp; &lt;b&gt; &nbsp;"
        result = _strip_html(html)
        assert "&" in result
        assert "<b>" in result

    def test_strip_html_preserves_paragraph_breaks(self):
        html = "<p>Paragraph one</p><p>Paragraph two</p>"
        result = _strip_html(html)
        assert "Paragraph one" in result
        assert "Paragraph two" in result

    def test_strip_html_empty_string(self):
        assert _strip_html("") == ""


# ---------------------------------------------------------------------------
# _prepare_content
# ---------------------------------------------------------------------------

class TestPrepareContent:
    def test_prefers_plain_text_over_html(self):
        long_text = "Plain text content. " * 20
        result = _prepare_content(long_text, "<html><p>HTML content</p></html>")
        assert "Plain text content" in result
        assert "HTML content" not in result

    def test_falls_back_to_html_when_text_too_short(self):
        result = _prepare_content("short", "<p>HTML fallback content here</p>")
        assert "HTML fallback content here" in result

    def test_returns_empty_string_when_both_empty(self):
        result = _prepare_content("", "")
        assert result == ""

    def test_normalises_whitespace_in_plain_text(self):
        # Pad to >100 chars to trigger plain text path; three+ blank lines should collapse
        text = "Line one\n\n\n\n\nLine two" + " extra content " * 20
        result = _prepare_content(text, "")
        assert "\n\n\n" not in result


# ---------------------------------------------------------------------------
# _normalise_whitespace
# ---------------------------------------------------------------------------

class TestNormaliseWhitespace:
    def test_collapses_multiple_blank_lines(self):
        text = "Para one\n\n\n\n\nPara two"
        result = _normalise_whitespace(text)
        assert "\n\n\n" not in result
        assert "Para one" in result
        assert "Para two" in result

    def test_collapses_horizontal_whitespace(self):
        text = "word1   \t  word2"
        result = _normalise_whitespace(text)
        assert "word1 word2" in result

    def test_strips_leading_trailing_space(self):
        text = "   content   "
        assert _normalise_whitespace(text) == "content"


# ---------------------------------------------------------------------------
# extract_stories (with mocked LLM)
# ---------------------------------------------------------------------------

class TestExtractStories:
    def _make_fake_llm_response(self, stories: list[dict]) -> str:
        """Build the JSON string the fake LLM will return."""
        return json.dumps({"stories": stories})

    def test_extract_stories_returns_extracted_story_objects(self, monkeypatch):
        fake_response = self._make_fake_llm_response([
            {"title": "AI Raises $1B", "body": "An AI startup raised $1B.", "key_facts": ["$1B"]},
            {"title": "Fed Holds Rates", "body": "The Fed held rates steady.", "key_facts": []},
        ])
        fake_llm = FakeListChatModel(responses=[fake_response])

        with patch("pipeline.extractor._llm", fake_llm):
            # FakeListChatModel doesn't parse JSON — we patch the chain directly
            with patch("pipeline.extractor._chain") as mock_chain:
                mock_chain.invoke.return_value = {
                    "stories": [
                        {"title": "AI Raises $1B", "body": "An AI startup raised $1B.", "key_facts": ["$1B"]},
                        {"title": "Fed Holds Rates", "body": "The Fed held rates steady.", "key_facts": []},
                    ]
                }
                results = extract_stories(
                    body_text="Some newsletter content " * 50,
                    body_html="",
                    newsletter_name="Morning Brew",
                    sender_email="morningbrew@morningbrew.com",
                )

        assert len(results) == 2
        assert all(isinstance(s, ExtractedStory) for s in results)
        assert results[0].title == "AI Raises $1B"
        assert results[0].source_newsletter == "Morning Brew"
        assert results[0].source_email == "morningbrew@morningbrew.com"
        assert results[0].key_facts == ["$1B"]

    def test_extract_stories_returns_empty_on_llm_failure(self, monkeypatch):
        with patch("pipeline.extractor._chain") as mock_chain:
            mock_chain.invoke.side_effect = RuntimeError("API error")
            results = extract_stories(
                body_text="Content " * 50,
                body_html="",
                newsletter_name="Test Newsletter",
                sender_email="test@example.com",
            )
        assert results == []

    def test_extract_stories_returns_empty_on_empty_content(self):
        results = extract_stories(
            body_text="",
            body_html="",
            newsletter_name="Empty Newsletter",
            sender_email="empty@example.com",
        )
        assert results == []

    def test_extract_stories_skips_stories_missing_title(self, monkeypatch):
        with patch("pipeline.extractor._chain") as mock_chain:
            mock_chain.invoke.return_value = {
                "stories": [
                    {"title": "", "body": "Some body text", "key_facts": []},
                    {"title": "Valid Title", "body": "Valid body", "key_facts": []},
                ]
            }
            results = extract_stories(
                body_text="Content " * 50,
                body_html="",
                newsletter_name="Newsletter",
                sender_email="test@example.com",
            )
        assert len(results) == 1
        assert results[0].title == "Valid Title"

    def test_extract_stories_skips_stories_missing_body(self, monkeypatch):
        with patch("pipeline.extractor._chain") as mock_chain:
            mock_chain.invoke.return_value = {
                "stories": [
                    {"title": "Title", "body": "", "key_facts": []},
                ]
            }
            results = extract_stories(
                body_text="Content " * 50,
                body_html="",
                newsletter_name="Newsletter",
                sender_email="test@example.com",
            )
        assert results == []

    def test_extract_stories_truncates_content_at_max_chars(self, monkeypatch):
        """Verify content is truncated before being sent to LLM."""
        captured_invocations = []

        with patch("pipeline.extractor._chain") as mock_chain:
            def capture_invoke(args):
                captured_invocations.append(args)
                return {"stories": []}
            mock_chain.invoke.side_effect = capture_invoke

            long_content = "x" * 20_000
            extract_stories(
                body_text=long_content,
                body_html="",
                newsletter_name="Newsletter",
                sender_email="test@example.com",
            )

        assert len(captured_invocations) == 1
        assert len(captured_invocations[0]["content"]) <= MAX_CONTENT_CHARS

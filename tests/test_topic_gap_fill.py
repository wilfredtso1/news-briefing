"""
Tests for pipeline/topic_gap_fill.py

Tavily calls and DB reads are mocked — never calls real external services.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from pipeline.synthesizer import SynthesizedStory
from pipeline.topic_gap_fill import gap_fill_topics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_story(topic: str, title: str = "Test Story") -> SynthesizedStory:
    return SynthesizedStory(
        title=title,
        body="Some body text.",
        topic=topic,
        source_newsletters=["Morning Brew"],
        source_emails=["brew@brew.com"],
        key_facts=[],
        cluster_embedding=[],
        source_count=1,
    )


_FAKE_RESULTS = [
    {"content": "Sports headline one from Reuters.", "url": "https://reuters.com/1"},
    {"content": "Sports headline two from AP News.", "url": "https://ap.org/1"},
]


# ---------------------------------------------------------------------------
# gap_fill_topics
# ---------------------------------------------------------------------------

class TestGapFillTopics:
    def test_returns_input_unchanged_when_web_search_topics_empty(self):
        stories = [_make_story("ai"), _make_story("markets")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=[]):
            result = gap_fill_topics(stories, run_id="run-1")
        assert result == stories

    def test_returns_input_unchanged_when_web_search_topics_none(self):
        stories = [_make_story("ai")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=None):
            result = gap_fill_topics(stories, run_id="run-1")
        assert result == stories

    def test_covered_topic_does_not_call_tavily(self):
        stories = [_make_story("ai"), _make_story("markets")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["ai"]), \
             patch("pipeline.topic_gap_fill._search_with_retry") as mock_search:
            result = gap_fill_topics(stories, run_id="run-1")
        mock_search.assert_not_called()
        assert result == stories

    def test_covered_topic_case_insensitive(self):
        """Topic comparison must be case-insensitive."""
        stories = [_make_story("ai")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["AI"]), \
             patch("pipeline.topic_gap_fill._search_with_retry") as mock_search:
            gap_fill_topics(stories, run_id="run-1")
        mock_search.assert_not_called()

    def test_uncovered_topic_calls_tavily_and_appends_story(self):
        stories = [_make_story("ai")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["sports"]), \
             patch("pipeline.topic_gap_fill._search_with_retry", return_value=_FAKE_RESULTS):
            result = gap_fill_topics(stories, run_id="run-1")

        assert len(result) == 2
        gap_story = result[-1]
        assert gap_story.source_newsletters == ["Web Search: sports"]
        assert gap_story.source_emails == ["web_search"]
        assert "sports" in gap_story.title.lower()

    def test_uncovered_topic_source_newsletter_format(self):
        """source_newsletters must be exactly ['Web Search: {topic}']."""
        stories = [_make_story("ai")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["geopolitics"]), \
             patch("pipeline.topic_gap_fill._search_with_retry", return_value=_FAKE_RESULTS):
            result = gap_fill_topics(stories, run_id="run-1")

        assert result[-1].source_newsletters == ["Web Search: geopolitics"]

    def test_gap_fill_stories_appended_after_newsletter_stories(self):
        """Newsletter stories must remain at the front; gap-fill appended at end."""
        newsletter_stories = [_make_story("ai"), _make_story("markets")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["sports"]), \
             patch("pipeline.topic_gap_fill._search_with_retry", return_value=_FAKE_RESULTS):
            result = gap_fill_topics(newsletter_stories, run_id="run-1")

        assert result[0] is newsletter_stories[0]
        assert result[1] is newsletter_stories[1]
        assert result[-1].source_emails == ["web_search"]

    def test_tavily_raises_graceful_skip_other_topics_still_processed(self):
        """A Tavily failure on one topic must not prevent others from being processed."""
        stories = [_make_story("ai")]

        def side_effect(query: str):
            if "sports" in query:
                raise RuntimeError("Tavily timeout")
            return _FAKE_RESULTS

        with patch("pipeline.topic_gap_fill.get_config", return_value=["sports", "markets"]), \
             patch("pipeline.topic_gap_fill._search_with_retry", side_effect=side_effect):
            result = gap_fill_topics(stories, run_id="run-1")

        # markets should succeed; sports should be skipped
        assert len(result) == 2
        topics = [s.source_newsletters[0] for s in result[1:]]
        assert "Web Search: markets" in topics
        assert not any("sports" in t for t in topics)

    def test_empty_tavily_results_no_story_added(self):
        stories = [_make_story("ai")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["sports"]), \
             patch("pipeline.topic_gap_fill._search_with_retry", return_value=[]):
            result = gap_fill_topics(stories, run_id="run-1")

        assert result == stories

    def test_tavily_results_with_no_content_no_story_added(self):
        """Results with empty/missing content field should not produce a story."""
        stories = [_make_story("ai")]
        empty_results = [{"url": "https://example.com", "content": ""}]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["sports"]), \
             patch("pipeline.topic_gap_fill._search_with_retry", return_value=empty_results):
            result = gap_fill_topics(stories, run_id="run-1")

        assert result == stories

    def test_synthesized_story_has_all_required_fields(self):
        """Gap-fill story must be a valid SynthesizedStory with all fields populated."""
        stories = [_make_story("ai")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["policy"]), \
             patch("pipeline.topic_gap_fill._search_with_retry", return_value=_FAKE_RESULTS):
            result = gap_fill_topics(stories, run_id="run-1")

        gap_story = result[-1]
        assert isinstance(gap_story, SynthesizedStory)
        assert gap_story.title
        assert gap_story.body
        assert gap_story.topic
        assert gap_story.source_newsletters
        assert gap_story.source_emails
        assert isinstance(gap_story.key_facts, list)
        assert isinstance(gap_story.cluster_embedding, list)
        assert gap_story.source_count == 1

    def test_multiple_uncovered_topics_all_appended(self):
        stories = [_make_story("ai")]
        with patch("pipeline.topic_gap_fill.get_config", return_value=["sports", "health"]), \
             patch("pipeline.topic_gap_fill._search_with_retry", return_value=_FAKE_RESULTS):
            result = gap_fill_topics(stories, run_id="run-1")

        assert len(result) == 3
        gap_newsletters = {s.source_newsletters[0] for s in result[1:]}
        assert "Web Search: sports" in gap_newsletters
        assert "Web Search: health" in gap_newsletters

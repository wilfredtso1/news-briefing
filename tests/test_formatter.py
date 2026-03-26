"""
Tests for pipeline/formatter.py
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pipeline.formatter import (
    FormattedDigest,
    _assign_treatments,
    _build_subject,
    _source_attribution,
    format_digest,
)
from pipeline.synthesizer import SynthesizedStory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_story(
    title: str = "Title",
    body: str = "Body text that fills space in the digest.",
    topic: str = "ai",
    source_count: int = 1,
    source_newsletters: list[str] | None = None,
) -> SynthesizedStory:
    newsletters = source_newsletters or (["Morning Brew"] * source_count)
    return SynthesizedStory(
        title=title,
        body=body,
        topic=topic,
        source_newsletters=newsletters,
        source_emails=["email@example.com"] * source_count,
        source_count=source_count,
    )


# ---------------------------------------------------------------------------
# _source_attribution
# ---------------------------------------------------------------------------

class TestSourceAttribution:
    def test_single_source(self):
        story = _make_story(source_newsletters=["Morning Brew"])
        assert _source_attribution(story) == "Morning Brew"

    def test_two_sources(self):
        story = _make_story(source_newsletters=["Morning Brew", "Axios AM"])
        attr = _source_attribution(story)
        assert "Morning Brew" in attr
        assert "Axios AM" in attr

    def test_three_or_more_sources(self):
        story = _make_story(source_newsletters=["A", "B", "C"])
        attr = _source_attribution(story)
        assert "A" in attr
        assert "2 others" in attr

    def test_no_sources_returns_unknown(self):
        story = SynthesizedStory(
            title="Title", body="Body", topic="ai",
            source_newsletters=[], source_emails=[], source_count=0,
        )
        assert "unknown" in _source_attribution(story).lower()


# ---------------------------------------------------------------------------
# _assign_treatments
# ---------------------------------------------------------------------------

class TestAssignTreatments:
    def test_multi_source_story_gets_full_treatment_when_budget_allows(self):
        story = _make_story(source_count=2)
        assigned = _assign_treatments([story], word_budget=500)
        assert assigned[0][1] == "full"

    def test_single_source_story_gets_brief_treatment(self):
        story = _make_story(source_count=1)
        assigned = _assign_treatments([story], word_budget=500)
        assert assigned[0][1] == "brief"

    def test_stories_beyond_budget_get_one_liner(self):
        stories = [_make_story(source_count=2)] * 10  # each needs ~80 words
        assigned = _assign_treatments(stories, word_budget=100)  # room for ~1 full
        one_liner_count = sum(1 for _, t in assigned if t == "one_liner")
        assert one_liner_count >= 8  # most should be one-liners

    def test_budget_exhaustion_does_not_drop_stories(self):
        stories = [_make_story()] * 20
        assigned = _assign_treatments(stories, word_budget=50)
        assert len(assigned) == 20


# ---------------------------------------------------------------------------
# _build_subject
# ---------------------------------------------------------------------------

class TestBuildSubject:
    def test_includes_date_when_provided(self):
        stories = [_make_story("Top AI Story")]
        subject = _build_subject(stories, "daily", "Monday, March 25")
        assert "Monday, March 25" in subject

    def test_includes_top_story_title(self):
        stories = [_make_story("Fed Holds Rates")]
        subject = _build_subject(stories, "daily", "")
        assert "Fed Holds Rates" in subject

    def test_weekend_prefix_for_weekend_type(self):
        subject = _build_subject([], "weekend", "Sunday")
        assert "Weekend" in subject

    def test_deep_read_prefix(self):
        subject = _build_subject([], "deep_read", "")
        assert "Deep Read" in subject

    def test_handles_empty_story_list(self):
        subject = _build_subject([], "daily", "Monday")
        assert "Daily Brief" in subject


# ---------------------------------------------------------------------------
# format_digest
# ---------------------------------------------------------------------------

class TestFormatDigest:
    def test_returns_formatted_digest_object(self):
        stories = [
            _make_story("AI Funding", topic="ai", source_count=2),
            _make_story("Market Update", topic="markets", source_count=1),
        ]
        with patch("pipeline.formatter.get_config", return_value=None):
            result = format_digest(stories, digest_type="daily", date_str="Monday, March 25")

        assert isinstance(result, FormattedDigest)
        assert result.story_count == 2
        assert result.word_count > 0
        assert "AI Funding" in result.body
        assert "Market Update" in result.body

    def test_plain_text_body_has_no_html(self):
        stories = [_make_story("Story")]
        with patch("pipeline.formatter.get_config", return_value=None):
            result = format_digest(stories)
        assert "<" not in result.body
        assert ">" not in result.body

    def test_empty_stories_returns_digest_with_footer(self):
        with patch("pipeline.formatter.get_config", return_value=None):
            result = format_digest([])
        assert isinstance(result, FormattedDigest)
        assert result.story_count == 0

    def test_topic_sections_present_for_represented_topics(self):
        stories = [
            _make_story("AI Story", topic="ai"),
            _make_story("Health Story", topic="health"),
        ]
        with patch("pipeline.formatter.get_config", return_value=None):
            result = format_digest(stories)
        assert "AI" in result.body
        assert "Health" in result.body

    def test_empty_topic_sections_omitted(self):
        stories = [_make_story("AI Story", topic="ai")]
        with patch("pipeline.formatter.get_config", return_value=None):
            result = format_digest(stories)
        # Markets section should not appear if no market stories
        assert "Markets" not in result.body

    def test_one_liners_appear_in_also_noted_section(self):
        # Fill budget with one full-treatment story, rest become one-liners
        stories = [_make_story(f"Story {i}", source_count=2) for i in range(10)]
        with patch("pipeline.formatter.get_config", return_value={"daily": 100}):
            result = format_digest(stories)
        assert "Also Noted" in result.body

    def test_word_count_tracked_accurately(self):
        stories = [_make_story("Story")]
        with patch("pipeline.formatter.get_config", return_value=None):
            result = format_digest(stories)
        actual_word_count = len(result.body.split())
        assert result.word_count == actual_word_count

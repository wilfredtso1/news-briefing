"""
Tests for pipeline/ranker.py
"""

from unittest.mock import patch

import pytest

from pipeline.ranker import _score, rank_stories
from pipeline.synthesizer import SynthesizedStory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_story(
    title: str = "Title",
    topic: str = "ai",
    source_count: int = 1,
) -> SynthesizedStory:
    return SynthesizedStory(
        title=title,
        body="Body text.",
        topic=topic,
        source_newsletters=["Newsletter"] * source_count,
        source_emails=["email@example.com"] * source_count,
        source_count=source_count,
    )


_DEFAULT_WEIGHTS = {
    "ai": 1.5,
    "health": 1.3,
    "vc": 1.2,
    "markets": 1.1,
    "tech": 1.0,
    "policy": 1.0,
    "other": 0.8,
}


# ---------------------------------------------------------------------------
# _score
# ---------------------------------------------------------------------------

class TestScore:
    def test_multi_source_scores_higher_than_single(self):
        single = _make_story(topic="ai", source_count=1)
        multi = _make_story(topic="ai", source_count=3)
        assert _score(multi, _DEFAULT_WEIGHTS) > _score(single, _DEFAULT_WEIGHTS)

    def test_ai_scores_higher_than_other(self):
        ai_story = _make_story(topic="ai", source_count=1)
        other_story = _make_story(topic="other", source_count=1)
        assert _score(ai_story, _DEFAULT_WEIGHTS) > _score(other_story, _DEFAULT_WEIGHTS)

    def test_unknown_topic_falls_back_to_other_weight(self):
        story = _make_story(topic="sports", source_count=1)
        score = _score(story, _DEFAULT_WEIGHTS)
        assert score == pytest.approx(_DEFAULT_WEIGHTS["other"])

    def test_source_count_bonus_increases_linearly(self):
        story_1 = _make_story(topic="tech", source_count=1)
        story_2 = _make_story(topic="tech", source_count=2)
        story_3 = _make_story(topic="tech", source_count=3)
        diff_1_2 = _score(story_2, _DEFAULT_WEIGHTS) - _score(story_1, _DEFAULT_WEIGHTS)
        diff_2_3 = _score(story_3, _DEFAULT_WEIGHTS) - _score(story_2, _DEFAULT_WEIGHTS)
        assert abs(diff_1_2 - diff_2_3) < 1e-6


# ---------------------------------------------------------------------------
# rank_stories
# ---------------------------------------------------------------------------

class TestRankStories:
    def test_returns_empty_for_no_stories(self):
        with patch("pipeline.ranker.get_config", return_value=None):
            assert rank_stories([]) == []

    def test_returns_stories_sorted_by_score_descending(self):
        stories = [
            _make_story("Low", topic="other", source_count=1),
            _make_story("High", topic="ai", source_count=3),
            _make_story("Mid", topic="markets", source_count=1),
        ]
        with patch("pipeline.ranker.get_config", return_value=None):
            ranked = rank_stories(stories)
        assert ranked[0].title == "High"
        assert ranked[-1].title == "Low"

    def test_uses_custom_topic_weights_from_config(self):
        # Override weights so "other" ranks above "ai"
        custom_weights = {"ai": 0.5, "other": 2.0}
        stories = [
            _make_story("AI story", topic="ai", source_count=1),
            _make_story("Other story", topic="other", source_count=1),
        ]
        with patch("pipeline.ranker.get_config", return_value=custom_weights):
            ranked = rank_stories(stories)
        assert ranked[0].title == "Other story"

    def test_falls_back_to_defaults_on_config_failure(self):
        stories = [
            _make_story("A", topic="ai", source_count=1),
            _make_story("B", topic="other", source_count=1),
        ]
        with patch("pipeline.ranker.get_config", side_effect=RuntimeError("DB down")):
            ranked = rank_stories(stories)
        # Should still rank without crashing
        assert len(ranked) == 2
        assert ranked[0].title == "A"  # ai > other in defaults

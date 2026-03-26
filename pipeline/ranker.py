"""
Story ranker.

Scores and sorts synthesized stories for inclusion in the daily digest.

Ranking factors (in order of weight):
1. Source count — stories covered by multiple newsletters are more important
2. Topic weight — from agent_config (AI, health, VC higher; crypto, sports lower)
3. Recency signal — not directly available at rank time, so we rely on source count

The ranker is intentionally simple. Topic weights come from agent_config so the
supervisor can adjust them without a code change. The weights default to the
values seeded in schema.sql.
"""

from __future__ import annotations

import structlog

from pipeline.synthesizer import SynthesizedStory
from tools.db import get_config

log = structlog.get_logger(__name__)

# Default topic weights if agent_config is unavailable
_DEFAULT_TOPIC_WEIGHTS: dict[str, float] = {
    "ai": 1.5,
    "health": 1.3,
    "vc": 1.2,
    "markets": 1.1,
    "tech": 1.0,
    "policy": 1.0,
    "other": 0.8,
}

# Weight multiplier applied per additional source beyond the first
_SOURCE_COUNT_MULTIPLIER = 0.3


def rank_stories(stories: list[SynthesizedStory]) -> list[SynthesizedStory]:
    """
    Return stories sorted by descending relevance score.

    Reads topic_weights from agent_config at call time, so supervisor
    adjustments take effect on the next pipeline run without a restart.
    """
    if not stories:
        return []

    topic_weights = _load_topic_weights()
    scored = [
        (story, _score(story, topic_weights))
        for story in stories
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    log.info(
        "ranker_complete",
        story_count=len(stories),
        top_story=scored[0][0].title[:60] if scored else None,
        top_score=round(scored[0][1], 3) if scored else None,
    )

    return [story for story, _ in scored]


def _score(story: SynthesizedStory, topic_weights: dict[str, float]) -> float:
    """
    Compute a relevance score for a story.

    Base score = topic_weight
    Bonus = source_count_multiplier * (source_count - 1)
    """
    base = topic_weights.get(story.topic, topic_weights.get("other", 0.8))
    source_bonus = _SOURCE_COUNT_MULTIPLIER * (story.source_count - 1)
    return base + source_bonus


def _load_topic_weights() -> dict[str, float]:
    """
    Load topic weights from agent_config.

    Falls back to defaults if the config key is missing or malformed.
    The supervisor can update this via set_config("topic_weights", {...}).
    """
    try:
        raw = get_config("topic_weights")
        if isinstance(raw, dict):
            # Merge with defaults so any new topics have a fallback weight
            return {**_DEFAULT_TOPIC_WEIGHTS, **{k: float(v) for k, v in raw.items()}}
    except Exception as e:
        log.warning("ranker_config_load_failed", error=str(e), action="using defaults")
    return dict(_DEFAULT_TOPIC_WEIGHTS)

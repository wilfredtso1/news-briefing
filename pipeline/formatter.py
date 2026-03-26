"""
Digest formatter.

Converts ranked SynthesizedStory objects into a plain-text email digest,
respecting word budgets and applying tiered treatment:

  - FULL paragraph: ~80 words — multi-source, high-importance stories
  - BRIEF: ~30 words — single-source or lower-ranked stories
  - ONE-LINER: one sentence — everything that didn't make the word budget

Stories are grouped by topic section. Sections with no stories are omitted.
The digest closes with a "Also noted" block of one-liners.

Word budgets come from agent_config so the supervisor can adjust them.
Defaults match the SPEC: ~400 words for daily brief (10-15 min read target).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from pipeline.synthesizer import SynthesizedStory
from tools.db import get_config

log = structlog.get_logger(__name__)

# Treatment levels
_FULL = "full"
_BRIEF = "brief"
_ONE_LINER = "one_liner"

# Approximate word counts per treatment
_FULL_WORD_TARGET = 80
_BRIEF_WORD_TARGET = 30

# Section order in the digest
_TOPIC_ORDER = ["ai", "markets", "health", "vc", "tech", "policy", "other"]

_TOPIC_HEADERS = {
    "ai": "AI & Technology",
    "markets": "Markets & Finance",
    "health": "Health & Biotech",
    "vc": "Venture & Startups",
    "tech": "Tech",
    "policy": "Policy & Regulation",
    "other": "Other",
}

# Default word budget if agent_config unavailable
_DEFAULT_WORD_BUDGET = 400


@dataclass
class FormattedDigest:
    subject: str
    body: str
    word_count: int
    story_count: int
    full_count: int
    brief_count: int
    one_liner_count: int


def format_digest(
    stories: list[SynthesizedStory],
    digest_type: str = "daily",
    date_str: str = "",
) -> FormattedDigest:
    """
    Format ranked stories into a plain-text email digest.

    Args:
        stories: Ranked stories (highest priority first).
        digest_type: "daily", "deep_read", or "weekend" — affects subject and budget.
        date_str: Human-readable date string for the subject line (e.g. "Monday, March 25").

    Returns a FormattedDigest with subject, body, and stats.
    """
    word_budget = _load_word_budget(digest_type)
    assigned = _assign_treatments(stories, word_budget)

    subject = _build_subject(stories, digest_type, date_str)
    body = _build_body(assigned, digest_type)
    word_count = len(body.split())

    full_count = sum(1 for _, t in assigned if t == _FULL)
    brief_count = sum(1 for _, t in assigned if t == _BRIEF)
    one_liner_count = sum(1 for _, t in assigned if t == _ONE_LINER)

    log.info(
        "formatter_complete",
        digest_type=digest_type,
        story_count=len(stories),
        word_count=word_count,
        word_budget=word_budget,
        full=full_count,
        brief=brief_count,
        one_liner=one_liner_count,
    )

    return FormattedDigest(
        subject=subject,
        body=body,
        word_count=word_count,
        story_count=len(stories),
        full_count=full_count,
        brief_count=brief_count,
        one_liner_count=one_liner_count,
    )


def _assign_treatments(
    stories: list[SynthesizedStory],
    word_budget: int,
) -> list[tuple[SynthesizedStory, str]]:
    """
    Assign treatment levels to stories based on available word budget.

    Multi-source stories start as FULL candidates. Single-source stories start
    as BRIEF candidates. If budget is exhausted, remaining stories become one-liners.
    """
    remaining_budget = word_budget
    assigned: list[tuple[SynthesizedStory, str]] = []

    for story in stories:
        if story.source_count >= 2 and remaining_budget >= _FULL_WORD_TARGET:
            assigned.append((story, _FULL))
            remaining_budget -= _FULL_WORD_TARGET
        elif remaining_budget >= _BRIEF_WORD_TARGET:
            assigned.append((story, _BRIEF))
            remaining_budget -= _BRIEF_WORD_TARGET
        else:
            assigned.append((story, _ONE_LINER))

    return assigned


def _build_body(
    assigned: list[tuple[SynthesizedStory, str]],
    digest_type: str,
) -> str:
    """Build the full digest body as plain text."""
    # Group stories by topic, preserving rank order within each topic
    topic_stories: dict[str, list[tuple[SynthesizedStory, str]]] = {t: [] for t in _TOPIC_ORDER}
    one_liners: list[SynthesizedStory] = []

    for story, treatment in assigned:
        if treatment == _ONE_LINER:
            one_liners.append(story)
        else:
            topic = story.topic if story.topic in topic_stories else "other"
            topic_stories[topic].append((story, treatment))

    sections: list[str] = []

    for topic in _TOPIC_ORDER:
        topic_items = topic_stories[topic]
        if not topic_items:
            continue

        header = _TOPIC_HEADERS.get(topic, topic.upper())
        section_lines = [f"--- {header} ---\n"]

        for story, treatment in topic_items:
            section_lines.append(_render_story(story, treatment))

        sections.append("\n".join(section_lines))

    # "Also noted" block for one-liners
    if one_liners:
        also_lines = ["--- Also Noted ---\n"]
        for story in one_liners:
            also_lines.append(f"• {story.title} ({_source_attribution(story)})")
        sections.append("\n".join(also_lines))

    body = "\n\n".join(sections)

    # Footer
    footer = _build_footer(assigned, digest_type)
    return f"{body}\n\n{footer}"


def _render_story(story: SynthesizedStory, treatment: str) -> str:
    """Render a single story block in plain text."""
    attribution = _source_attribution(story)

    if treatment == _FULL:
        return f"{story.title}\n{story.body}\n[{attribution}]\n"

    if treatment == _BRIEF:
        # Truncate body to ~30 words
        words = story.body.split()
        truncated = " ".join(words[:35])
        if len(words) > 35:
            truncated += "..."
        return f"{story.title} — {truncated} [{attribution}]\n"

    # Should not reach here — one-liners handled separately
    return f"• {story.title} [{attribution}]"


def _source_attribution(story: SynthesizedStory) -> str:
    """Format source attribution for a story."""
    sources = story.source_newsletters
    if not sources:
        return "source unknown"
    if len(sources) == 1:
        return sources[0]
    if len(sources) == 2:
        return f"{sources[0]} + {sources[1]}"
    return f"{sources[0]} + {len(sources) - 1} others"


def _build_subject(
    stories: list[SynthesizedStory],
    digest_type: str,
    date_str: str,
) -> str:
    """Build email subject from top story and date."""
    prefix_map = {
        "daily": "Your Daily Brief",
        "deep_read": "Deep Read",
        "weekend": "Weekend Catch-Up",
    }
    prefix = prefix_map.get(digest_type, "Your Brief")
    date_part = f" | {date_str}" if date_str else ""

    if stories:
        top = stories[0].title
        return f"{prefix}{date_part}: {top}"

    return f"{prefix}{date_part}"


def _build_footer(
    assigned: list[tuple[SynthesizedStory, str]],
    digest_type: str,
) -> str:
    """Build the digest footer with story count and reply instructions."""
    story_count = len(assigned)
    full_count = sum(1 for _, t in assigned if t == _FULL)
    return (
        f"---\n"
        f"{story_count} stories | {full_count} in depth\n"
        f"Reply to this email to share feedback or adjust your preferences."
    )


def _load_word_budget(digest_type: str) -> int:
    """
    Load word budget from agent_config.

    Expects agent_config key "word_budget" to be a dict with keys
    "daily", "deep_read", "weekend". Falls back to defaults if missing.
    """
    try:
        raw = get_config("word_budget")
        if isinstance(raw, dict):
            return int(raw.get(digest_type, _DEFAULT_WORD_BUDGET))
    except Exception as e:
        log.warning("formatter_budget_load_failed", error=str(e), action="using default")
    return _DEFAULT_WORD_BUDGET

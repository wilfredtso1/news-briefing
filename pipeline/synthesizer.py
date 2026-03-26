"""
Story synthesizer.

Takes a StoryCluster (one or more newsletter versions of the same event) and
produces a single canonical story with source attribution.

Multi-source clusters: claude-opus-4-6 merges multiple perspectives into one
authoritative synthesis, preserving exact figures, quotes, and key facts.

Single-source clusters: passed through with minimal reformatting — no LLM
call needed when there's only one perspective.

Uses a LCEL chain: ChatPromptTemplate | ChatAnthropic | JsonOutputParser
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import settings
from pipeline.embedder import StoryCluster
from pipeline.extractor import ExtractedStory

log = structlog.get_logger(__name__)

_llm = ChatAnthropic(
    model="claude-opus-4-6",
    api_key=settings.anthropic_api_key,
    max_tokens=1024,
    temperature=0,
)

# Multi-source synthesis: merge N newsletter versions of the same story.
# We send each source's title + body and ask for a single canonical synthesis.
# The sources field is used for attribution in the final digest.
_SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You synthesize multiple newsletter versions of the same news story into one authoritative paragraph.

Rules:
- Preserve ALL specific figures, percentages, dollar amounts, names, and direct quotes exactly as written
- Include the most complete information from all sources — never drop facts
- Write in clear, direct prose. No fluff, no filler phrases
- One paragraph, 3-6 sentences
- Do not mention newsletter names or sources in the body text

Return JSON only:
{{"title": "concise headline under 12 words", "body": "synthesized paragraph", "topic": "one of: AI, markets, policy, health, tech, vc, other"}}""",
    ),
    (
        "human",
        "{sources_block}",
    ),
])

_chain = _SYNTHESIS_PROMPT | _llm | JsonOutputParser()

# Single-source reformatter: normalise formatting without losing information.
_REFORMAT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You reformat a newsletter story into clean prose.

Rules:
- Preserve ALL facts, figures, quotes, and names exactly
- Remove newsletter-specific phrasing ("our take:", "why it matters:", bullet prefixes)
- Write as a clean news paragraph
- One paragraph, 2-5 sentences

Return JSON only:
{{"title": "concise headline under 12 words", "body": "clean paragraph", "topic": "one of: AI, markets, policy, health, tech, vc, other"}}""",
    ),
    (
        "human",
        "Title: {title}\n\n{body}",
    ),
])

_reformat_chain = _REFORMAT_PROMPT | _llm | JsonOutputParser()

# Max chars per source sent to LLM — prevents token overflow on long newsletters
_MAX_SOURCE_CHARS = 600


@dataclass
class SynthesizedStory:
    """A canonical story synthesized from one or more newsletter sources."""
    title: str
    body: str
    topic: str                              # "AI", "markets", "policy", etc.
    source_newsletters: list[str]
    source_emails: list[str]
    key_facts: list[str] = field(default_factory=list)
    cluster_embedding: list[float] = field(default_factory=list)
    source_count: int = 1


def synthesize_clusters(clusters: list[StoryCluster]) -> list[SynthesizedStory]:
    """
    Synthesize all clusters into canonical stories.

    Multi-source clusters use LLM synthesis. Single-source clusters are
    reformatted with a lighter LLM pass to normalise newsletter formatting.

    Returns list of SynthesizedStory objects ready for ranking and formatting.
    """
    results: list[SynthesizedStory] = []

    for cluster in clusters:
        story = _synthesize_cluster(cluster)
        if story:
            results.append(story)

    log.info(
        "synthesizer_complete",
        clusters_in=len(clusters),
        stories_out=len(results),
        multi_source=sum(1 for s in results if s.source_count > 1),
    )
    return results


def _synthesize_cluster(cluster: StoryCluster) -> SynthesizedStory | None:
    """Synthesize a single cluster. Returns None if synthesis fails."""
    source_newsletters = cluster.source_newsletters
    source_emails = list({s.source_email for s in cluster.stories})
    all_key_facts = _merge_key_facts(cluster.stories)

    if len(cluster.stories) == 1:
        return _synthesize_single(
            cluster.stories[0],
            cluster.representative_embedding,
            all_key_facts,
        )

    return _synthesize_multi(
        cluster.stories,
        cluster.representative_embedding,
        source_newsletters,
        source_emails,
        all_key_facts,
    )


def _synthesize_single(
    story: ExtractedStory,
    embedding: list[float],
    key_facts: list[str],
) -> SynthesizedStory | None:
    """Reformat a single-source story into clean prose."""
    try:
        result = _reformat_chain.invoke({
            "title": story.title,
            "body": story.body[:_MAX_SOURCE_CHARS],
        })
        title = result.get("title", story.title).strip()
        body = result.get("body", story.body).strip()
        topic = _normalise_topic(result.get("topic", "other"))
    except Exception as e:
        log.warning(
            "synthesizer_reformat_failed",
            title=story.title[:60],
            error=str(e),
            action="using original text",
        )
        title = story.title
        body = story.body
        topic = "other"

    return SynthesizedStory(
        title=title,
        body=body,
        topic=topic,
        source_newsletters=[story.source_newsletter],
        source_emails=[story.source_email],
        key_facts=key_facts,
        cluster_embedding=embedding,
        source_count=1,
    )


def _synthesize_multi(
    stories: list[ExtractedStory],
    embedding: list[float],
    source_newsletters: list[str],
    source_emails: list[str],
    key_facts: list[str],
) -> SynthesizedStory | None:
    """Merge multiple newsletter versions into one canonical story."""
    sources_block = _build_sources_block(stories)

    try:
        result = _chain.invoke({"sources_block": sources_block})
        title = result.get("title", stories[0].title).strip()
        body = result.get("body", "").strip()
        topic = _normalise_topic(result.get("topic", "other"))

        if not body:
            raise ValueError("empty body in LLM response")

    except Exception as e:
        log.warning(
            "synthesizer_multi_failed",
            story_count=len(stories),
            sources=source_newsletters,
            error=str(e),
            action="falling back to longest source",
        )
        # Fallback: use the longest body as the canonical version
        best = max(stories, key=lambda s: len(s.body))
        title = best.title
        body = best.body
        topic = "other"

    log.info(
        "synthesizer_merged",
        title=title[:60],
        source_count=len(stories),
        sources=source_newsletters,
        topic=topic,
    )

    return SynthesizedStory(
        title=title,
        body=body,
        topic=topic,
        source_newsletters=source_newsletters,
        source_emails=source_emails,
        key_facts=key_facts,
        cluster_embedding=embedding,
        source_count=len(stories),
    )


def _build_sources_block(stories: list[ExtractedStory]) -> str:
    """Format multiple story versions into a single prompt block."""
    parts = []
    for i, story in enumerate(stories, 1):
        parts.append(f"Source {i}: {story.title}\n{story.body[:_MAX_SOURCE_CHARS]}")
    return "\n\n---\n\n".join(parts)


def _merge_key_facts(stories: list[ExtractedStory]) -> list[str]:
    """Deduplicate key facts across all stories in a cluster."""
    seen: set[str] = set()
    merged: list[str] = []
    for story in stories:
        for fact in story.key_facts:
            normalised = fact.strip().lower()
            if normalised not in seen:
                seen.add(normalised)
                merged.append(fact.strip())
    return merged


_VALID_TOPICS = {"ai", "markets", "policy", "health", "tech", "vc", "other"}


def _normalise_topic(topic: str) -> str:
    """Normalise topic to one of the valid set."""
    normalised = topic.strip().lower()
    if normalised in _VALID_TOPICS:
        return normalised
    # Handle common variants
    if "market" in normalised or "finance" in normalised or "crypto" in normalised:
        return "markets"
    if "artificial" in normalised or "machine" in normalised:
        return "ai"
    if "health" in normalised or "pharma" in normalised or "biotech" in normalised:
        return "health"
    if "venture" in normalised or "startup" in normalised or "fund" in normalised:
        return "vc"
    if "tech" in normalised or "software" in normalised:
        return "tech"
    if "law" in normalised or "regulat" in normalised or "govern" in normalised:
        return "policy"
    return "other"

"""
Story enricher — Tavily web search for single-source stories.

Multi-source clusters are already cross-validated across newsletters, so they
don't need enrichment. Single-source stories get one Tavily search to surface
primary sources, official statements, additional data, and context.

One search per story. No additional calls. (See CLAUDE.md conventions.)

The enrichment result is appended to the story body as a context paragraph.
If search fails or returns nothing useful, the story is returned unchanged.
"""

from __future__ import annotations

import structlog
from langchain_community.tools.tavily_search import TavilySearchResults

from config import settings
from pipeline.synthesizer import SynthesizedStory

log = structlog.get_logger(__name__)

_search = TavilySearchResults(
    api_key=settings.tavily_api_key,
    max_results=3,
)

# Max chars to include from each Tavily result in enrichment context
_MAX_RESULT_CHARS = 300


def enrich_stories(stories: list[SynthesizedStory]) -> list[SynthesizedStory]:
    """
    Run Tavily enrichment on single-source stories.

    Multi-source stories are returned unchanged — they're already
    cross-validated across newsletters.

    Returns the full list with single-source stories enriched where possible.
    """
    enriched_count = 0
    results: list[SynthesizedStory] = []

    for story in stories:
        if story.source_count > 1:
            results.append(story)
            continue

        enriched = _enrich_single(story)
        if enriched is not story:
            enriched_count += 1
        results.append(enriched)

    log.info(
        "enricher_complete",
        total_stories=len(stories),
        single_source=sum(1 for s in stories if s.source_count == 1),
        enriched=enriched_count,
    )
    return results


def _enrich_single(story: SynthesizedStory) -> SynthesizedStory:
    """
    Search Tavily for additional context on a single-source story.

    Returns the original story unchanged if search fails or yields nothing useful.
    """
    query = _build_query(story)

    try:
        search_results = _search.invoke(query)
    except Exception as e:
        log.warning(
            "enricher_search_failed",
            title=story.title[:60],
            error=str(e),
            action="returning story unchanged",
        )
        return story

    if not search_results:
        return story

    context = _build_context(search_results)
    if not context:
        return story

    log.debug(
        "enricher_enriched",
        title=story.title[:60],
        result_count=len(search_results),
    )

    # Append context as a new paragraph
    enriched_body = f"{story.body}\n\n{context}"

    return SynthesizedStory(
        title=story.title,
        body=enriched_body,
        topic=story.topic,
        source_newsletters=story.source_newsletters,
        source_emails=story.source_emails,
        key_facts=story.key_facts,
        cluster_embedding=story.cluster_embedding,
        source_count=story.source_count,
    )


def _build_query(story: SynthesizedStory) -> str:
    """
    Build a focused search query from the story title and key facts.

    Using the title alone often returns the same newsletter sources.
    Adding one or two key facts anchors the search to primary sources.
    """
    if story.key_facts:
        # Use title + first key fact for a more targeted query
        return f"{story.title} {story.key_facts[0]}"
    return story.title


def _build_context(search_results: list[dict]) -> str:
    """
    Build a context paragraph from Tavily search results.

    Each result is a dict with keys: url, content, score (and optionally title).
    Only includes results with non-empty content. Returns empty string if nothing useful.
    """
    snippets: list[str] = []
    for result in search_results:
        if not isinstance(result, dict):
            continue
        content = result.get("content", "").strip()
        if content and len(content) > 50:
            snippets.append(content[:_MAX_RESULT_CHARS])

    if not snippets:
        return ""

    # Combine into a concise context paragraph
    return "Additional context: " + " ".join(snippets)

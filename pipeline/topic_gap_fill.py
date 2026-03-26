"""
Topic gap-fill — searches Tavily for agent_config["web_search_topics"] entries
that have no newsletter story coverage in the current run.
"""
from __future__ import annotations

import structlog
from langchain_community.tools.tavily_search import TavilySearchResults

from config import settings
from pipeline.synthesizer import SynthesizedStory, _normalise_topic
from tools.db import get_config
from tools.retry import with_retry

log = structlog.get_logger(__name__)

_MAX_RESULT_CHARS = 300
_search = TavilySearchResults(api_key=settings.tavily_api_key, max_results=3)
_search_with_retry = with_retry(_search.invoke)


def gap_fill_topics(stories: list[SynthesizedStory], run_id: str) -> list[SynthesizedStory]:
    """
    Append SynthesizedStory objects for web_search_topics not covered by newsletters.

    Returns input unchanged when web_search_topics is empty or None. Gap-fill
    stories are always appended AFTER newsletter stories. Tavily failures are
    logged and skipped — other topics continue processing.
    """
    topics: list[str] = get_config("web_search_topics") or []
    if not topics:
        return stories

    covered = {s.topic.lower() for s in stories}
    additions: list[SynthesizedStory] = []

    for topic in topics:
        if topic.lower() in covered:
            log.debug("gap_fill_topic_covered", topic=topic, run_id=run_id)
            continue
        try:
            results = _search_with_retry(f"top news {topic} today")
            if not results:
                continue
            snippets = [
                r.get("content", "")[:_MAX_RESULT_CHARS]
                for r in results
                if isinstance(r, dict) and r.get("content")
            ]
            if not snippets:
                continue
            additions.append(SynthesizedStory(
                title=f"Top {topic.title()} Headlines",
                body=" ".join(snippets[:3]),
                topic=_normalise_topic(topic),
                source_newsletters=[f"Web Search: {topic}"],
                source_emails=["web_search"],
                key_facts=[],
                cluster_embedding=[],
                source_count=1,
            ))
            log.info("gap_fill_complete", topic=topic, run_id=run_id)
        except Exception as e:
            log.warning("gap_fill_failed", topic=topic, run_id=run_id, error=str(e))

    return stories + additions

"""
Story extractor.

Takes a newsletter email body and uses claude-haiku-4-5 to extract individual
news stories. Each story is returned with a title, body text, key facts, and
the source newsletter name.

HTML stripping is handled here before the LLM sees the content, keeping
the prompt focused on text rather than markup.

Uses a LCEL chain: ChatPromptTemplate | ChatAnthropic | JsonOutputParser
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import settings

log = structlog.get_logger(__name__)

# We use haiku for extraction — high volume, structured output, doesn't need Opus reasoning
_llm = ChatAnthropic(
    model="claude-haiku-4-5",
    api_key=settings.anthropic_api_key,
    max_tokens=2048,
    temperature=0,
)

# We ask for JSON with a "stories" array because JsonOutputParser is more
# reliable with a top-level wrapper key than a bare array.
_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You extract individual news stories from newsletter emails.
For each distinct story, return:
- title: concise headline, max 12 words
- body: the full story text as written in the newsletter (do not summarize — preserve the original wording)
- key_facts: list of specific facts to preserve exactly (numbers, percentages, dollar amounts, names, direct quotes)

Rules:
- Only extract actual news stories. Skip promotional content, event announcements, job listings, and sponsor messages.
- If the newsletter has no news stories, return {{"stories": []}}.
- Preserve exact numbers, figures, and quotes in key_facts.

Return valid JSON only, no markdown fences:
{{"stories": [{{"title": "...", "body": "...", "key_facts": ["..."]}}]}}""",
    ),
    (
        "human",
        "Newsletter: {newsletter_name}\n\nContent:\n{content}",
    ),
])

_chain = _EXTRACTION_PROMPT | _llm | JsonOutputParser()

# Max characters to send to the LLM — prevents token overflow on very long newsletters.
# ~8000 chars ≈ ~2000 tokens, well within haiku's context window.
MAX_CONTENT_CHARS = 8_000


@dataclass
class ExtractedStory:
    title: str
    body: str
    key_facts: list[str]
    source_newsletter: str
    source_email: str


def extract_stories(
    body_text: str,
    body_html: str,
    newsletter_name: str,
    sender_email: str,
) -> list[ExtractedStory]:
    """
    Extract individual stories from a newsletter email.

    Prefers plain text body; falls back to HTML-stripped content.
    Returns an empty list if no stories are found or if extraction fails.
    A single extraction failure must not crash the pipeline — callers should
    continue processing other newsletters.
    """
    content = _prepare_content(body_text, body_html)
    if not content:
        log.warning("extractor_empty_content", newsletter=newsletter_name)
        return []

    try:
        result = _chain.invoke({
            "newsletter_name": newsletter_name,
            "content": content[:MAX_CONTENT_CHARS],
        })
        raw_stories = result.get("stories", [])
    except Exception as e:
        log.error(
            "extractor_llm_failed",
            newsletter=newsletter_name,
            error=str(e),
            action="skipping newsletter, continuing pipeline",
        )
        return []

    stories = []
    for raw in raw_stories:
        if not isinstance(raw, dict):
            continue
        title = raw.get("title", "").strip()
        body = raw.get("body", "").strip()
        if not title or not body:
            continue
        stories.append(ExtractedStory(
            title=title,
            body=body,
            key_facts=[str(f) for f in raw.get("key_facts", [])],
            source_newsletter=newsletter_name,
            source_email=sender_email,
        ))

    log.info(
        "extractor_complete",
        newsletter=newsletter_name,
        stories_found=len(stories),
    )
    return stories


def _prepare_content(body_text: str, body_html: str) -> str:
    """
    Return the best available text content from an email.
    Prefers plain text. Falls back to HTML-stripped content.
    Normalises whitespace in both cases.
    """
    if body_text and len(body_text.strip()) > 100:
        return _normalise_whitespace(body_text)
    if body_html:
        return _normalise_whitespace(_strip_html(body_html))
    return body_text.strip()


def _strip_html(html_content: str) -> str:
    """
    Strip HTML tags and decode entities from email HTML.
    Removes script/style blocks first, then strips all remaining tags.
    """
    # Remove script and style blocks entirely
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Replace block-level tags with newlines to preserve paragraph structure
    text = re.sub(r"<(?:p|br|div|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities (&amp; &nbsp; etc.)
    text = html.unescape(text)
    return text


def _normalise_whitespace(text: str) -> str:
    """Collapse runs of whitespace and strip leading/trailing space."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

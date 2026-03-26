"""
Tests for pipeline/synthesizer.py

LLM calls are mocked — never calls real Anthropic API.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.embedder import StoryCluster
from pipeline.extractor import ExtractedStory
from pipeline.synthesizer import (
    SynthesizedStory,
    _build_sources_block,
    _build_system,
    _merge_key_facts,
    _normalise_topic,
    _SYNTHESIS_SYSTEM_BASE,
    _REFORMAT_SYSTEM_BASE,
    synthesize_clusters,
)


# ---------------------------------------------------------------------------
# Auto-mock get_config for all tests that call synthesize_clusters.
# Without this, synthesize_clusters() would attempt a real DB connection.
# Tests that need specific style_notes values override this per-test.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_get_config(request):
    """
    Default: patch get_config to return [] (no style notes) for all synthesizer tests.
    Tests in TestSynthesizeClustersStyleNotes override this themselves via nested patches.
    """
    # Skip autouse mock for tests that manage get_config themselves
    if request.node.cls and request.node.cls.__name__ == "TestSynthesizeClustersStyleNotes":
        yield
        return
    with patch("pipeline.synthesizer.get_config", return_value=[]):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_story(title: str, body: str = "Body text.", newsletter: str = "Morning Brew",
                key_facts: list[str] | None = None) -> ExtractedStory:
    return ExtractedStory(
        title=title,
        body=body,
        key_facts=key_facts or [],
        source_newsletter=newsletter,
        source_email=f"newsletter@example.com",
    )


def _make_cluster(stories: list[ExtractedStory], emb: list[float] | None = None) -> StoryCluster:
    if emb is None:
        emb = [1.0, 0.0, 0.0, 0.0]
    embeddings = [emb] * len(stories)
    return StoryCluster(
        stories=stories,
        embeddings=embeddings,
        is_ambiguous=False,
        representative_embedding=emb,
    )


# ---------------------------------------------------------------------------
# _normalise_topic
# ---------------------------------------------------------------------------

class TestNormaliseTopic:
    def test_valid_topics_pass_through(self):
        for topic in ["ai", "markets", "policy", "health", "tech", "vc", "other"]:
            assert _normalise_topic(topic) == topic

    def test_case_insensitive(self):
        assert _normalise_topic("AI") == "ai"
        assert _normalise_topic("Markets") == "markets"

    def test_variant_terms_mapped_correctly(self):
        assert _normalise_topic("artificial intelligence") == "ai"
        assert _normalise_topic("finance") == "markets"
        assert _normalise_topic("regulation") == "policy"
        assert _normalise_topic("startup") == "vc"
        assert _normalise_topic("biotechnology") == "health"
        assert _normalise_topic("software") == "tech"

    def test_unknown_topic_returns_other(self):
        assert _normalise_topic("sports") == "other"
        assert _normalise_topic("random junk") == "other"


# ---------------------------------------------------------------------------
# _merge_key_facts
# ---------------------------------------------------------------------------

class TestMergeKeyFacts:
    def test_deduplicates_identical_facts(self):
        stories = [
            _make_story("A", key_facts=["$1B raised", "Q1 2026"]),
            _make_story("B", key_facts=["$1B raised", "Series C"]),
        ]
        result = _merge_key_facts(stories)
        assert result.count("$1B raised") == 1
        assert "Q1 2026" in result
        assert "Series C" in result

    def test_returns_empty_for_no_facts(self):
        stories = [_make_story("A"), _make_story("B")]
        assert _merge_key_facts(stories) == []

    def test_case_insensitive_dedup(self):
        stories = [
            _make_story("A", key_facts=["$1B Raised"]),
            _make_story("B", key_facts=["$1b raised"]),
        ]
        result = _merge_key_facts(stories)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _build_sources_block
# ---------------------------------------------------------------------------

class TestBuildSourcesBlock:
    def test_includes_all_source_titles(self):
        stories = [
            _make_story("Fed Holds Rates", newsletter="Axios AM"),
            _make_story("Fed Keeps Rates Unchanged", newsletter="Morning Brew"),
        ]
        block = _build_sources_block(stories)
        assert "Fed Holds Rates" in block
        assert "Fed Keeps Rates Unchanged" in block

    def test_separates_sources_with_divider(self):
        stories = [_make_story("A"), _make_story("B")]
        block = _build_sources_block(stories)
        assert "---" in block

    def test_truncates_long_bodies(self):
        long_body = "x" * 2000
        stories = [_make_story("A", body=long_body)]
        block = _build_sources_block(stories)
        assert len(block) < 2000


# ---------------------------------------------------------------------------
# synthesize_clusters (with mocked LLM)
# ---------------------------------------------------------------------------

class TestSynthesizeClusters:
    def test_single_source_cluster_uses_reformat(self):
        cluster = _make_cluster([_make_story("AI Funding", body="An AI startup raised $500M.")])

        with patch("pipeline.synthesizer._reformat_chain") as mock_chain:
            mock_chain.invoke.return_value = {
                "title": "AI Startup Raises $500M",
                "body": "An AI startup raised $500M in a Series C round.",
                "topic": "ai",
            }
            results = synthesize_clusters([cluster])

        assert len(results) == 1
        assert results[0].source_count == 1
        assert results[0].topic == "ai"
        assert results[0].title == "AI Startup Raises $500M"

    def test_multi_source_cluster_uses_synthesis(self):
        cluster = _make_cluster([
            _make_story("AI Funding", newsletter="Axios AM"),
            _make_story("AI Company Raises Big Round", newsletter="Morning Brew"),
        ])

        with patch("pipeline.synthesizer._chain") as mock_chain:
            mock_chain.invoke.return_value = {
                "title": "AI Startup Raises $500M Series C",
                "body": "A leading AI startup raised $500M.",
                "topic": "ai",
            }
            results = synthesize_clusters([cluster])

        assert len(results) == 1
        assert results[0].source_count == 2
        assert "Axios AM" in results[0].source_newsletters
        assert "Morning Brew" in results[0].source_newsletters

    def test_multi_source_fallback_on_llm_failure(self):
        stories = [
            _make_story("Short story", body="Quick text."),
            _make_story("Longer story version here", body="More detailed text about this important event."),
        ]
        cluster = _make_cluster(stories)

        with patch("pipeline.synthesizer._chain") as mock_chain:
            mock_chain.invoke.side_effect = RuntimeError("LLM error")
            results = synthesize_clusters([cluster])

        # Should fall back to longest source body
        assert len(results) == 1
        assert results[0].body != ""

    def test_preserves_key_facts_from_all_sources(self):
        stories = [
            _make_story("A", key_facts=["$500M raised"]),
            _make_story("B", key_facts=["Series C", "$500M raised"]),
        ]
        cluster = _make_cluster(stories)

        with patch("pipeline.synthesizer._chain") as mock_chain:
            mock_chain.invoke.return_value = {"title": "T", "body": "B", "topic": "vc"}
            results = synthesize_clusters([cluster])

        assert "$500M raised" in results[0].key_facts
        assert "Series C" in results[0].key_facts
        assert results[0].key_facts.count("$500M raised") == 1

    def test_empty_clusters_returns_empty_list(self):
        assert synthesize_clusters([]) == []

    def test_source_emails_collected(self):
        stories = [
            ExtractedStory("A", "Body", [], "Morning Brew", "brew@brew.com"),
            ExtractedStory("B", "Body", [], "Axios", "axios@axios.com"),
        ]
        cluster = _make_cluster(stories)

        with patch("pipeline.synthesizer._chain") as mock_chain:
            mock_chain.invoke.return_value = {"title": "T", "body": "B", "topic": "ai"}
            results = synthesize_clusters([cluster])

        assert "brew@brew.com" in results[0].source_emails
        assert "axios@axios.com" in results[0].source_emails


# ---------------------------------------------------------------------------
# _build_system
# ---------------------------------------------------------------------------

class TestBuildSystem:
    def test_empty_style_notes_returns_base_unchanged(self):
        result = _build_system(_SYNTHESIS_SYSTEM_BASE, [])
        assert result == _SYNTHESIS_SYSTEM_BASE

    def test_empty_list_returns_base_unchanged(self):
        result = _build_system(_REFORMAT_SYSTEM_BASE, [])
        assert result == _REFORMAT_SYSTEM_BASE

    def test_style_notes_injected_before_json_line(self):
        notes = ["write shorter stories", "use active voice"]
        result = _build_system(_SYNTHESIS_SYSTEM_BASE, notes)
        assert "Additional style instructions:" in result
        assert "- write shorter stories" in result
        assert "- use active voice" in result
        # JSON format line must still be present and at the end
        assert result.strip().endswith('"topic": "one of: AI, markets, policy, health, tech, vc, other"}}')

    def test_style_notes_appear_before_json_line(self):
        notes = ["be concise"]
        result = _build_system(_SYNTHESIS_SYSTEM_BASE, notes)
        notes_pos = result.index("Additional style instructions:")
        json_pos = result.index("Return JSON only:")
        assert notes_pos < json_pos


# ---------------------------------------------------------------------------
# synthesize_clusters with style_notes (mocked get_config + LLM)
# ---------------------------------------------------------------------------

class TestSynthesizeClustersStyleNotes:
    def test_style_notes_injected_into_single_source_system_prompt(self):
        """Non-empty style_notes → _build_system called with notes for single-source path."""
        cluster = _make_cluster([_make_story("AI Funding")])
        notes = ["write shorter stories"]
        build_calls: list[tuple] = []

        def fake_build(base, style_notes):
            build_calls.append((base, style_notes))
            # Return unchanged base so the dynamic chain still gets a valid system string
            return base

        with patch("pipeline.synthesizer.get_config", return_value=notes), \
             patch("pipeline.synthesizer._build_system", side_effect=fake_build), \
             patch("pipeline.synthesizer._reformat_chain") as mock_static_chain:
            mock_static_chain.invoke.return_value = {"title": "T", "body": "B", "topic": "ai"}
            # dynamic chain will fail (no real LLM), fallback fires — that's OK
            synthesize_clusters([cluster])

        assert build_calls, "_build_system was not called at all"
        assert build_calls[0][1] == notes, f"style_notes not passed: {build_calls[0][1]}"

    def test_style_notes_injected_into_multi_source_system_prompt(self):
        """Non-empty style_notes → _build_system called with notes for multi-source path."""
        cluster = _make_cluster([
            _make_story("AI Funding", newsletter="Axios AM"),
            _make_story("AI Company Raises", newsletter="Morning Brew"),
        ])
        notes = ["be concise"]
        build_calls: list[tuple] = []

        def fake_build(base, style_notes):
            build_calls.append((base, style_notes))
            return base

        with patch("pipeline.synthesizer.get_config", return_value=notes), \
             patch("pipeline.synthesizer._build_system", side_effect=fake_build), \
             patch("pipeline.synthesizer._chain") as mock_static_chain:
            mock_static_chain.invoke.return_value = {"title": "T", "body": "B", "topic": "ai"}
            synthesize_clusters([cluster])

        assert build_calls, "_build_system was not called at all"
        assert build_calls[0][1] == notes

    def test_empty_style_notes_uses_static_chain_unchanged(self):
        """Empty style_notes → module-level static chain used directly."""
        cluster = _make_cluster([_make_story("AI Funding")])

        with patch("pipeline.synthesizer.get_config", return_value=[]), \
             patch("pipeline.synthesizer._reformat_chain") as mock_chain:
            mock_chain.invoke.return_value = {
                "title": "T", "body": "B", "topic": "ai"
            }
            results = synthesize_clusters([cluster])

        mock_chain.invoke.assert_called_once()

    def test_empty_style_notes_does_not_call_build_system(self):
        """Empty style_notes → _build_system never called (hot path unchanged)."""
        cluster = _make_cluster([_make_story("AI Funding")])

        with patch("pipeline.synthesizer.get_config", return_value=[]), \
             patch("pipeline.synthesizer._build_system") as mock_build, \
             patch("pipeline.synthesizer._reformat_chain") as mock_chain:
            mock_chain.invoke.return_value = {"title": "T", "body": "B", "topic": "ai"}
            synthesize_clusters([cluster])

        mock_build.assert_not_called()

    def test_get_config_called_once_per_synthesize_clusters_call(self):
        """get_config must be called once per synthesize_clusters() call, not once per story."""
        clusters = [
            _make_cluster([_make_story("Story A")]),
            _make_cluster([_make_story("Story B")]),
            _make_cluster([_make_story("Story C")]),
        ]

        with patch("pipeline.synthesizer.get_config", return_value=[]) as mock_get_config, \
             patch("pipeline.synthesizer._reformat_chain") as mock_chain:
            mock_chain.invoke.return_value = {"title": "T", "body": "B", "topic": "ai"}
            synthesize_clusters(clusters)

        # Must be called exactly once regardless of how many clusters there are
        assert mock_get_config.call_count == 1

    def test_none_style_notes_uses_static_chain(self):
        """get_config returning None → treated as empty, static chain used."""
        cluster = _make_cluster([_make_story("AI Funding")])

        with patch("pipeline.synthesizer.get_config", return_value=None), \
             patch("pipeline.synthesizer._reformat_chain") as mock_chain:
            mock_chain.invoke.return_value = {"title": "T", "body": "B", "topic": "ai"}
            results = synthesize_clusters([cluster])

        mock_chain.invoke.assert_called_once()

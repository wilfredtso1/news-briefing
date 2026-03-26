"""
Tests for pipeline/embedder.py

Embedding generation is mocked — tests focus on clustering and dedup logic.
"""

from unittest.mock import patch

import pytest

from pipeline.embedder import (
    StoryCluster,
    _cluster,
    _cosine_similarity,
    _filter_already_covered,
    _mean_embedding,
    embed_and_cluster,
    HIGH_SIMILARITY_THRESHOLD,
    LOW_SIMILARITY_THRESHOLD,
)
from pipeline.extractor import ExtractedStory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_story(title: str, newsletter: str = "Morning Brew") -> ExtractedStory:
    return ExtractedStory(
        title=title,
        body=f"Body of {title}",
        key_facts=[],
        source_newsletter=newsletter,
        source_email=f"{newsletter.lower().replace(' ', '')}@example.com",
    )


def _unit_vec(n: int, dims: int = 4) -> list[float]:
    """Return a unit vector with 1.0 at position n and 0 elsewhere."""
    v = [0.0] * dims
    v[n % dims] = 1.0
    return v


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors_return_1(self):
        v = [1.0, 0.5, 0.25]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors_return_0(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors_return_minus_1(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) + 1.0) < 1e-6

    def test_zero_vector_returns_0(self):
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_partial_similarity(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        sim = _cosine_similarity(a, b)
        assert 0.5 < sim < 1.0


# ---------------------------------------------------------------------------
# _mean_embedding
# ---------------------------------------------------------------------------

class TestMeanEmbedding:
    def test_mean_of_two_embeddings(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        result = _mean_embedding([a, b])
        assert abs(result[0] - 0.5) < 1e-6
        assert abs(result[1] - 0.5) < 1e-6

    def test_mean_of_single_embedding(self):
        a = [1.0, 2.0, 3.0]
        result = _mean_embedding([a])
        assert result == pytest.approx(a)


# ---------------------------------------------------------------------------
# _cluster
# ---------------------------------------------------------------------------

class TestCluster:
    def test_identical_embeddings_grouped_together(self):
        stories = [_make_story("A"), _make_story("B")]
        embs = [[1.0, 0.0], [1.0, 0.0]]  # identical → similarity = 1.0
        clusters = _cluster(stories, embs, threshold=0.82)
        assert len(clusters) == 1
        assert len(clusters[0].stories) == 2

    def test_orthogonal_embeddings_kept_separate(self):
        stories = [_make_story("A"), _make_story("B")]
        embs = [[1.0, 0.0], [0.0, 1.0]]  # orthogonal → similarity = 0.0
        clusters = _cluster(stories, embs, threshold=0.82)
        assert len(clusters) == 2

    def test_ambiguous_pairs_flagged(self):
        # Similarity between 0.70 and 0.88 → ambiguous
        import math
        # Two vectors with ~0.79 cosine similarity
        angle = math.radians(37)  # cos(37°) ≈ 0.799
        a = [1.0, 0.0]
        b = [math.cos(angle), math.sin(angle)]
        stories = [_make_story("A"), _make_story("B")]
        clusters = _cluster(stories, [a, b], threshold=0.82)
        # They should be in one cluster flagged as ambiguous
        assert len(clusters) == 1
        assert clusters[0].is_ambiguous is True

    def test_single_story_forms_single_cluster(self):
        stories = [_make_story("A")]
        embs = [[1.0, 0.0, 0.0, 0.0]]
        clusters = _cluster(stories, embs, threshold=0.82)
        assert len(clusters) == 1
        assert clusters[0].is_ambiguous is False

    def test_already_assigned_story_not_double_grouped(self):
        # Three identical stories — should form one cluster, not 3
        stories = [_make_story("A"), _make_story("B"), _make_story("C")]
        embs = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
        clusters = _cluster(stories, embs, threshold=0.82)
        assert len(clusters) == 1
        assert len(clusters[0].stories) == 3

    def test_representative_embedding_is_mean(self):
        stories = [_make_story("A"), _make_story("B")]
        embs = [[1.0, 0.0], [1.0, 0.0]]
        clusters = _cluster(stories, embs, threshold=0.82)
        assert clusters[0].representative_embedding == pytest.approx([1.0, 0.0])

    def test_cluster_preserves_source_newsletters(self):
        stories = [
            _make_story("Story A", "Morning Brew"),
            _make_story("Story B", "Axios AM"),
        ]
        embs = [[1.0, 0.0], [1.0, 0.0]]
        clusters = _cluster(stories, embs, threshold=0.82)
        newsletters = clusters[0].source_newsletters
        assert "Morning Brew" in newsletters
        assert "Axios AM" in newsletters


# ---------------------------------------------------------------------------
# _filter_already_covered
# ---------------------------------------------------------------------------

class TestFilterAlreadyCovered:
    def test_story_above_threshold_is_filtered(self):
        stories = [_make_story("AI story")]
        embs = [[1.0, 0.0]]
        recent = [{"embedding": [1.0, 0.0]}]  # identical
        kept_s, kept_e = _filter_already_covered(stories, embs, recent, threshold=0.82)
        assert len(kept_s) == 0

    def test_story_below_threshold_is_kept(self):
        stories = [_make_story("New story")]
        embs = [[1.0, 0.0]]
        recent = [{"embedding": [0.0, 1.0]}]  # orthogonal
        kept_s, kept_e = _filter_already_covered(stories, embs, recent, threshold=0.82)
        assert len(kept_s) == 1

    def test_empty_recent_keeps_all_stories(self):
        stories = [_make_story("A"), _make_story("B")]
        embs = [[1.0, 0.0], [0.0, 1.0]]
        kept_s, kept_e = _filter_already_covered(stories, embs, [], threshold=0.82)
        assert len(kept_s) == 2

    def test_recent_without_embeddings_keeps_all_stories(self):
        stories = [_make_story("A")]
        embs = [[1.0, 0.0]]
        recent = [{"embedding": None}, {"id": "123"}]
        kept_s, kept_e = _filter_already_covered(stories, embs, recent, threshold=0.82)
        assert len(kept_s) == 1


# ---------------------------------------------------------------------------
# embed_and_cluster (integration — mocked embedding model and DB)
# ---------------------------------------------------------------------------

class TestEmbedAndCluster:
    def test_returns_empty_for_no_stories(self):
        result = embed_and_cluster([])
        assert result == []

    def test_clusters_returned_for_stories(self):
        stories = [_make_story("AI story"), _make_story("Market update")]

        with patch("pipeline.embedder._embeddings_model") as mock_model, \
             patch("pipeline.embedder.get_recent_story_embeddings", return_value=[]):
            mock_model.embed_documents.return_value = [
                [1.0, 0.0, 0.0, 0.0],  # AI story
                [0.0, 1.0, 0.0, 0.0],  # Market update — orthogonal → separate cluster
            ]
            clusters = embed_and_cluster(stories)

        assert len(clusters) == 2
        assert all(isinstance(c, StoryCluster) for c in clusters)

    def test_propagates_embedding_failure(self):
        stories = [_make_story("A")]

        with patch("pipeline.embedder._embeddings_model") as mock_model, \
             patch("pipeline.embedder.get_recent_story_embeddings", return_value=[]):
            mock_model.embed_documents.side_effect = RuntimeError("Voyage API down")

            with pytest.raises(RuntimeError, match="Voyage API down"):
                embed_and_cluster(stories)

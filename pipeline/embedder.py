"""
Story embedder and clusterer.

Embeds extracted stories using Voyage AI (voyage-3, 1024 dimensions) and
groups them into clusters via cosine similarity. Stories above the similarity
threshold are considered the same real-world story.

Also handles cross-day deduplication: stories already covered in recent digests
are identified and excluded before synthesis, preventing the same story
appearing in consecutive daily briefs.

Clustering algorithm: greedy O(n²) grouping — fine for our data size (40-80
stories per run). Does not require pre-training unlike IVFFlat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import structlog
from langchain_voyageai import VoyageAIEmbeddings

from config import settings
from pipeline.extractor import ExtractedStory
from tools.db import get_recent_story_embeddings

log = structlog.get_logger(__name__)

# Thresholds for automatic merge/split decisions.
# Stories with similarity above HIGH_THRESHOLD are merged without LLM.
# Stories below LOW_THRESHOLD are kept separate without LLM.
# Stories in between are sent to the disambiguator.
# We use 0.82 as the default (from agent_config) — see DECISIONS.md 2026-03-26.
HIGH_SIMILARITY_THRESHOLD = 0.88
LOW_SIMILARITY_THRESHOLD = 0.70

_embeddings_model = VoyageAIEmbeddings(
    voyage_api_key=settings.voyage_api_key,
    model="voyage-3",
)


@dataclass
class StoryCluster:
    """A group of stories from different newsletters covering the same event."""
    stories: list[ExtractedStory]
    embeddings: list[list[float]]
    is_ambiguous: bool = False      # True if similarity was in the middle zone
    representative_embedding: list[float] = field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len(self.stories)

    @property
    def is_single_source(self) -> bool:
        return len(self.stories) == 1

    @property
    def source_newsletters(self) -> list[str]:
        return list({s.source_newsletter for s in self.stories})


def embed_and_cluster(
    stories: list[ExtractedStory],
    similarity_threshold: float | None = None,
) -> list[StoryCluster]:
    """
    Embed all stories and group them into clusters by cosine similarity.

    Returns a list of StoryCluster objects. Each cluster represents one
    real-world story, potentially covered by multiple newsletters.

    Filters out stories already covered in recent digests (cross-day dedup).
    Ambiguous clusters (similarity in the middle zone) are flagged for
    downstream LangGraph disambiguation.
    """
    if not stories:
        return []

    threshold = similarity_threshold or settings.cosine_similarity_threshold

    # Embed all stories in one batched call — don't embed one at a time
    texts = [f"{s.title}\n{s.body[:500]}" for s in stories]
    try:
        embeddings = _embeddings_model.embed_documents(texts)
    except Exception as e:
        log.error("embedder_voyage_failed", error=str(e), story_count=len(stories))
        raise

    log.info("embedder_embedded", story_count=len(stories))

    # Cross-day dedup: check against recent stories already in the DB
    recent = get_recent_story_embeddings(days_back=2)
    new_stories, new_embeddings = _filter_already_covered(stories, embeddings, recent, threshold)

    if len(new_stories) < len(stories):
        log.info(
            "embedder_deduped_cross_day",
            original=len(stories),
            after_dedup=len(new_stories),
            removed=len(stories) - len(new_stories),
        )

    if not new_stories:
        return []

    clusters = _cluster(new_stories, new_embeddings, threshold)
    log.info("embedder_clustered", story_count=len(new_stories), cluster_count=len(clusters))
    return clusters


def _filter_already_covered(
    stories: list[ExtractedStory],
    embeddings: list[list[float]],
    recent: list[dict],
    threshold: float,
) -> tuple[list[ExtractedStory], list[list[float]]]:
    """
    Remove stories that are too similar to stories in recent digests.
    Returns filtered (stories, embeddings) tuples.
    """
    if not recent:
        return stories, embeddings

    recent_vecs = [r["embedding"] for r in recent if r.get("embedding")]
    if not recent_vecs:
        return stories, embeddings

    kept_stories = []
    kept_embeddings = []

    for story, emb in zip(stories, embeddings):
        max_sim = max(_cosine_similarity(emb, rv) for rv in recent_vecs)
        if max_sim >= threshold:
            log.debug(
                "embedder_story_already_covered",
                title=story.title,
                similarity=round(max_sim, 3),
            )
        else:
            kept_stories.append(story)
            kept_embeddings.append(emb)

    return kept_stories, kept_embeddings


def _cluster(
    stories: list[ExtractedStory],
    embeddings: list[list[float]],
    threshold: float,
) -> list[StoryCluster]:
    """
    Greedy clustering: iterate through stories, group each with all unassigned
    stories above the similarity threshold.

    Stories with pairwise similarity in (LOW_SIMILARITY_THRESHOLD, HIGH_SIMILARITY_THRESHOLD)
    are flagged as ambiguous for downstream LangGraph resolution.
    """
    n = len(stories)
    assigned = [False] * n
    clusters: list[StoryCluster] = []

    for i in range(n):
        if assigned[i]:
            continue

        cluster_indices = [i]
        assigned[i] = True
        is_ambiguous = False

        for j in range(i + 1, n):
            if assigned[j]:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim >= HIGH_SIMILARITY_THRESHOLD:
                cluster_indices.append(j)
                assigned[j] = True
            elif sim >= LOW_SIMILARITY_THRESHOLD:
                # Middle zone — flag for disambiguation but include tentatively
                cluster_indices.append(j)
                assigned[j] = True
                is_ambiguous = True
                log.debug(
                    "embedder_ambiguous_pair",
                    story_a=stories[i].title[:60],
                    story_b=stories[j].title[:60],
                    similarity=round(sim, 3),
                )

        cluster_embeddings = [embeddings[idx] for idx in cluster_indices]
        representative = _mean_embedding(cluster_embeddings)

        clusters.append(StoryCluster(
            stories=[stories[idx] for idx in cluster_indices],
            embeddings=cluster_embeddings,
            is_ambiguous=is_ambiguous,
            representative_embedding=representative,
        ))

    return clusters


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def _mean_embedding(embeddings: list[list[float]]) -> list[float]:
    """Compute the mean of a list of embeddings (representative cluster vector)."""
    arr = np.array(embeddings, dtype=np.float32)
    return arr.mean(axis=0).tolist()

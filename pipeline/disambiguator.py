"""
Cluster disambiguator — LangGraph StateGraph.

Resolves borderline cluster merges where cosine similarity fell in the middle
zone (LOW_SIMILARITY_THRESHOLD to HIGH_SIMILARITY_THRESHOLD). The embedder
flags these clusters as ambiguous; this module decides whether to keep them
merged or split them.

Graph structure:
  START → evaluate → (auto_merge | auto_split | llm_decide) → END

- auto_merge: similarity is high enough, no LLM needed
- auto_split: similarity is too low, split without LLM
- llm_decide: borderline case, use claude-opus-4-6 to reason

Why LangGraph (not LCEL):
  The resolution requires a conditional routing step and potential branching
  based on the LLM's structured output. LCEL is for linear chains; LangGraph
  handles this conditional flow cleanly. See CLAUDE.md Non-Obvious Design Decisions.
"""

from __future__ import annotations

from typing import TypedDict

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from config import settings
from pipeline.embedder import (
    HIGH_SIMILARITY_THRESHOLD,
    LOW_SIMILARITY_THRESHOLD,
    StoryCluster,
    _cosine_similarity,
    _mean_embedding,
)

log = structlog.get_logger(__name__)

_llm = ChatAnthropic(
    model="claude-opus-4-6",
    api_key=settings.anthropic_api_key,
    max_tokens=512,
    temperature=0,
)

# We instruct the LLM to return a simple JSON decision object.
# The reasoning field is kept for LangSmith tracing and DECISIONS.md context.
_DISAMBIGUATE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You decide whether two news stories are about the same real-world event.

Return JSON only:
{{"decision": "merge" | "split", "reasoning": "one sentence explanation"}}

Merge if: same event, same company/person, same announcement — even if written differently.
Split if: different events, different time periods, or only superficially related topics.""",
    ),
    (
        "human",
        "Story A: {title_a}\n{body_a}\n\nStory B: {title_b}\n{body_b}",
    ),
])

_chain = _DISAMBIGUATE_PROMPT | _llm | JsonOutputParser()


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class DisambiguatorState(TypedDict):
    title_a: str
    body_a: str
    title_b: str
    body_b: str
    similarity: float
    decision: str       # "merge" or "split"
    reasoning: str


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def evaluate_node(state: DisambiguatorState) -> DisambiguatorState:
    """Route based on similarity score. Sets decision for clear-cut cases."""
    sim = state["similarity"]
    if sim >= HIGH_SIMILARITY_THRESHOLD:
        return {**state, "decision": "merge", "reasoning": f"similarity {sim:.3f} above high threshold"}
    if sim < LOW_SIMILARITY_THRESHOLD:
        return {**state, "decision": "split", "reasoning": f"similarity {sim:.3f} below low threshold"}
    # Middle zone — leave decision empty for llm_decide node
    return state


def llm_decide_node(state: DisambiguatorState) -> DisambiguatorState:
    """Use claude-opus-4-6 to resolve borderline cases."""
    try:
        result = _chain.invoke({
            "title_a": state["title_a"],
            "body_a": state["body_a"][:400],
            "title_b": state["title_b"],
            "body_b": state["body_b"][:400],
        })
        decision = result.get("decision", "split")
        reasoning = result.get("reasoning", "")
        # Normalise — LLM might return "merge" or "split" with different casing
        decision = "merge" if "merge" in decision.lower() else "split"
    except Exception as e:
        log.warning("disambiguator_llm_failed", error=str(e), action="defaulting to split")
        decision = "split"
        reasoning = f"LLM failed: {e}"

    log.info(
        "disambiguator_decided",
        title_a=state["title_a"][:60],
        title_b=state["title_b"][:60],
        similarity=round(state["similarity"], 3),
        decision=decision,
        reasoning=reasoning,
    )
    return {**state, "decision": decision, "reasoning": reasoning}


def route_after_evaluate(state: DisambiguatorState) -> str:
    """Conditional edge: route to llm_decide if not yet resolved, else END."""
    if state.get("decision"):
        return END
    return "llm_decide"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

_graph_builder = StateGraph(DisambiguatorState)
_graph_builder.add_node("evaluate", evaluate_node)
_graph_builder.add_node("llm_decide", llm_decide_node)
_graph_builder.add_edge(START, "evaluate")
_graph_builder.add_conditional_edges("evaluate", route_after_evaluate)
_graph_builder.add_edge("llm_decide", END)
_disambiguator = _graph_builder.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_ambiguous_clusters(clusters: list[StoryCluster]) -> list[StoryCluster]:
    """
    Run disambiguation on any clusters flagged as ambiguous by the embedder.
    Non-ambiguous clusters are returned unchanged.

    For ambiguous clusters with more than 2 stories, we evaluate each pair
    of stories against the first story and split out any that should be separate.

    Returns the final resolved list of clusters.
    """
    resolved: list[StoryCluster] = []

    for cluster in clusters:
        if not cluster.is_ambiguous or len(cluster.stories) < 2:
            # Clear case — no disambiguation needed
            resolved.append(StoryCluster(
                stories=cluster.stories,
                embeddings=cluster.embeddings,
                is_ambiguous=False,
                representative_embedding=cluster.representative_embedding,
            ))
            continue

        resolved.extend(_resolve_cluster(cluster))

    return resolved


def _resolve_cluster(cluster: StoryCluster) -> list[StoryCluster]:
    """
    For an ambiguous cluster, evaluate each story (2nd onward) against the first.
    Stories that should be split are returned as separate single-story clusters.
    Stories confirmed as the same event stay merged.
    """
    anchor_story = cluster.stories[0]
    anchor_emb = cluster.embeddings[0]
    merged_stories = [anchor_story]
    merged_embeddings = [anchor_emb]
    split_off: list[StoryCluster] = []

    for story, emb in zip(cluster.stories[1:], cluster.embeddings[1:]):
        sim = _cosine_similarity(anchor_emb, emb)
        state: DisambiguatorState = {
            "title_a": anchor_story.title,
            "body_a": anchor_story.body,
            "title_b": story.title,
            "body_b": story.body,
            "similarity": sim,
            "decision": "",
            "reasoning": "",
        }
        result = _disambiguator.invoke(state)

        if result["decision"] == "merge":
            merged_stories.append(story)
            merged_embeddings.append(emb)
        else:
            split_off.append(StoryCluster(
                stories=[story],
                embeddings=[emb],
                is_ambiguous=False,
                representative_embedding=emb,
            ))

    main_cluster = StoryCluster(
        stories=merged_stories,
        embeddings=merged_embeddings,
        is_ambiguous=False,
        representative_embedding=_mean_embedding(merged_embeddings),
    )
    return [main_cluster] + split_off

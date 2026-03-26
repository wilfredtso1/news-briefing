# Changelog

## [Unreleased] — Phase 3/4/5 (in progress)

### In Progress
- `supervisor/immediate.py` — LangGraph immediate supervisor: reply classification, config updates, unsubscribe executor
- `pipeline/weekend_catchup.py` — Sunday catch-up pipeline drawing from unacknowledged stories
- `pipeline/deep_read.py` — Long-form queue pipeline with threshold trigger
- `tools/tracing.py` — LangSmith tracing decorator for all LLM calls
- `tools/retry.py` — Retry wrapper with retryable vs. fatal error discrimination
- `tools/alerts.py` — Alert email on pipeline failure after retries exhausted

---

## [Phase 2 — Core Pipeline] — 2026-03-26

### Added
- Phase 2 core pipeline: full daily brief pipeline from email fetch → extraction → embedding → disambiguation → synthesis → enrichment → ranking → formatting → delivery. E2E tested against real Gmail inbox.
- `pipeline/extractor.py` — LCEL chain (claude-haiku-4-5) extracts structured stories from newsletter HTML/text; graceful failure per-newsletter with pipeline continuing
- `pipeline/embedder.py` — Voyage AI voyage-3 embeddings with greedy cosine-similarity clustering; cross-day dedup against recent digest embeddings; ambiguous pairs flagged for LangGraph resolution
- `pipeline/disambiguator.py` — LangGraph StateGraph with auto-merge/split thresholds and claude-opus-4-6 for borderline cases
- `pipeline/synthesizer.py` — LCEL chain (claude-opus-4-6) merges multi-source clusters into canonical stories; single-source stories reformatted with lighter pass; key facts deduplicated across sources
- `pipeline/enricher.py` — Tavily web search enrichment for single-source stories only; one search per story, appended as context paragraph
- `pipeline/ranker.py` — scores stories by topic weight (from agent_config) + source count bonus; weights hot-reloaded from DB so supervisor can adjust without restart
- `pipeline/formatter.py` — tiered treatment (full/brief/one-liner) respecting word budget from agent_config; topic-grouped sections; plain text only
- `pipeline/daily_brief.py` — orchestrator wiring all pipeline stages; persists digest + stories to DB after delivery; anchor check still in main.py
- `main.py` — `_run_daily_brief` now calls full pipeline instead of stub
- 84 new tests across extractor, embedder, synthesizer, ranker, formatter — 124 total passing

---

## [Phase 1 — Foundation]

### Added
- Phase 1 foundation: Gmail service wrapper, source classifier, DB schema and helpers, FastAPI job endpoint skeleton
- `config.py` validates all required env vars at startup and crashes immediately with a clear message listing all missing vars
- `schema.sql` creates all 6 tables (newsletter_sources, digests, story_clusters, stories, feedback_events, agent_config) with pgvector HNSW index and seeded baseline agent_config values
- `gmail_service.py` wraps Gmail API v1 for reading, archiving, sending, thread reply detection, and anchor source polling — no LangChain GmailLoader dependency
- `source_classifier.py` detects newsletters via List-Unsubscribe header, List-Id header, and known sender matching; classifies as news_brief or long_form by body length; upserts into newsletter_sources registry
- `main.py` FastAPI app with job endpoints for all 5 pipeline types, triggerable by Railway cron or manual HTTP call
- Full unit test suite for source_classifier (25 tests) and gmail_service pure helpers; DB integration tests gated behind TEST_DATABASE_URL
- `DECISIONS.md`, `TODO.md` project tracking files seeded

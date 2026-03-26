# Changelog

## [Unreleased] — Integration Sprint

### Pending Integration
- Thread `@traced` / `with_retry` / `send_alert` through all pipeline orchestrators
- Schema migration: add `thread_id` and `sent_message_id` columns to `digests` table
- Merge branches: phase-5-infra → phase-3-supervisor → phase-4-pipelines → main
- E2E validation: supervisor reply processing against real Gmail; weekend_catchup + deep_read against live DB

---

## [Phase 5 — Infrastructure] — 2026-03-26

### Added
- `tools/tracing.py` — `@traced(name)` decorator wrapping sync/async callables; no-op when LANGSMITH_API_KEY absent or langsmith not installed; uses functools.wraps to preserve metadata
- `tools/retry.py` — `with_retry(fn, max_attempts=3, delay=5)` for sync and async; fatal errors (ValueError, TypeError, AuthenticationError) re-raise immediately; all other errors retry up to max_attempts with delay between attempts
- `tools/alerts.py` — `send_alert(pipeline_name, error, run_id)` sends plain-text alert email via gmail_service; silent no-op if ALERT_EMAIL not set; catches all gmail_service exceptions to never re-raise

### Fixed
- Removed dead `_is_retryable()` function from retry.py — defined but never called; actual retry logic only uses `_is_fatal()`

---

## [Phase 4 — Weekend Catch-Up & Deep Read] — 2026-03-26

### Added
- `pipeline/weekend_catchup.py` — Sunday catch-up pipeline: queries unacknowledged daily brief stories (6 days back), cross-day dedup via DISTINCT ON cluster_id (DB level, no re-embedding), reranks by importance via ranker.py, formats at 30-min word budget, delivers via Gmail; dry_run mode for testing
- `pipeline/deep_read.py` — Long-form queue pipeline: fetches unread emails from active long_form sources, checks threshold from agent_config (Thursday fallback), caps at 5 articles, aborts if fewer than 3 extracted; preserves original article voice (no synthesis); original links extracted from HTML
- `tests/test_weekend_catchup.py` — 20 unit tests + 2 `@pytest.mark.e2e` tests covering all orchestration paths, DB row conversion, error modes
- `tests/test_deep_read.py` — unit tests covering source fetching, threshold checks, URL extraction, and dry_run behaviour

### Fixed
- Removed dead `_load_weekend_word_budget()` function and unused `get_config` import from weekend_catchup.py — format_digest reads the word budget internally via digest_type

---

## [Phase 3 — Acknowledgment & Immediate Supervisor] — 2026-03-26

### Added
- `supervisor/immediate.py` — LangGraph StateGraph with sequential routing: classify_reply (Haiku) → maybe_acknowledge → extract_change (Haiku) → validate_change → apply_change|queue_change → log_feedback_event; LOW_RISK_CONFIG_KEYS = {topic_weights, word_budget, cosine_similarity_threshold}; high-risk changes (prompt_edit, unsubscribe, source_change, unknown keys) queued for human review
- `supervisor/__init__.py` — exports SupervisorResult dataclass and run_immediate_supervisor
- `main.py` `_run_poll_replies()` — polls unacknowledged digests (7 days back) for Gmail thread replies; runs each reply through immediate supervisor; single-reply failures are non-fatal; digests without thread_id skipped (schema gap noted)
- `tests/test_supervisor_immediate.py` — 64 tests: full graph tests for all reply types and risk levels, node-level unit tests, routing function tests, SupervisorResult dataclass contract, LOW_RISK_CONFIG_KEYS guard

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

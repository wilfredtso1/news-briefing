# Changelog

## [End-to-End Reliability + Testing Harness] — 2026-03-26

### Fixed
- **Daily brief never ran past anchor wait** — `anchor_cutoff_hour` was configured but never checked. If Axios AM or Morning Brew didn't arrive, the brief silently skipped every poll cycle including the 10am hard cutoff. `_run_daily_brief()` now compares `datetime.now().hour` against `settings.anchor_cutoff_hour` and runs the pipeline unconditionally once the cutoff is reached.

### Added
- **`tests/test_daily_brief.py`** — 24 new tests covering the full pipeline (previously had 0 tests):
  - Happy path: email sent, newsletters archived, digest persisted to DB
  - Early returns: no messages, no newsletters, no stories
  - Resilience: single-newsletter extraction failure skips that newsletter, pipeline continues
  - Failed newsletter not archived (prevents losing emails silently)
  - dry_run mode: no send, no archive, no DB write
  - Anchor cutoff: 5 tests covering before/at/after cutoff and anchors-present cases

---

## [Web App — Multi-User Frontend] — 2026-03-26

### Added
- **React SPA wired to real backend** — Alloy/Paper-designed React app (`web/`) connected to new FastAPI endpoints. Google OAuth flow replaces mock sign-in; setup form POSTs to real API; account page shows live user status and last brief time.
- **Google OAuth sign-in** — `GET /auth/google` redirects to Google consent screen; `GET /auth/google/callback` exchanges code for tokens, upserts user record, sets a signed session cookie (30-day expiry), redirects to `/setup` (new user) or `/account` (returning user).
- **Session management** — `itsdangerous.URLSafeSerializer` signs session cookies with `SESSION_SECRET_KEY`. `_require_session()` helper validates cookie on every protected endpoint, raises 401 if missing or stale.
- **User management endpoints** — `GET /api/me` (profile + status), `POST /api/setup` (saves delivery email + timezone, triggers onboarding), `POST /api/pause` (pauses briefings), `DELETE /api/account` (revokes Gmail token, marks user deleted, clears cookie).
- **Signed unsubscribe links** — `GET /api/unsubscribe?token=...` validates HMAC-SHA256 token, marks user deleted, redirects to `/unsubscribe` SPA page. `_make_unsubscribe_token()` helper for brief footers. `UNSUBSCRIBE_SECRET_KEY` in Railway.
- **`users` table** — `migrations/005_users.sql`: id, google_sub (unique), email, display_name, refresh_token, delivery_email, timezone, status, onboarding_complete, created_at, last_brief_at.
- **Static file serving** — `app.mount("/", StaticFiles(...))` at end of `main.py` serves built React app from `static/`. Conditional on `static/` directory existing so the app starts cleanly before first build.
- **DB helpers** — `upsert_user`, `get_user_by_id`, `update_user_setup`, `set_user_status` in `tools/db.py`.

### Fixed
- **Web setup didn't trigger onboarding** — `run_onboarding()` was checking `agent_config.onboarding_complete` (already `true` from initial CLI setup) and returning early before sending the setup email. Fixed by passing `user_id` from `/api/setup` through `_run_onboard` to `run_onboarding`; web-triggered calls now check `users.onboarding_complete` for the specific user instead of the global flag.
- **SPA routes returned 404 on Railway** — `Path("static")` resolved relative to Railway's CWD (not the project root). Changed to `Path(__file__).parent / "static"` for absolute resolution.

### Changed
- `run_onboarding()` gains optional `user_id` param — web-triggered onboarding checks per-user flag; cron-triggered path unchanged.
- `_run_onboard()` passes `user_id` through to `run_onboarding`.
- `process_onboarding_reply` calls `mark_users_onboarding_complete()` after setting global flag.
- `requirements.txt` — added `itsdangerous==2.2.0` for session signing.

---

## [Production Deployment] — 2026-03-26

### Added
- **Railway web service deployed** — FastAPI app live at `https://news-briefings-agent-production.up.railway.app`; all env vars configured, health check passing.
- **5 Railway cron services configured** — `daily-brief` (*/15 6-10 Mon–Fri), `poll-replies` (*/15 every day), `deep-read` (9am Mon–Fri), `weekend-catchup` (8am Sunday), `supervisor-weekly` (7am Sunday). All services have `WEB_SERVICE_URL` set.
- **Onboarding completed** — first run of `/jobs/onboard` processed against live Gmail inbox; user preferences applied to `agent_config`; `onboarding_complete` set to `true`.

### Fixed
- Removed `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, and `WEBHOOK_SECRET` from `.env.example` — leftover from an earlier architecture; this project uses Gmail API for all email sending.

---

## [Unreleased] — 2026-03-26

### Fixed
- `tools/retry.py` — `fn.__name__` access on MagicMock raised `AttributeError` in unit tests; replaced manual name assignment with `functools.wraps` + `getattr(fn, '__name__', repr(fn))` in log call. No behavior change in production.
- `tests/test_weekend_catchup.py`, `tests/test_deep_read.py` — `send_message` mocks returned bare strings; `pipeline/weekend_catchup.py` and `pipeline/deep_read.py` unpack the return as `(message_id, thread_id)`. Fixed mocks to return `("msg-id", "thread-id")` tuples. All 388 unit tests now pass (was 379).
- `tests/test_weekend_catchup.py`, `tests/test_deep_read.py` — E2E skip guard checked `SUPABASE_URL` but `.env` sets `DATABASE_URL`. Fixed env var name. All 4 Phase 4 E2E tests now pass against real DB.
- `tools/db.py` — `conn.description` used throughout; psycopg3 `Connection` has no `.description` attribute (only `Cursor` does). Fixed all 8 occurrences by capturing cursor: `cur = conn.execute(...); cols = [d.name for d in cur.description]`. Fixes `AttributeError` on real DB connections (was masked by mocks).
- `tools/db.py` `get_unacknowledged_stories` — hook had added a `story_clusters` JOIN referencing `sc.read_at` (column doesn't exist in schema); reverted to original query with no clusters join.

### Added
- **On-demand pipeline trigger via email** — User can reply to any digest (or send a self-addressed email) saying "send brief" or "deep read" to trigger a pipeline run within ~15 minutes, bypassing anchor checks and queue thresholds. Implemented as a new `"command"` reply type in the immediate supervisor graph with two new nodes (`extract_command`, `execute_command`); `_check_inbox_commands` helper in `main.py` handles the self-email failsafe path. `run_deep_read` gains a `force=True` parameter to bypass threshold and minimum article count.
- **Cluster-level read tracking** — Acknowledging any digest now marks all its `story_clusters` as read via the new `mark_clusters_read()` helper. `get_unacknowledged_stories` excludes read clusters, so a story that appeared in two digests (e.g. daily brief + on-demand brief) won't resurface in the weekend catch-up once the user acknowledges either. Requires `migrations/002_story_clusters_add_read_at.sql`.
- `gmail_service.GmailService.list_messages_with_query(q, max_results)` — queries Gmail with arbitrary `q=` syntax; used by inbox command detection.
- `supervisor/immediate.classify_command(text)` — public helper for classifying free-form text as `"daily_brief"` or `"deep_read"`; reuses the same Haiku chain as the graph.

---

## [Phase 6 — Onboarding] — 2026-03-26

### Added
- `pipeline/onboarding.py` — first-run flow: scans inbox via source_classifier, merges with known active sources, sends a setup email listing discovered newsletters by type, processes the user's reply to set source trust weights and topic preferences
- `migrations/003_onboarding.sql` — `onboarding_events` table (thread_id, sent_message_id, raw_reply, parsed_preferences, applied) + seeds `onboarding_complete: false` in agent_config; kept separate from `feedback_events` which requires a NOT NULL digest_id
- `tools/db.py`: `create_onboarding_event`, `update_onboarding_thread`, `get_pending_onboarding_event`, `mark_onboarding_applied`, `update_source_trust_weight` helpers
- `main.py`: `/jobs/onboard` endpoint + `_run_onboard` background task; `_check_onboarding_reply` wired into `_run_poll_replies`; `onboarding_complete` guard in `_run_daily_brief` — pipeline skips with a log warning if user hasn't replied yet
- `tests/test_onboarding.py` — 23 tests covering all guards, happy path, source weight boosts, topic merging, unsubscribe-not-executed, parse failure resilience, email formatting

---

## [Phase 5 / 6 Integration] — 2026-03-26

### Added
- `tools/unsubscribe.py` — unsubscribe executor: parses `List-Unsubscribe` header (mailto preferred over URL), executes action, marks source inactive in DB; raises `UnsubscribeError` if action fails before DB update so source is never silently marked inactive
- `supervisor/weekly.py` — LangGraph weekly pattern sweep: gathers 7 days of digest stats and feedback, Opus reasons over engagement patterns, applies low-risk config changes, sends weekly review email with observations and proposed high-risk changes
- `railway.toml` + `runtime.txt` — Railway web service config (nixpacks, uvicorn start command, health check, restart policy)
- CLAUDE.md "Deploying to Railway" section with cron service schedules and start commands
- `tools/db.py`: `get_source_by_email()` and `get_weekly_digest_stats()` helpers

### Changed
- `main.py`: `_run_supervisor_weekly` wired to `run_weekly_supervisor` (was a stub)

---

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

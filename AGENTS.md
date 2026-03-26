# Concurrent Agent Build Plan

> Read CLAUDE.md fully before starting work. This file defines your scope, file ownership, and integration seams.
> Phase 2 is being built externally on a separate branch. Do not touch Phase 2 files.

---

## Status at Plan Creation

- **Phase 1**: Complete
- **Phase 2**: In progress externally (extractor, embedder, disambiguator, synthesizer, enricher, ranker, formatter, daily_brief orchestrator — code written, integration + E2E testing in progress)
- **Phases 3–5**: Not started

---

## Agent 1 — Phase 3: Supervisor Infrastructure

**Branch**: `phase-3-supervisor`

### Build
- `supervisor/immediate.py` — LangGraph graph for immediate supervisor mode
  - Nodes: classify reply (acknowledge / feedback / both), extract proposed change, validate change (low-risk vs. high-risk), apply low-risk immediately, queue high-risk for approval
  - Tools available to graph: `update_agent_config`, `execute_unsubscribe`, `log_feedback_event`
  - Input: `digest_id`, `raw_reply`, `thread_id`
  - Output: `SupervisorResult` (action taken, config delta if any, queued items)
- `supervisor/__init__.py`
- Reply polling logic in `main.py` — fill in `_run_poll_replies()` stub
  - Fetch replies to known digest threads via `gmail_service.get_replies()`
  - For each reply: run classifier, invoke immediate supervisor graph
  - Mark digest `acknowledged_at` if reply is acknowledgment type
- Reply classifier (inline in `supervisor/immediate.py`) — Haiku call, returns `ReplyType`: `acknowledge | feedback | both | irrelevant`
- `tests/test_supervisor_immediate.py` — unit tests with mocked gmail_service, mocked DB, mocked LLM

### Files you own
```
supervisor/immediate.py
supervisor/__init__.py
tests/test_supervisor_immediate.py
```
One targeted edit to `main.py`: fill in `_run_poll_replies()` only. Do not touch any other function in `main.py`.

### Files to stay out of
```
pipeline/           # Phase 2 person is here
main.py             # except _run_poll_replies stub
tools/              # owned by Agent 3
```

### Integration seam
Your graph receives `digest_id` (UUID) and `raw_reply` (string). You do not care how the digest was produced. The `digests` table and `feedback_events` table from Phase 1 schema are your data contract. The `agent_config` table is where you write config changes.

### Definition of done
- LangGraph graph runs end-to-end in tests with mocked inputs
- `_run_poll_replies()` in main.py calls the graph correctly
- All low-risk config changes (topic_weights, word_budget, cosine_similarity_threshold) applied via `update_agent_config` DB helper
- Unsubscribe flow calls `gmail_service.execute_unsubscribe()` and updates `newsletter_sources` status
- >90% test coverage on supervisor logic

---

## Agent 2 — Phase 4: Weekend Catch-Up + Deep Read

**Branch**: `phase-4-pipelines`

### Build
- `pipeline/weekend_catchup.py`
  - Query `stories` table for unacknowledged digests Mon–Fri (join `digests` on `acknowledged_at IS NULL`)
  - Cross-day dedup using stored `embedding` vectors (pgvector cosine similarity, no re-embedding needed — embeddings already in DB)
  - Rerank by importance (source count, topic weights) not recency — import `ranker.py` from Phase 2
  - Format at 30-min time budget — import `formatter.py` from Phase 2 with `word_budget` override
  - Send via `gmail_service.send()`, archive source digests
  - Trigger: Sunday morning (Railway cron calls `/jobs/weekend-catchup` endpoint)

- `pipeline/deep_read.py`
  - Query `newsletter_sources` where `type = 'long_form'` and `status = 'active'`
  - Fetch unread long-form emails via `gmail_service`
  - Queue threshold: only run if 5+ long-form pieces available (check `agent_config` `deep_read_threshold`)
  - Extract via `extractor.py` from Phase 2
  - Format with full treatment for 3–5 articles, include original link for each
  - Send via `gmail_service.send()`, archive
  - Trigger: Thursday fallback if queue at threshold, or `/jobs/deep-read` endpoint

- `tests/test_weekend_catchup.py` — mock DB returns, mock Phase 2 imports, mock gmail_service
- `tests/test_deep_read.py` — same approach

### Files you own
```
pipeline/weekend_catchup.py
pipeline/deep_read.py
tests/test_weekend_catchup.py
tests/test_deep_read.py
```
No changes to `main.py` — the endpoint stubs (`_run_weekend_catchup`, `_run_deep_read`) already exist. Wire them in the integration sprint after Phase 2 lands.

### Files to stay out of
```
pipeline/daily_brief.py
pipeline/extractor.py
pipeline/embedder.py
pipeline/disambiguator.py
pipeline/synthesizer.py
pipeline/enricher.py
pipeline/ranker.py
pipeline/formatter.py
main.py
supervisor/
tools/
```
Import Phase 2 modules directly — do not copy their logic.

### Integration seam
Both pipelines import Phase 2 modules (`ranker`, `formatter`, `synthesizer`, `extractor`) by reference. In unit tests, mock these imports. E2E testing waits until Phase 2 is integrated and stories exist in the DB.

### Definition of done
- Both pipeline files importable with Phase 2 modules mocked
- Unit tests pass with >90% coverage on orchestration logic
- `weekend_catchup.py` correctly builds the unacknowledged-story query (even if E2E test is skipped)
- `deep_read.py` correctly applies queue threshold from `agent_config`

---

## Agent 3 — Phase 5: Cross-Cutting Infrastructure

**Branch**: `phase-5-infra`

### Build
- `tools/tracing.py` — LangSmith tracing wrapper
  - Decorator `@traced(name)` that wraps any LangChain LCEL chain or LangGraph graph invocation with `langsmith.trace()`
  - Reads `LANGSMITH_API_KEY` from config (already in `config.py` env validation — add if missing)
  - No changes to existing pipeline files yet — this is a drop-in used during integration sprint

- `tools/retry.py` — retry wrapper
  - `with_retry(fn, max_attempts=3, delay=5)` — wraps any pipeline step
  - Distinguishes retryable errors (network, rate limit) from fatal errors (auth, schema)
  - Logs each attempt with attempt number and error type

- `tools/alerts.py` — alert email on pipeline failure
  - `send_alert(pipeline_name, error, run_id)` — sends plain-text email via `gmail_service.send()` to `ALERT_EMAIL` env var
  - Called after all retries exhausted
  - Include: pipeline name, run_id, error type, timestamp, last 500 chars of traceback

- `tests/test_tracing.py`, `tests/test_retry.py`, `tests/test_alerts.py`

### Files you own
```
tools/tracing.py
tools/retry.py
tools/alerts.py
tests/test_tracing.py
tests/test_retry.py
tests/test_alerts.py
```
Do not touch `tools/db.py` — it belongs to Phase 1 and is complete.

### Files to stay out of
```
pipeline/
supervisor/
main.py
```

### Integration seam
All three utilities are designed for zero-friction adoption: `@traced(name)` wraps a chain, `with_retry(fn)` wraps a step, `send_alert(...)` is called in the except block of each job endpoint in `main.py`. Integration happens in one pass during the integration sprint — you are just building the tools.

### Definition of done
- `@traced` decorator correctly starts/ends LangSmith trace and passes through return value
- `with_retry` correctly retries N times, raises on exhaustion
- `send_alert` sends correctly formatted email and does not itself throw
- All utilities work when `LANGSMITH_API_KEY` is absent (tracing is a no-op, not a crash)
- Tests pass with mocked LangSmith client and mocked gmail_service

---

## Coordination Rules

1. **No agent touches `main.py` except Agent 1** (and only `_run_poll_replies`).
2. **No agent touches Phase 2 pipeline files** — import them, never edit them.
3. **No agent touches `tools/db.py`** — it is complete.
4. Conflicts go to the human. Do not attempt merges autonomously.

---

## Integration Sprint (after Phase 2 merges to main)

All three branches rebase onto main, then:

1. **Agent 1**: Wire supervisor to real digest IDs. Run E2E test against Gmail with a real reply.
2. **Agent 2**: Run E2E tests for both pipelines against real DB with real story data.
3. **Agent 3**: Thread `@traced`, `with_retry`, and `send_alert` through all pipeline steps and job endpoints in `main.py`.
4. **All**: Update `CHANGELOG.md` and `TODO.md`. Add `DECISIONS.md` entries for any non-obvious choices made during build.

Weekly supervisor (`supervisor/weekly.py`) starts after integration sprint — it needs real feedback events in the DB.

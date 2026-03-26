# TODO

## In Progress — Phase 3 (agent building)

- [ ] `supervisor/immediate.py` — LangGraph graph: classify reply → apply/queue changes
- [ ] Reply polling: query recent digest thread IDs, call `get_thread_replies`, mark `acknowledged_at`
- [ ] Wire Phase 3 into `main.py` `_run_poll_replies`
- [ ] Unsubscribe executor: call List-Unsubscribe header URL/mailto, update source status
- [ ] Feedback event logging: persist every reply + supervisor interpretation to `feedback_events`
- [ ] `tests/test_supervisor_immediate.py` — >90% coverage

## In Progress — Phase 4 (agent building)

- [ ] `pipeline/weekend_catchup.py` — query unacknowledged stories, dedup via stored embeddings, rerank by importance, format at 30-min budget
- [ ] `pipeline/deep_read.py` — long-form queue pipeline, threshold check from agent_config, full treatment with original links
- [ ] Wire Phase 4 into `main.py` `_run_weekend_catchup`, `_run_deep_read`
- [ ] `tests/test_weekend_catchup.py`, `tests/test_deep_read.py` — unit + `@pytest.mark.e2e` tests

## In Progress — Phase 5 Infrastructure (agent building)

- [ ] `tools/tracing.py` — `@traced(name)` decorator; no-op if LANGSMITH_API_KEY absent
- [ ] `tools/retry.py` — `with_retry(fn, max_attempts=3)` with retryable vs. fatal error discrimination
- [ ] `tools/alerts.py` — `send_alert(pipeline_name, error, run_id)` via gmail_service

## Blocked on Phase 3/4/5 completion

- [ ] `supervisor/weekly.py` — LangGraph weekly pattern sweep (needs real feedback_events in DB)
- [ ] Railway deployment config + cron schedule setup
- [ ] Integration sprint: thread tracing/retry/alerts through all pipelines and endpoints

## High Priority — Now

- [ ] End-to-end smoke test: run pipeline against real inbox in dry-run mode
- [ ] Verify anchor sender emails in `.env` match exact Axios AM sender address (check Gmail)
- [ ] Run `schema.sql` against Supabase if not yet done

## Low Priority / Nice to Have

- [ ] `TEST_DATABASE_URL` setup for DB integration tests in CI
- [ ] `GET /jobs/status` endpoint to inspect last run result per job type
- [ ] `--dry-run` flag support via CLI entrypoint in `pipeline/daily_brief.py`

## Completed

- [x] AGENTS.md — concurrent build plan for Phases 3–5 — 2026-03-26
- [x] Git repository initialized, remote set to wilfredtso1/news-briefing — 2026-03-26
- [x] Worktrees created for phase-3-supervisor, phase-4-pipelines, phase-5-infra branches — 2026-03-26
- [x] Phase 2 E2E tested against real Gmail inbox — 2026-03-26
- [x] main.py wired to Phase 2 pipeline — 2026-03-26
- [x] tests: test_extractor.py, test_embedder.py, test_synthesizer.py, test_ranker.py, test_formatter.py — 124 passing — 2026-03-26
- [x] pipeline/extractor.py, embedder.py, disambiguator.py, synthesizer.py, enricher.py, ranker.py, formatter.py, daily_brief.py — 2026-03-26
- [x] SPEC.md — product spec finalized — 2026-03-26
- [x] CLAUDE.md — engineering standards documented — 2026-03-26
- [x] AGENT_INSTRUCTIONS.md — supervisor standing orders — 2026-03-26
- [x] requirements.txt — dependencies pinned — 2026-03-26
- [x] config.py — startup env var validation — 2026-03-26
- [x] schema.sql — full DB schema with pgvector — 2026-03-26
- [x] tools/db.py — all DB helpers — 2026-03-26
- [x] gmail_service.py — Gmail API wrapper — 2026-03-26
- [x] source_classifier.py — newsletter detection + anchor logic — 2026-03-26
- [x] main.py — FastAPI skeleton with all job endpoints — 2026-03-26
- [x] tests/conftest.py, test_source_classifier.py, test_gmail_service.py, test_db.py — 2026-03-26

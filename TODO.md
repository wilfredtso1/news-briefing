# TODO

## Integration Sprint — Now Unblocked

- [ ] Merge order: phase-5-infra → phase-3-supervisor → phase-4-pipelines (into main)
- [ ] Thread `@traced` / `with_retry` / `send_alert` through daily_brief.py, weekend_catchup.py, deep_read.py, _run_poll_replies
- [ ] Schema migration: add `thread_id` and `sent_message_id` columns to `digests` table (needed by `_run_poll_replies`)
- [ ] Unsubscribe executor: call List-Unsubscribe header URL/mailto, update source status (was out of scope for Phase 3 agent)
- [ ] E2E test Phase 3 supervisor against real Gmail reply thread
- [ ] E2E test Phase 4 pipelines (weekend_catchup, deep_read) against live DB with `@pytest.mark.e2e`

## Blocked on integration sprint completion

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

- [x] Phase 3 supervisor reviewed, 64/64 tests passing, pushed to phase-3-supervisor — 2026-03-26
- [x] Phase 4 pipelines reviewed, tests fixed, 60/60 passing, pushed to phase-4-pipelines — 2026-03-26
- [x] Phase 5 infra reviewed, dead code removed from retry.py, 60/60 passing, pushed to phase-5-infra — 2026-03-26
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

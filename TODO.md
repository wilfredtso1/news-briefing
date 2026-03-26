# TODO

## Phase 6 — Onboarding ✓ Completed 2026-03-26

- [x] Schema migration: `onboarding_events` table + seed `onboarding_complete: false` — migrations/003_onboarding.sql
- [x] `pipeline/onboarding.py` — inbox scan, setup email, reply processor
- [x] Wire reply polling: `_check_onboarding_reply` in `_run_poll_replies`
- [x] `_run_daily_brief()` guard for onboarding_complete
- [x] `/jobs/onboard` FastAPI endpoint + `_run_onboard` background task
- [x] `tests/test_onboarding.py` — 23 tests passing

**Remaining action (manual)**: Run `migrations/003_onboarding.sql` against Supabase before first deploy

## Completed

- [x] Cluster-level read tracking — read_at on story_clusters, mark_clusters_read, get_unacknowledged_stories excludes read clusters — Completed 2026-03-26; run migrations/002_story_clusters_add_read_at.sql against Supabase
- [x] On-demand pipeline trigger via email — "command" reply type in supervisor, self-addressed inbox detection, force mode for deep read — Completed 2026-03-26

## Remaining Pre-Production Work

- [ ] E2E smoke test: daily_brief against real Gmail inbox in dry-run mode (needs live credentials)
- [ ] E2E test Phase 3 supervisor against real Gmail reply thread (needs live credentials)
- [ ] E2E test Phase 4 pipelines (weekend_catchup, deep_read) against live DB — `@pytest.mark.e2e`
- [ ] Weekly supervisor approval flow: store weekly review as a digest, poll replies, route approvals to immediate supervisor — deferred per DECISIONS.md 2026-03-26

## Low Priority / Nice to Have

- [ ] `TEST_DATABASE_URL` setup for DB integration tests in CI
- [ ] `GET /jobs/status` endpoint to inspect last run result per job type
- [ ] `--dry-run` flag support via CLI entrypoint in `pipeline/daily_brief.py`

## Completed

- [x] Unsubscribe executor (`tools/unsubscribe.py`), weekly supervisor (`supervisor/weekly.py`), Railway config — Completed 2026-03-26
- [x] Run `migrations/001_digests_add_thread_fields.sql` against Supabase — Completed 2026-03-26

- [x] Integration sprint: branch merges, schema migration, thread wiring, tracing/retry/alerts — 2026-03-26
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

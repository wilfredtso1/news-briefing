# TODO

## Web App — Multi-User Frontend ✓ Backend Complete 2026-03-26

- [x] `migrations/005_users.sql` — `users` table (google_sub, email, display_name, refresh_token, delivery_email, timezone, status, onboarding_complete, last_brief_at)
- [x] `tools/db.py`: `upsert_user`, `get_user_by_id`, `update_user_setup`, `set_user_status` helpers
- [x] `main.py`: 7 new endpoints (`GET /auth/google`, `GET /auth/google/callback`, `GET /api/me`, `POST /api/setup`, `POST /api/pause`, `DELETE /api/account`, `GET /api/unsubscribe`); session signing helpers; static file mount
- [x] `config.py`: `google_oauth_client_id`, `google_oauth_client_secret`, `google_oauth_redirect_uri`, `session_secret_key`, `unsubscribe_secret_key` optional fields
- [x] `web/src/pages/LandingPage.tsx` — `handleSignIn` redirects to `/auth/google`
- [x] `web/src/pages/SetupPage.tsx` — email pre-filled from `/api/me`; submit POSTs to `/api/setup`
- [x] `web/src/pages/AccountPage.tsx` — loads real user from `/api/me`; real pause/delete handlers
- [x] Railway: `SESSION_SECRET_KEY`, `UNSUBSCRIBE_SECRET_KEY`, `GOOGLE_OAUTH_REDIRECT_URI` set
- [x] `run_onboarding` per-user flag — web sign-ups check `users.onboarding_complete` instead of global flag; `mark_users_onboarding_complete()` added to `tools/db.py`
- [x] SPA routing absolute path fix — `Path(__file__).parent / "static"` instead of relative `Path("static")`
- [ ] **Remaining manual**: Run `migrations/005_users.sql` against Supabase (if not done)
- [ ] **Future**: Add `user_id` to `onboarding_events` for proper per-user scoping (see DECISIONS.md 2026-03-26)
- [ ] **Future**: Multi-tenancy — `user_id` column on all pipeline tables
- [ ] **Future**: Encrypt `refresh_token` at rest

## Phase 7 — Self-Improving Agent ✓ Completed 2026-03-26

- [x] `supervisor/code_change_agent.py` — LangGraph agent with 4 scoped tools (`read_file`, `write_file`, `run_bash`, `send_diff_email`); invoked from `trigger_code_change_node` when `proposed_key == "unknown"` and `len(raw_reply) > 50`
- [x] Agent drafts code changes, runs `pytest tests/` as gate, emails diff with subject "product input required for news briefing"
- [x] Approval path: user replies "approve" → `code_change_approval` reply type → `git push` → Railway auto-deploys
- [x] Scope constraints: `write_file` blocks `schema.sql`, `main.py`, `config.py`, `migrations/`; only `pipeline/`, `supervisor/`, `tools/` allowed
- [x] `CODE_CHANGE_NOTIFY_EMAIL` env var (falls back to `ALERT_EMAIL`); added to `config.py` as optional field
- [x] 20 tests — all passing

## Immediate Fixes — Source Coverage & Supervisor Expansion ✓ Completed 2026-03-26

- [x] Source classifier reads `newsletter_sources.type` from DB before running length heuristic — fixes Morning Brew/Axios permanently after onboarding
- [x] `update_source_type(sender_email, type)` DB helper added to `tools/db.py`
- [x] `crew@morningbrew.com` and `markets@axios.com` added to `KNOWN_NEWS_BRIEF_SENDERS`
- [x] Onboarding setup email + reply parser accepts `source_type_corrections`
- [x] Supervisor maps "include X in daily brief" → `source_reclassify` → `update_source_type`
- [x] `web_search_topics` agent_config key + `gap_fill_topics()` step in daily_brief after enricher
- [x] `synthesis_style_notes` agent_config key; synthesizer reads at call time
- [x] Schema seed + `migrations/004_agent_config_style_topics.sql`; migration run 2026-03-26
- [x] 83 total new tests across all 4 branches — 471 passing (up from 388)

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

- [x] E2E smoke test: daily_brief against real Gmail inbox in dry-run mode — Completed 2026-03-26
- [x] E2E test Phase 3 supervisor against real Gmail reply thread — Completed 2026-03-26 (word_budget change applied from live reply)
- [x] E2E test Phase 4 pipelines (weekend_catchup, deep_read) against live DB — Completed 2026-03-26
- [x] Railway web service deployed and healthy — Completed 2026-03-26
- [x] 5 Railway cron services configured (daily-brief, poll-replies, deep-read, weekend-catchup, supervisor-weekly) — Completed 2026-03-26
- [x] Onboarding completed against live Gmail inbox — Completed 2026-03-26
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

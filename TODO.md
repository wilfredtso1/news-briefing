# TODO

## High Priority

- [ ] End-to-end smoke test: run pipeline in `--dry-run` mode against real inbox (`python -m pipeline.daily_brief --dry-run`)
- [ ] Verify anchor sender emails in `.env` match your exact Axios AM sender address (check Gmail)

## Medium Priority — Phase 3

- [ ] `supervisor/immediate.py` — LangGraph graph: classify reply → apply/queue changes
- [ ] Reply polling: query recent digest thread IDs, call `get_thread_replies`
- [ ] Wire Phase 3 into `main.py` `_run_poll_replies`
- [ ] Unsubscribe executor: call List-Unsubscribe header URL/mailto

## Low Priority — Phase 4

- [ ] `pipeline/weekend_catchup.py` — Draw from unacknowledged stories, rerank
- [ ] `pipeline/deep_read.py` — Long-form queue pipeline
- [ ] Wire Phase 4 into `main.py`

## Low Priority — Phase 5

- [ ] `supervisor/weekly.py` — LangGraph weekly pattern sweep
- [ ] LangSmith instrumentation across all LLM calls
- [ ] Pipeline failure retry logic + alert email
- [ ] Railway deployment config + cron schedule setup

## Low Priority / Nice to Have

- [ ] `TEST_DATABASE_URL` setup for DB integration tests
- [ ] `GET /jobs/status` endpoint to inspect last run result per job type
- [ ] `--dry-run` flag support via CLI entrypoint in `pipeline/daily_brief.py`

## Completed (recent)

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
- [x] pipeline/extractor.py — LLM story extraction via LCEL chain (claude-haiku-4-5) — 2026-03-25
- [x] pipeline/embedder.py — Voyage AI embeddings + cosine clustering — 2026-03-25
- [x] pipeline/disambiguator.py — LangGraph ambiguous cluster resolution — 2026-03-25
- [x] pipeline/synthesizer.py — multi-source → canonical story (claude-opus-4-6) — 2026-03-25
- [x] pipeline/enricher.py — Tavily web search enrichment for single-source stories — 2026-03-25
- [x] pipeline/ranker.py — topic-weighted story ranking — 2026-03-25
- [x] pipeline/formatter.py — tiered treatment, word budget, topic sections — 2026-03-25
- [x] pipeline/daily_brief.py — full pipeline orchestrator — 2026-03-25
- [x] main.py wired to Phase 2 pipeline — 2026-03-25
- [x] tests: test_extractor.py, test_embedder.py, test_synthesizer.py, test_ranker.py, test_formatter.py — 124 passing — 2026-03-25

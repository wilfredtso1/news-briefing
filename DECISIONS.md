# Architectural Decisions

Foundational decisions made before development began are documented in `CLAUDE.md` (Non-Obvious Design Decisions section). This file captures decisions made during development.

---

## 2026-03-26: Concurrent agent build for Phases 3–5 using git worktrees

**Status**: Accepted

**Context**: Phase 2 completed. Phases 3 (supervisor), 4 (weekend catch-up + deep read), and 5 (tracing/retry/alerts) needed to be built. Default approach would be sequential: finish one phase, start the next.

**Options considered**:
1. **Sequential build** — One phase at a time. Simple, no coordination overhead. Cons: leaves agents idle and doesn't exploit the independence of these phases.
2. **Concurrent build, shared working directory** — Multiple agents working in the same checkout simultaneously. Cons: file conflicts, impossible to isolate changes, merge chaos.
3. **Concurrent build, git worktrees** — Each agent gets its own branch and working directory via `git worktree add`. Agents work in isolation, push branches, PRs merged in a defined order. Cons: requires a merge/integration sprint at the end.

**Decision**: Concurrent build with git worktrees. Analysis showed Phase 3 has almost no dependency on Phase 2 logic (only needs Phase 1 schema and gmail_service). Phase 4 imports complete Phase 2 modules but doesn't need them running to write code. Phase 5 utilities are entirely independent. Running all three concurrently with defined file ownership in `AGENTS.md` eliminates idle time.

**File ownership**: Agent 1 owns `supervisor/`, Agent 2 owns `pipeline/weekend_catchup.py` + `pipeline/deep_read.py`, Agent 3 owns `tools/tracing.py` + `tools/retry.py` + `tools/alerts.py`. Conflicts go to the human — agents do not merge autonomously.

**Integration order**: phase-5-infra merges first (tools must exist), then phase-3-supervisor, then phase-4-pipelines.

**Consequences**: Requires a short integration sprint after all branches complete. Weekly supervisor (`supervisor/weekly.py`) remains sequential — it needs real feedback_events in the DB before it can be built meaningfully.

---

## 2026-03-26: Use HNSW index for story embeddings instead of IVFFlat

**Status**: Accepted

**Context**: pgvector supports two index types for approximate nearest-neighbor search: IVFFlat and HNSW. Needed to choose one for the `stories.embedding` column.

**Options considered**:
1. **IVFFlat** — Faster to build, lower memory. Requires a training phase (needs existing data to build lists). Poor performance on empty or small tables. Pros: lower memory at scale. Cons: requires `SET ivfflat.probes` tuning; cold-start problem with no data.
2. **HNSW** — Slower to build, higher memory. No training phase required — works immediately on empty tables. Better recall at equivalent speed for our data size. Pros: works day one, better developer experience. Cons: higher memory usage at very large scale (not a concern here).

**Decision**: HNSW. This project starts with zero stories and grows incrementally. IVFFlat's training requirement makes it a poor fit for early development. At the data volumes we expect (thousands of stories, not millions), the memory difference is negligible.

**Consequences**: Index is immediately usable after schema creation. If the project ever scales to millions of stories, revisit IVFFlat for better memory efficiency.

---

## 2026-03-26: No APScheduler — Railway cron hits FastAPI job endpoints

**Status**: Accepted

**Context**: Needed a scheduling mechanism for periodic jobs (daily brief, reply polling, etc.).

**Options considered**:
1. **APScheduler embedded in FastAPI** — Scheduler runs inside the app process. Flexible, supports complex schedules. Cons: couples scheduling to the app process lifetime; harder to monitor; overkill for a personal tool with simple schedules.
2. **Railway cron + FastAPI endpoints** — Railway cron sends `POST /jobs/daily-brief` on a schedule. App is stateless between runs. Pros: simpler, observable in Railway dashboard, schedule config lives in Railway not code. Cons: requires Railway deployment before scheduling works.
3. **Standalone cron worker** — Separate process/service just for scheduling. Pros: decoupled. Cons: extra service to deploy and maintain.

**Decision**: Railway cron + FastAPI job endpoints. The schedules are simple (hourly, daily, weekly) and don't need APScheduler's flexibility. Railway's cron dashboard gives free observability. The FastAPI endpoints also enable manual triggering from phone via Shortcuts app.

**Consequences**: No scheduling in local dev — jobs must be triggered manually or via `curl`. This is acceptable for development; the full schedule only matters in production.

---

## 2026-03-26: Voyage AI voyage-3 (1024 dimensions) for embeddings

**Status**: Accepted

**Context**: Anthropic does not provide an embeddings API. Needed an external embeddings provider for story clustering.

**Options considered**:
1. **OpenAI text-embedding-3-small** — Well-known, 1536 dims, $0.02/1M tokens. Cons: introduces OpenAI dependency when we're already committed to Anthropic for LLM calls.
2. **Voyage AI voyage-3** — Anthropic's recommended partner, 1024 dims, ~$0.06/1M tokens. Purpose-built to complement Claude. Cons: slightly higher cost per token than OpenAI.
3. **voyage-3-lite** — 512 dims, faster, cheaper. Cons: lower quality embeddings, more clustering errors.

**Decision**: voyage-3 at 1024 dimensions. Keeps the dependency surface to Anthropic's ecosystem. Quality difference over voyage-3-lite is worth the cost for accurate story deduplication — a false merge (two different stories treated as one) is a visible quality defect.

**Consequences**: `stories.embedding` column is `vector(1024)`. If we ever switch embedding models, a migration will be needed to re-embed all existing stories.

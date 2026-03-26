# Architectural Decisions

Foundational decisions made before development began are documented in `CLAUDE.md` (Non-Obvious Design Decisions section). This file captures decisions made during development.

---

## 2026-03-26: Web app served as static files from FastAPI

**Status**: Accepted

**Context**: The React SPA needs to be hosted somewhere. Options are a separate static hosting service (Vercel, Netlify) or bundling into the existing Railway FastAPI service.

**Options considered**:
1. **Vercel/Netlify** — Pros: free tier, fast CDN, automatic deploys from git. Cons: CORS configuration required; two deploy targets to manage; session cookie must be cross-origin (complicates `httponly` + `samesite=lax` requirements).
2. **FastAPI static mount** — `app.mount("/", StaticFiles(directory="static", html=True))` at end of `main.py`. Build step copies `dist/` to `static/`. Pros: one service, no CORS, session cookies work natively. Cons: Railway redeploys on every frontend change; static/ must be excluded from git and built at deploy time.

**Decision**: FastAPI static mount (Option 2). One Railway service is simpler. Session cookies work correctly with no CORS config. The static mount is guarded by `if os.path.isdir("static")` so the app starts cleanly before the first build. The API routes (`/auth/*`, `/api/*`, `/jobs/*`) are registered before the catch-all, so the SPA only receives paths not matched by any API route.

**Consequences**: React app rebuild required on every UI change before deploying. Add `static/` to `.gitignore`. Railway build command must run `bun run build && cp -r dist/ static/` before starting uvicorn.

---

## 2026-03-26: Separate Google OAuth client for web app sign-in

**Status**: Accepted

**Context**: The pipeline uses `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` for service-level Gmail API access via a manually-obtained refresh token. The web app needs a different OAuth flow: redirect-based, short-lived authorization codes, where each user gets their own refresh token.

**Options considered**:
1. **Reuse existing GMAIL_* credentials** — The existing credentials are for a "Desktop app" OAuth client type in Google Cloud Console. Desktop app clients don't support `https://` redirect URIs, so the authorization code flow for web users would fail.
2. **New "Web application" OAuth client in the same Google Cloud project** — Pros: scoped correctly for redirect flows, supports `https://` redirect URIs, production-safe. Cons: must add redirect URIs in Google Console for each environment (local, staging, production).

**Decision**: New "Web application" OAuth client (Option 2). This is required — desktop app credentials cannot be used for web redirect flows. The `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` env vars are distinct from `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` to make this separation explicit. Both can live in the same Google Cloud project.

**Redirect URI to authorize**: `https://news-briefings-agent-production.up.railway.app/auth/google/callback`

**Consequences**: Two OAuth clients to manage in Google Console. `refresh_token` from user sign-in stored in `users` table — this is the per-user Gmail access credential. Future: encrypt at rest with Fernet before storing.

---

## 2026-03-26: refresh_token stored unencrypted for now

**Status**: Accepted (temporary) — encrypt before opening to other users

**Context**: User OAuth refresh tokens grant Gmail access and must be stored in the `users` table to call Gmail on their behalf. Encrypting at rest adds complexity (Fernet key rotation, key management).

**Decision**: Store plaintext for now. This is a personal tool with a single user. Before opening to other users, add `cryptography` library (Fernet), store `FERNET_KEY` in Railway, encrypt on write, decrypt on read. Noted in TODO.md and web-integration-spec.md.

**Consequences**: Acceptable risk for single-user personal tool. Must be addressed before any public beta.

---

## 2026-03-26: `/api/unsubscribe` not `/unsubscribe` for one-click unsubscribe

**Status**: Accepted

**Context**: The spec had the one-click unsubscribe endpoint at `GET /unsubscribe`. But the React SPA has a `<Route path="/unsubscribe">` that renders the confirmation page. If FastAPI registers `@app.get("/unsubscribe")`, it intercepts all requests to that path — including the SPA page load — and the React component never renders.

**Decision**: Move the endpoint to `GET /api/unsubscribe?token=...`. Email footer unsubscribe links use `/api/unsubscribe`. After validating the token and marking the user deleted, the endpoint redirects to `/unsubscribe` which the static file mount serves as the SPA (React renders `UnsubscribePage`). The clean separation of `/api/*` for backend and everything else for the SPA catches-all is maintained.

**Consequences**: Unsubscribe links in email footers must use `/api/unsubscribe?token=...` not `/unsubscribe?token=...`. Update `_make_unsubscribe_token` call sites when wiring to the formatter.

---

## 2026-03-26: CodeChangeAgent for structural/unknown supervisor feedback

**Status**: Accepted — implementation deferred to Phase 7

**Context**: The immediate supervisor handles config key changes (topic_weights, word_budget, etc.) automatically. But a class of user feedback doesn't map to any config key — "I want sports headlines", "include Morning Brew in the brief", "why no markets data?" — and currently gets silently queued with no action path. For a personal tool, this means valid feedback goes unaddressed unless the developer manually reads the queue and codes a fix.

**Options considered**:
1. **Expand LOW_RISK_CONFIG_KEYS indefinitely** — Add new config keys for every pattern that emerges. Pros: simple, predictable. Cons: can't anticipate every feedback pattern; fundamentally limited by what the developer hard-codes.
2. **Human review queue** — All unknown feedback queued to a dashboard; developer handles manually. Pros: safe. Cons: requires developer attention; feedback loop takes days not minutes; defeats the purpose of a self-improving agent.
3. **CodeChangeAgent using Anthropic API tool use** — When feedback doesn't map to a config key, invoke an agent with `read_file`, `write_file`, `run_bash` tools. Agent reads the codebase, drafts a fix, runs tests, emails a diff for approval. User replies "approve" to deploy. Pros: handles genuinely novel feedback; maintains human oversight via approval gate; test suite prevents regressions. Cons: more complex; requires careful scope constraints to prevent unsafe changes.

**Decision**: CodeChangeAgent (Option 3). The approval gate (email diff → user replies "approve" → git push → Railway deploy) provides the safety that makes autonomous code changes acceptable. The test suite pass requirement is a hard gate — no diff is proposed if tests fail. Scope constraints (no schema migrations, no `main.py` job routing) keep the blast radius bounded.

**Email subject**: `product input required for news briefing` — distinct from pipeline alerts so the user can filter/route it separately.

**Consequences**: Unknown feedback now has an action path. The agent may occasionally propose wrong changes — the approval gate catches these. Over time, as common patterns get added to LOW_RISK_CONFIG_KEYS, the CodeChangeAgent is invoked less frequently for routine things and more for genuinely novel structural requests.

---

## 2026-03-26: Source classifier must respect user-confirmed DB types

**Status**: Accepted — implementation in Immediate Fixes

**Context**: The source classifier uses email body length as a heuristic to determine whether a newsletter is `news_brief` or `long_form`. Morning Brew is a daily news digest but has a long body, so it gets classified as `long_form` every run and routed to the deep read queue — entirely excluded from the daily brief. The `newsletter_sources` table has a `type` column that can hold a user-confirmed classification, but the classifier never reads it.

**Options considered**:
1. **`source_type_overrides` in agent_config** — A separate dict in agent_config that the classifier checks. Pros: agent_config already has supervisor write access. Cons: duplicates data that `newsletter_sources.type` already stores; two sources of truth for source type.
2. **Classifier reads `newsletter_sources.type` for known sources** — Before running the length heuristic, look up the sender in the DB. If a type is already stored, use it. Only fall back to the heuristic for first-seen senders. Pros: single source of truth; the DB column already exists for this purpose. Cons: adds a DB read per email classified (acceptable — classifier already upserts to DB).
3. **Hard-code correct types in `KNOWN_NEWS_BRIEF_SENDERS`** — Add Morning Brew, Axios Markets, etc. to the known-sender sets. Pros: no DB read. Cons: must be maintained in code; doesn't generalize to sources discovered through onboarding.

**Decision**: Option 2 (DB lookup) as the primary mechanism, plus Option 3 for sources we already know are misclassified (`crew@morningbrew.com`, `markets@axios.com`). The hard-codes are a safety net for before onboarding runs; the DB lookup is the long-term mechanism that makes user corrections durable.

**Consequences**: After onboarding confirms source types, re-classification errors are permanently fixed without code changes. The classifier DB read is bounded to `newsletter_sources` which is a small table.

---

## 2026-03-26: On-demand pipeline trigger via email command

**Status**: Accepted

**Context**: Pipelines run on Railway cron. If a scheduled run fails (e.g. anchors arrive late, pipeline crashes), the user has no way to get a brief without hitting the FastAPI endpoint manually. The user also wants the ability to request a brief at any time outside the schedule.

**Options considered**:
1. **Dedicated email address / webhook** — Give the agent its own Gmail address; user emails it to trigger runs. Pros: clean separation. Cons: requires a second OAuth credential, extra Gmail account to manage, unnecessary complexity for a single-user tool.
2. **Extend existing supervisor graph with a new "command" reply type** — User replies to any existing digest saying "send brief". The 15-minute poll cycle already runs; adding a new reply type to the graph reuses all existing infrastructure. Self-addressed email (from/to `gmail_send_as`) as a failsafe when no digest exists to reply to.
3. **New FastAPI endpoint with auth token** — `POST /jobs/trigger?token=xxx`. Pros: instant. Cons: requires user to remember a URL and token; no email-native UX.

**Decision**: Option 2. New `"command"` reply type in the immediate supervisor graph with `extract_command_node` (Haiku classifies `daily_brief` vs `deep_read`) and `execute_command_node` (runs the pipeline synchronously in the background task). Failsafe: `_check_inbox_commands` in `_run_poll_replies` scans for self-addressed unread emails. All runs use `force=True` to bypass anchor checks and queue thresholds — user explicitly asked, deliver what's available.

**Consequences**: On-demand runs happen within one 15-minute polling cycle. They share the same `run_id` logging and alert infrastructure as scheduled runs. The `force` flag on `run_deep_read` delivers with even 1 article if that's all that's available — deliberate UX choice. Command replies to a digest do NOT mark it acknowledged (it's a request, not a reading confirmation).

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

## 2026-03-26: Weekly supervisor sends informational email; approval flow deferred

**Status**: Accepted

**Context**: The spec calls for the weekly supervisor to send proposed changes in a review email and "apply approved changes" when the user replies. Implementing the approval flow requires polling replies to the weekly review email and distinguishing approval replies from other replies — a non-trivial extension of the reply polling logic.

**Options considered**:
1. **Full approval flow** — Store weekly review as a `weekly_review` digest type, poll for replies, interpret approvals via the immediate supervisor. Pros: complete spec implementation. Cons: significant scope for a first pass; the immediate supervisor already handles reply feedback for day-to-day changes.
2. **Informational only, approvals via normal reply flow** — Weekly review email is purely informational. Any approved changes the user wants to make, they reply to a digest email (same flow as always). Cons: proposed changes from the weekly review aren't directly actionable.
3. **Apply all proposed changes automatically (no approval step)** — Cons: violates the spec's separation of low-risk (auto-apply) vs. high-risk (human approval).

**Decision**: Apply low-risk changes automatically (consistent with immediate supervisor), send high-risk proposals in the review email with instructions to reply. Approval flow deferred to future work. In practice, the user can reply to any recent digest to approve a structural change — the immediate supervisor will handle it.

**Consequences**: High-risk changes proposed in the weekly review require the user to remember to reply to a digest separately. This is acceptable for a personal tool. Track in TODO.md.

---

## 2026-03-26: Sequential graph design (no fan-out) for immediate supervisor

**Status**: Accepted

**Context**: The 'both' reply type requires two independent operations: marking the digest
acknowledged AND processing the feedback config change. The natural LangGraph solution is
fan-out (two parallel branches). However, LangGraph's fan-out API changed between 0.2.x
versions and requires the `Send` primitive, which has more complex state management semantics.

**Options considered**:
1. **Fan-out via `Send`** — True parallel execution of log_acknowledgment and extract_change.
   Pros: semantically correct. Cons: Send API complexity, harder to test, version-sensitive.
2. **Sequential: maybe_acknowledge → route_feedback** — A single `maybe_acknowledge` node
   that conditionally calls `mark_digest_acknowledged` (no-op for non-acknowledge types),
   then routes to `extract_change` for feedback/both or END for acknowledge.
   Pros: simpler, version-stable, easy to test, no shared state merge needed.
   Cons: slightly less conceptually pure (acknowledgment and feedback are sequential not parallel).

**Decision**: Sequential design. Acknowledgment and feedback are not truly independent —
both need the digest_id and raw_reply from state. The sequential ordering (acknowledge first,
then extract change) is correct in practice and much easier to test and maintain.

**Consequences**: The graph is simpler and easier to reason about. The `maybe_acknowledge`
node is a no-op for pure feedback/irrelevant replies, adding one trivial step but keeping
routing consistent.

---

## 2026-03-26: Haiku for all immediate supervisor LLM calls (no Opus)

**Status**: Accepted

**Context**: The immediate supervisor makes two LLM calls per reply: classify and extract.
CLAUDE.md instructs to use Haiku for high-volume classification and Opus for reasoning-heavy
decisions. Needed to decide whether extraction requires Opus.

**Options considered**:
1. **Haiku for both classify and extract** — Fast, cheap. Extraction is structured JSON output
   with well-defined keys — Haiku handles this well.
2. **Haiku for classify, Opus for extract** — More capable extraction. Cons: 15x cost
   increase for the extraction call; extraction is a structured task, not open-ended reasoning.
3. **Opus for both** — Maximum quality. Cons: excessive cost for a per-reply task; overkill.

**Decision**: Haiku for both calls. Reply classification and config extraction are structured
JSON tasks with enumerated options. The prompts constrain the output space enough that Haiku
produces reliable results. Opus is reserved for the weekly pattern sweep (Phase 5), which
requires open-ended reasoning over many feedback events.

**Consequences**: Cost stays low for high-frequency reply polling. If extraction quality is
found to be poor in practice, the model can be upgraded for the extract call only without
changing the architecture.

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

---

## 2026-03-26: Weekend catch-up dedup delegates to DB query (no pgvector call in pipeline)

**Status**: Accepted

**Context**: Weekend catch-up needs to deduplicate stories that appeared across multiple days (e.g., the same Fed story covered Monday, Tuesday, and Wednesday). The task spec says "cross-day dedup using stored embedding vectors (pgvector cosine similarity)."

**Options considered**:
1. **Re-embed and similarity-search in the pipeline** — Load all stories, re-embed each with Voyage AI, compute pairwise cosine similarity, drop near-duplicates. Pros: flexible thresholding. Cons: re-embedding is unnecessary cost since embeddings are already stored; N² similarity computation; adds Voyage API dependency to weekend pipeline.
2. **pgvector query in db.py** — `get_unacknowledged_stories()` uses `DISTINCT ON (cluster_id)` to deduplicate — stories in the same cluster appear once. Pros: no re-embedding cost, dedup happens in the query, consistent with how the daily brief deduplicates. Cons: only deduplicates at the cluster level, not by embedding similarity (but cluster_id is the canonical dedup unit).
3. **Hybrid: use cluster_id as primary dedup, pgvector similarity as secondary** — Extra similarity pass over the deduplicated set. Cons: over-engineering; cluster_id already captures semantic identity since the daily brief assigned it.

**Decision**: Option 2 — delegate to `get_unacknowledged_stories()` which uses `DISTINCT ON (cluster_id)`. The cluster_id is assigned during the daily brief pipeline by the embedder+disambiguator. Two stories in the same cluster are already known duplicates. Running pgvector similarity again would be redundant. "Do not re-embed" is explicitly stated in the task spec.

**Consequences**: Weekend catch-up dedup quality is bounded by daily brief clustering quality. If a story was assigned a wrong cluster during the week, it may appear twice. Acceptable for a personal tool.

---

## 2026-03-26: Onboarding agent is a separate flow, not routed through the supervisor

**Status**: Accepted

**Context**: User onboarding requires scanning the inbox, emailing the user a source list, and processing their reply to set initial preferences. The existing supervisor (immediate mode) only processes replies to known digest thread IDs and writes to `feedback_events`, which has a NOT NULL `digest_id` foreign key. There is no digest at onboarding time.

**Options considered**:
1. **Route onboarding through the supervisor** — Make `feedback_events.digest_id` nullable, add an `event_source` column (`onboarding` vs `digest_reply`), and teach the supervisor to handle both. Pros: one reply-processing path. Cons: the supervisor's job is to improve digest quality from feedback; onboarding is a one-time setup task with different inputs, outputs, and risk profile. Mixing them complicates both.
2. **Separate `onboarding_events` table + `pipeline/onboarding.py`** — Onboarding has its own table, its own LLM processor, its own FastAPI endpoint (`/jobs/onboard`). The supervisor is untouched. Pros: clean separation of concerns; onboarding logic can evolve independently; no schema surgery on `feedback_events`. Cons: slightly more code surface.
3. **Make `feedback_events.digest_id` nullable** — Simplest schema change. Cons: loses the NOT NULL guarantee that every feedback event is tied to a real digest; makes the supervisor harder to reason about.

**Decision**: Option 2 — separate `onboarding_events` table and `pipeline/onboarding.py`. The supervisor and onboarding agent are distinct in purpose, trigger, and output. Keeping them separate maintains clear invariants on both sides.

**Consequences**: `feedback_events.digest_id` stays NOT NULL. Onboarding reply processing is in `pipeline/onboarding.py`. The `agent_config` table gains an `onboarding_complete` key that gates the daily brief pipeline. A Phase 6 schema migration adds `onboarding_events`.

---

## 2026-03-26: Deep Read formats each article individually, no synthesis LLM call

**Status**: Accepted

**Context**: Deep Read processes long-form essays/analyses. Needed to decide how to format 3–5 articles — could synthesize across them or present individually.

**Options considered**:
1. **Synthesize across articles** — Use synthesizer.py to merge insights from all articles into a meta-summary. Pros: concise. Cons: destroys the individual voice and nuance that makes long-form essays worth reading; misses the point of "deep read."
2. **Present each article individually at full treatment** — No LLM synthesis. Extract each article's content and present in full with source attribution and link. Pros: preserves author voice, lets the reader engage with each piece fully. Cons: longer digest.
3. **Use formatter.py's digest_type="deep_read"** — Force all stories to full treatment via the existing formatter. Cons: formatter doesn't support original links and synthesizes topics together.

**Decision**: Option 2 — custom `_format_deep_read()` that presents each article individually with its title, source, link, and full body. We import `extractor.py` for content extraction but bypass the synthesizer entirely. The format is sequential (article 1, article 2, ...) not topic-grouped.

**Consequences**: Deep read digest is longer and doesn't use formatter.py's topic grouping. The word budget is effectively unbounded (capped only by 3–5 articles × article length). The formatter.py import is still used for the subject line via `format_digest` in weekend_catchup — not deep_read.


---

## 2026-03-26: Cluster-level read tracking for cross-digest story deduplication

**Status**: Accepted

**Context**: Stories can appear in multiple digests — e.g., a daily brief and an on-demand brief triggered via email command. If the user acknowledges only one, the other remains "unacknowledged" and the story could re-appear in the weekend catch-up. Acknowledgment at the digest level alone doesn't prevent this.

**Options considered**:
1. **Digest-level acknowledgment only (current)** — `get_unacknowledged_stories` queries stories from unacknowledged digests. Simple, but a story in two digests appears in catch-up if only one digest is acknowledged.
2. **Story-level `read_at` on stories table** — Mark each story row individually. Requires updating every story in every digest that contains a given cluster, which is O(digests × stories). Also doesn't propagate automatically to future digests that include the same cluster.
3. **Cluster-level `read_at` on story_clusters** — One UPDATE per cluster marks the canonical story identity as read. Any future query that checks `sc.read_at IS NULL` automatically excludes it, regardless of how many digests the story appeared in. One migration, one new db.py function.

**Decision**: Option 3 — `read_at` on `story_clusters`. `mark_digest_acknowledged` calls `mark_clusters_read(digest_id)` which stamps all clusters referenced by that digest. `get_unacknowledged_stories` LEFT JOINs `story_clusters` and filters `sc.read_at IS NULL OR cluster_id IS NULL`.

**Consequences**: Stories with no `cluster_id` (NULL) are always included in catch-up — this is correct behaviour for older stories that predate the cluster assignment logic. The index `idx_story_clusters_unread` (partial, WHERE read_at IS NULL) keeps the weekend catch-up query fast even as the cluster table grows.

---

## 2026-03-26: Per-user onboarding_complete check for web sign-ups

**Status**: Accepted

**Context**: `run_onboarding()` guards against re-running with `get_config("onboarding_complete")` from `agent_config`. That flag was set to `true` during the original single-user CLI setup. When a new user signs in via the web app and hits `/api/setup`, `_run_onboard` calls `run_onboarding()` which immediately returns `already_complete` — the setup email is never sent.

**Options considered**:
1. **Reset the global flag on new web sign-up** — Clear `agent_config.onboarding_complete` when a new user authenticates. Pros: minimal code change. Cons: destructive if the original user's preferences are still in use; confusing semantics (the system IS onboarded, a specific user is not).
2. **Add `user_id` to `onboarding_events` (migration)** — Store which user triggered the onboarding so `process_onboarding_reply` can mark the right user complete. Pros: fully relational, correct for multi-user. Cons: requires schema migration; over-engineered for a personal single-user tool.
3. **Per-user flag with fallback to global** — `run_onboarding(run_id, user_id=None)`: if `user_id` provided, check `users.onboarding_complete`; if not provided (cron call), check the global `agent_config` flag. On reply, call `mark_users_onboarding_complete()` which updates all `onboarding_complete = false` users. Pros: no migration, correct semantics, clean fallback for cron path.

**Decision**: Option 3 — per-user flag with fallback. Web-triggered onboarding checks the per-user flag; cron-triggered onboarding uses the global flag (unchanged). `mark_users_onboarding_complete()` updates all pending users on reply — safe for a single-user deployment.

**Consequences**: Multiple concurrent users signing up before anyone replies to the setup email would all be marked complete when the first reply is processed. Acceptable for a personal tool. If this becomes multi-user, migrate `onboarding_events` to add `user_id` and scope the update to that user.

# News Briefing Agent — CLAUDE.md

> This file is the single source of truth for Claude Code working on this project.
> **Part 1** covers what we're building and how. **Part 2** covers engineering standards.
> Read both before making any changes.

---

# Part 1 — Project Context

## What This Project Is

A personal AI news digest system. It reads all newsletters from a Gmail inbox daily, deduplicates overlapping coverage across sources, synthesizes canonical stories with source attribution, and delivers clean plain-text email digests at defined time budgets. A supervisor agent learns from natural-language email replies and improves output over time.

The full product spec is in `SPEC.md`. Read it before making significant changes.

---

## Architecture

```
First run
    ↓
[Onboarding Agent] — scans inbox, emails user a source list with type corrections, processes reply
    ↓ (sets initial agent_config + newsletter_sources trust_weights + source types)

Gmail Inbox
    ↓
[Source Classifier] — detects newsletters via List-Unsubscribe header + sender patterns
    ↓ checks newsletter_sources.type before running length heuristic
    ↓ (news-brief)              ↓ (long-form)
[Daily Brief Pipeline]     [Deep Read Queue]
    ↓                               ↓
[Story Extractor]          [Deep Read Pipeline]
[Embedder + Clusterer]              ↓
[Web Search Enrichment]    [Deep Read Email]
[Web Topic Gap Fill]  ← agent_config: web_search_topics
[Synthesizer]         ← agent_config: synthesis_style_notes
[Ranker + Formatter]  ← agent_config: topic_weights, word_budget, source_trust_overrides
    ↓
[Daily Brief Email]
    ↓
[Gmail Archiver] — labels source emails "Briefed", removes from inbox

User replies to any digest
    ↓
[Supervisor Agent — Immediate Mode] — LangGraph
    ├── known config key (topic_weights, word_budget, synthesis_style_notes,
    │   web_search_topics, cosine_similarity_threshold) → auto-apply
    ├── source reclassification request → update newsletter_sources.type
    ├── unsubscribe → queue for confirmation
    └── unknown/structural → [CodeChangeAgent]
                                  ↓
                         Anthropic API + tool use
                         (read_file, write_file, run_bash)
                                  ↓
                         run pytest — must pass
                                  ↓
                         email diff to user
                         subject: "product input required for news briefing"
                                  ↓
                         user replies "approve"
                                  ↓
                         git push → Railway auto-deploy
    ↓ (weekly)
[Supervisor Agent — Pattern Sweep] — LangGraph

[Weekend Catch-Up Pipeline] — Sunday, draws from unacknowledged stories
```

---

## Tech Stack

- **Runtime**: Python 3.11+
- **Framework**: FastAPI (job endpoints + future web app/multi-user support)
- **LLM**: Anthropic `claude-opus-4-6` (synthesis, supervisor), `claude-haiku-4-5` (extraction, classification)
- **Embeddings**: Voyage AI `voyage-3` (Anthropic's recommended embeddings partner — Claude has no native embeddings API)
- **Orchestration**: LangChain + LCEL (linear pipeline steps), LangGraph (supervisor agent, disambiguation loop)
- **Tracing**: LangSmith
- **Email**: Gmail API (raw) for reading, archiving, thread detection, reply detection, and sending. No third-party email service.
- **Web search**: Tavily API
- **Database**: Supabase (PostgreSQL + pgvector extension)
- **Hosting**: Railway (set up at deployment time, not during development)
- **Scheduling**: Railway cron → hits FastAPI job endpoints (e.g. `POST /jobs/daily-brief`)

### Key LangChain/LangGraph components
- `ChatAnthropic` — LLM calls
- `VoyageAIEmbeddings` — story embeddings
- `ChatPromptTemplate` + `JsonOutputParser` — structured extraction
- `LCEL chains` — story extraction, synthesis pipelines
- `TavilySearchResults` — web enrichment tool
- `LangGraph StateGraph` — supervisor agent (both modes), cluster disambiguation
- `LangSmith` — tracing all LLM calls

---

## Non-Obvious Design Decisions

> These are project-level decisions made before development began. Log new decisions in `DECISIONS.md` using the format defined in Part 2.

**Why raw Gmail API instead of LangChain's GmailLoader:**
GmailLoader only reads email content. We need thread detection (to catch replies), archiving (label + inbox removal), reply detection, header inspection (List-Unsubscribe), and sending. GmailLoader exposes none of this. We use raw Gmail API for everything.

**Why LangGraph for supervisor, not LCEL:**
The supervisor has branching logic (acknowledge vs. feedback vs. both), conditional tool calls (unsubscribe), and a loop structure (weekly pattern analysis). LCEL is for linear chains. LangGraph handles stateful loops with conditional edges.

**Why LangGraph for cluster disambiguation too:**
Ambiguous cluster resolution may need to fetch additional context before deciding merge/split. That's a loop with tool use — LangGraph, not a single LLM call.

**Why pgvector instead of a separate vector DB:**
Story embeddings need to be queried alongside relational data (digest_id, acknowledged status, date range). Keeping everything in Postgres avoids cross-DB joins and simplifies the weekend catch-up deduplication query.

**Supervisor feedback is immediate, not batched:**
Every reply triggers the supervisor in real-time. The weekly sweep is for pattern analysis only. Low-risk changes (topic weights, word budget) apply immediately. High-risk changes (prompt edits) are queued for approval.

**Web search only for single-source stories:**
Multi-source stories are already cross-validated across newsletters. Single-source stories get Tavily enrichment to find primary sources, official statements, and data. Bounded to one search per single-source story per run.

**Anchor-based pipeline trigger:**
Daily brief triggers when Axios AM + Morning Brew have both arrived in inbox (polled every 15 min). Hard cutoff at 10am regardless. This ensures the brief is comprehensive without waiting indefinitely.

---

## Database Schema

See `schema.sql` (to be created in Phase 1). Key tables:
- `digests` — each sent digest with type, timestamps, acknowledgment status
- `stories` — individual synthesized stories with embeddings, treatment level, sources
- `story_clusters` — canonical cluster records for cross-day deduplication
- `feedback_events` — raw replies to digests, supervisor interpretation, applied changes (digest_id NOT NULL — onboarding replies do not go here)
- `onboarding_events` — setup email thread_id, raw user reply, sources confirmed/deprioritized, applied status (Phase 6)
- `agent_config` — runtime config (topic weights, prompts, word budgets) with rollback; includes `onboarding_complete` key
- `newsletter_sources` — discovered sources, classification, trust weight, unsubscribe info

---

## Phased Build Roadmap

### Phase 1 — Foundation ◯
- Gmail OAuth2 setup and service wrapper (read, archive, thread detection, reply detection)
- Supabase project + pgvector extension + schema.sql
- Source classifier (List-Unsubscribe header + sender pattern detection)
- `newsletter_sources` registry with upsert on discovery
- Anchor detection logic (poll for Axios AM + Morning Brew)
- FastAPI job endpoints (`POST /jobs/daily-brief`, `/jobs/poll-replies`, etc.)
- Railway cron config (triggers job endpoints on schedule)

### Phase 2 — Core Pipeline ◯
- Story extractor: HTML strip → LLM extraction → `{title, body, key_facts, source}`
- Embedding + cosine similarity clustering (pgvector)
- LangGraph disambiguation loop for ambiguous clusters
- Story synthesizer: multi-source → canonical story via LCEL chain
- Tavily web enrichment for single-source stories
- Ranker (source count, topic weights, recency)
- Formatter (tiered treatment, word budget, topic grouping)
- Plain text email delivery via Gmail API
- Gmail archiver (label "Briefed", remove from inbox)
- Digest + story logging

### Phase 3 — Acknowledgment & Immediate Supervisor ◯
- Gmail reply detection on known digest threads
- LLM reply classifier (acknowledgment / feedback / both)
- LangGraph supervisor — immediate mode
- `agent_config` read/write for runtime config updates
- Unsubscribe flow (confirm → execute List-Unsubscribe → mark inactive)
- `feedback_events` logging

### Phase 4 — Weekend Catch-Up & Deep Read ◯
- Weekend catch-up pipeline (unacknowledged story query, dedup across days, Sunday trigger)
- Deep Read pipeline (long-form queue, threshold + Thursday fallback trigger)
- Deep Read formatter (depth-first, 3-5 articles, original links)

### Phase 5 — Weekly Supervisor & Polish ◯
- LangGraph supervisor — weekly pattern sweep mode
- Weekly review email format
- LangSmith instrumentation across all LLM calls
- Pipeline failure retry logic + alert email
- Error handling and resilience hardening

### Phase 7 — Self-Improving Agent ◯
- `supervisor/code_change_agent.py` — Anthropic API agent with `read_file`, `write_file`, `run_bash` tools
- Triggered by `validate_change_node` when feedback doesn't map to any known config key
- Drafts code changes, runs test suite as gate, emails diff to user
- Subject line: `product input required for news briefing`
- Approval reply triggers `git push` → Railway auto-deploys
- Scope constraints: no schema migrations, no `main.py` job routing changes without flagging for manual review

### Phase 6 — Onboarding ◯
- `pipeline/onboarding.py` — first-run flow: scan inbox via source_classifier, build discovered source list, send setup email asking user to identify important sources
- `onboarding_events` table migration — stores setup email thread_id, raw reply, parsed preferences, applied status
- `agent_config` key: `onboarding_complete` (boolean) — gates the `/jobs/onboard` endpoint; daily-brief endpoint checks this before running
- Reply polling for setup email thread — detected via `gmail_service.get_replies()` on stored thread_id
- Onboarding reply processor — LLM parses free-text reply to extract source priorities; writes `topic_weights` + `newsletter_sources.trust_weight` to DB; sets `onboarding_complete: true`
- `/jobs/onboard` FastAPI endpoint — one-time trigger; no-ops if `onboarding_complete` is true
- `ONBOARDING_COMPLETE` guard in `_run_daily_brief()` — if false, send a reminder and skip the run

---

## Project-Specific Conventions

These conventions are specific to this project. They supplement (and in case of conflict, override) the general engineering standards in Part 2.

- **All LLM calls go through LangChain.** No raw `httpx` or `requests` to Anthropic. This ensures LangSmith traces everything automatically.
- **Prompts are defined as `ChatPromptTemplate` objects** in the module that uses them. Baseline prompts live in code; supervisor overrides are stored in `agent_config` and merged at runtime.
- **All DB access goes through `tools/db.py` helpers.** No inline SQL in pipeline code. If you need a new query, add a function to `db.py`.
- **Digests are always plain text.** No HTML email, no templating libraries.
- **Never delete emails.** Archive only (Gmail label + inbox removal).
- **Unsubscribe requires explicit user confirmation.** Never execute unilaterally.
- **One Tavily search per single-source story per run.** Do not add additional search calls without logging a decision in `DECISIONS.md`.

---

## File Structure

```
news-briefing-agent/
├── CLAUDE.md               # This file — project context + engineering standards
├── SPEC.md                 # Full product spec (read before major changes)
├── DECISIONS.md            # Architectural decision log (see Part 2)
├── TODO.md                 # Prioritized work tracker (see Part 2)
├── CHANGELOG.md            # Human-readable change history (see Part 2)
├── AGENT_INSTRUCTIONS.md
├── schema.sql
├── requirements.txt
├── .env.example
├── .gitignore
├── main.py                 # FastAPI app + job endpoints (triggered by Railway cron)
├── gmail_service.py        # Raw Gmail API wrapper
├── source_classifier.py    # Newsletter detection + routing
├── pipeline/
│   ├── daily_brief.py      # Main daily pipeline orchestrator
│   ├── onboarding.py       # First-run onboarding flow (Phase 6)
│   ├── deep_read.py        # Deep read pipeline
│   ├── weekend_catchup.py  # Weekend catch-up pipeline
│   ├── extractor.py        # LLM story extraction (LCEL)
│   ├── embedder.py         # Embedding + pgvector clustering
│   ├── disambiguator.py    # LangGraph cluster disambiguation
│   ├── synthesizer.py      # LLM story synthesis (LCEL)
│   ├── enricher.py         # Tavily web search enrichment
│   ├── ranker.py           # Story ranking
│   └── formatter.py        # Digest formatting + word budget
├── supervisor/
│   ├── immediate.py        # LangGraph supervisor — reply-triggered
│   ├── weekly.py           # LangGraph supervisor — pattern sweep
│   └── code_change_agent.py  # Anthropic tool-use agent for structural changes (Phase 7)
├── tools/
│   └── db.py               # Supabase/Postgres helpers
└── tests/
    ├── test_source_classifier.py
    ├── test_extractor.py
    ├── test_embedder.py
    ├── test_synthesizer.py
    ├── test_ranker.py
    ├── test_formatter.py
    ├── test_gmail_service.py
    ├── test_supervisor_immediate.py
    ├── test_db.py
    └── conftest.py          # Shared fixtures (mock emails, sample stories, db setup)
```

---

## Environment Variables

See `.env.example` for full list with descriptions and placeholder formats.

Required:
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` — Gmail OAuth2
- `ANTHROPIC_API_KEY` — Claude API access
- `VOYAGE_API_KEY` — Voyage AI embeddings
- `TAVILY_API_KEY` — Web search enrichment
- `LANGCHAIN_API_KEY` — LangSmith tracing
- `DATABASE_URL` — Supabase PostgreSQL connection string

Optional:
- `ALERT_EMAIL` — recipient for pipeline failure alerts
- `CODE_CHANGE_NOTIFY_EMAIL` — recipient for CodeChangeAgent diffs and approvals (defaults to `ALERT_EMAIL` if not set)
- `GOOGLE_OAUTH_CLIENT_ID` — OAuth 2.0 "Web application" client ID for user sign-in (separate from `GMAIL_CLIENT_ID`)
- `GOOGLE_OAUTH_CLIENT_SECRET` — paired secret for the web app OAuth client
- `GOOGLE_OAUTH_REDIRECT_URI` — must match an authorized redirect URI in Google Cloud Console (e.g. `https://[domain]/auth/google/callback`)
- `SESSION_SECRET_KEY` — 32-byte hex string for signing session cookies with `itsdangerous`
- `UNSUBSCRIBE_SECRET_KEY` — 32-byte hex string for HMAC-signing unsubscribe tokens in brief footers

All env vars must follow the configuration rules in Part 2 (validate at startup, no magic strings, type-safe parsing).

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run FastAPI + scheduler
uvicorn main:app --reload

# Simulate a pipeline run (dev mode, no email sent)
python -m pipeline.daily_brief --dry-run

# Run tests
pytest tests/ -v
```

---

## Deploying to Railway

`railway.toml` configures the web service (build + start command + health check).
Cron jobs are separate Railway services. Create each in the Railway dashboard as a
**Cron** service type pointing to the same repo, with the start commands and schedules below.

Set `WEB_SERVICE_URL` as a shared env var (the public URL of the web service).

### Current status (as of 2026-03-26)

| Service name | Cron schedule | Start command | Status |
|---|---|---|---|
| `daily-brief` | `*/15 6-10 * * 1-5` | `curl -sS -X POST $WEB_SERVICE_URL/jobs/daily-brief` | ✅ Configured |
| `poll-replies` | `*/15 * * * *` | `curl -sS -X POST $WEB_SERVICE_URL/jobs/poll-replies` | ✅ Configured |
| `deep-read` | `0 9 * * 1-5` | `curl -sS -X POST $WEB_SERVICE_URL/jobs/deep-read` | ✅ Configured |
| `weekend-catchup` | `0 8 * * 0` | `curl -sS -X POST $WEB_SERVICE_URL/jobs/weekend-catchup` | ✅ Configured |
| `supervisor-weekly` | `0 7 * * 0` | `curl -sS -X POST $WEB_SERVICE_URL/jobs/supervisor-weekly` | ✅ Configured |

**Action required**: Set `ALERT_EMAIL` on the web service — pipeline failures are silently logged only (`alert_skipped reason=ALERT_EMAIL not set` confirmed in production logs).

Notes:
- `daily-brief` polls every 15 min Mon–Fri from 6–10am. The pipeline checks anchor sources before running, and exits early if the brief was already sent today (`was_brief_sent_today()` guard prevents duplicate sends after archiving).
- `supervisor-weekly` runs at 7am Sunday — before `weekend-catchup` at 8am — so the review email reflects a complete week.
- All env vars (see Environment Variables section) must be set on the web service. Cron services only need `WEB_SERVICE_URL`.
- **`ALERT_EMAIL` is not currently set** — without it, pipeline failures are silently logged but never emailed. Set it to your address in Railway environment variables.

---

# Part 2 — Engineering Standards

> These standards apply to all code written in this project. They are not suggestions.

---

## Testing

### Requirements

- **Every functional change must include tests.** No exceptions. If you're writing a function, you're writing a test. If you're fixing a bug, you're writing a regression test that fails without the fix and passes with it.
- **Test the behavior, not the implementation.** Tests should describe *what* the code does, not *how* it does it internally. If you're mocking more than two layers deep, your design is wrong — refactor first.
- **Test taxonomy — use all three levels:**
  - **Unit tests**: Pure logic, no I/O, no network, no filesystem. These should run in <1ms each. Aim for >90% line coverage on business logic modules (ranker, formatter, source_classifier, synthesizer logic).
  - **Integration tests**: Test real interactions between components — `db.py` against a test database, `gmail_service.py` with mock Gmail responses, LCEL chains with mocked LLM responses via `FakeListChatModel`.
  - **Smoke tests / E2E tests**: For each pipeline (daily_brief, deep_read, weekend_catchup), write at least one happy-path test that exercises the full pipeline with fixture data and `--dry-run` mode.
- **Edge cases are not optional.** For every function, think about: empty inputs, null/undefined, boundary values, error cases, concurrent access (if applicable). Write tests for at least the top 3 most likely failure modes.
- **Test naming convention**: `test_<unit>_<scenario>_<expected_outcome>`. Example: `test_source_classifier_missing_unsubscribe_header_classifies_as_unknown`. The test name should read like a spec.
- **No test should depend on another test's state.** Tests must be independently runnable and order-independent.
- **If you cannot write a test for something, say so explicitly and explain why.** Do not silently skip testing. Common valid reasons: live Gmail API calls, Tavily rate limits, Supabase in CI. Invalid reasons: "it's too simple to test," "it's just a wrapper."

### Project-specific testing notes

- **LLM calls in tests**: Use LangChain's `FakeListChatModel` or `FakeMessagesListChatModel` for unit tests. Never call real Anthropic API in tests — it's slow, costly, and non-deterministic.
- **Embedding tests**: Mock `VoyageAIEmbeddings` with deterministic fake vectors. Test clustering logic separately from embedding generation.
- **Gmail fixtures**: Create realistic email fixtures in `tests/conftest.py` — include plain text, HTML newsletters, edge cases (empty body, missing headers, non-English content, forwarded emails).
- **Database tests**: Use a separate test database or transaction rollbacks. Never test against production Supabase.

### Test quality checks

Before considering tests complete, verify:
1. Remove the implementation — do the tests actually fail? (If not, they're testing nothing.)
2. Introduce a subtle bug (off-by-one, wrong cosine similarity threshold, incorrect topic weight) — does at least one test catch it?
3. Are assertion messages descriptive enough to diagnose failures without reading test code?
4. Are you testing the *contract*, not the *implementation*? (Tests shouldn't break when you refactor internals.)

---

## Documentation and Decision Logging

### Core principle

**Code tells you *what* happens. Documentation tells you *why* it happens and *what else was considered*.** Every decision that wasn't obvious should leave a trace. Six months from now, neither you nor the human developer should have to reverse-engineer intent from code.

### Project file ecosystem

Maintain these files at the project root. If they don't exist, create them on the first relevant change. If they exist, keep them current — stale docs are worse than no docs.

#### `DECISIONS.md`
An append-only log of architectural and design decisions made *during development*. The foundational decisions are already in the "Non-Obvious Design Decisions" section of Part 1 — `DECISIONS.md` captures everything after that.

**Format for each entry:**
```
## YYYY-MM-DD: [Short title of the decision]

**Status**: Accepted | Superseded by [link] | Deprecated

**Context**: What situation or problem prompted this decision?

**Options considered**:
1. [Option A] — [Pros]. [Cons].
2. [Option B] — [Pros]. [Cons].
3. [Option C] — [Pros]. [Cons].

**Decision**: We chose [Option X] because [reasoning].

**Consequences**: What does this mean going forward? What trade-offs are we accepting? What becomes easier or harder?
```

**When to add an entry:**
- Choosing between two or more reasonable approaches
- Introducing a new dependency or tool
- Deciding on a data model or schema change
- Establishing a pattern that the rest of the codebase should follow
- Deviating from an established pattern (and why)
- Choosing NOT to do something (these are often the most valuable entries)
- Changing a cosine similarity threshold, word budget, or any other tuned parameter — include what you tested and why you landed on the new value
- Any decision where someone might later ask "why did we do it this way?"

**You must log a decision any time you find yourself weighing trade-offs.** If you considered more than one approach, that's a decision worth recording.

#### `TODO.md`
A living, prioritized list of known work. Cross-references the phased roadmap in Part 1 but tracks granular tasks.

**Format:**
```
# TODO

## High Priority
- [ ] [Description of task] — [Why it matters or what's blocked by it]

## Medium Priority
- [ ] [Description of task] — [Context]

## Low Priority / Nice to Have
- [ ] [Description of task] — [Context]

## Completed (recent)
- [x] [Description] — Completed YYYY-MM-DD
```

**Update rules:**
- When you complete a task → move it to Completed with the date and update the phase status in Part 1 if the phase is done (◯ → ●)
- When you discover a new issue or improvement while working → add it (don't fix it silently and don't ignore it)
- When a task becomes irrelevant → remove it with a brief note why
- Keep Completed items for the last 2-4 weeks, then archive or remove
- When you encounter a `TODO` or `FIXME` comment in code, it must also have a corresponding entry here. Inline TODOs are invisible; this file is the index.

#### `CHANGELOG.md`
A human-readable history of notable changes.

**Format:**
```
# Changelog

## [Unreleased]
### Added
- [What new capability was added and why it matters]
### Changed
- [What existing behavior changed and why]
### Fixed
- [What bug was fixed and how it manifested]
### Removed
- [What was removed and why]
```

**Update rules:**
- Every user-facing or behavior-changing commit should have a CHANGELOG entry
- Write entries for humans: "Added anchor-based trigger that waits for Axios AM + Morning Brew before running daily brief" not "Updated scheduler logic"
- Internal refactors with no behavior change do not need entries

#### `README.md`
This project uses CLAUDE.md as the primary project doc. If a separate README.md is created (e.g., for a public repo), it should contain a subset: what the project does, setup instructions, and how to run it. Keep it synced with the relevant sections of Part 1.

### Inline documentation standards

- **Function/method docstrings**: Required for any function that is public, non-trivial, or has non-obvious parameters. Describe what it does, what it takes, what it returns, and what errors it can raise. Do NOT describe *how* it works internally.
- **Prompt documentation**: Every `ChatPromptTemplate` must have a comment above it explaining: what the LLM is being asked to do, what format the output should be in, and any non-obvious prompt engineering decisions (e.g., "We ask for JSON with key_facts as an array because structured extraction with JsonOutputParser is more reliable than free-text extraction").
- **"Why" comments**: Add comments only when the *why* isn't obvious from the code. Good: `# We use 0.82 threshold (not 0.85) because newsletter titles often share boilerplate text that inflates similarity`. Bad: `# Calculate cosine similarity`.
- **TODO/FIXME/HACK comments**: Allowed, but must include context. Format: `# TODO(context): description — reason it's not done now`. Every inline TODO must also appear in `TODO.md`.
- **No commented-out code.** That's what git history is for. Delete it.

### Documentation timing

**Documentation is not a follow-up task. It is part of the implementation.**

- Write/update docs *during* the change, not after
- If you're about to commit and haven't updated relevant docs, the change is not complete
- When in doubt about whether a doc update is needed: it is

---

## Git Discipline

### Commit messages

Every commit message should be useful to someone reading `git log` six months from now.

```
<type>: <concise summary of what changed> (imperative mood, <72 chars)

<optional body: WHY this change was made, not WHAT changed (the diff shows that).
Include context that isn't obvious from the code.>

<optional footer: references to DECISIONS.md entries, TODO.md items, or phase numbers>
```

**Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `security`

**Examples of good commit messages:**
```
feat: add anchor-based trigger for daily brief pipeline

Polls Gmail every 15 min for Axios AM + Morning Brew. Triggers pipeline when
both arrive or at 10am hard cutoff, whichever comes first. This ensures the
brief captures the major morning newsletters without waiting indefinitely.

Phase 1, ref: DECISIONS.md 2026-03-25
```

```
fix: prevent duplicate story clusters across consecutive days

The cosine similarity check wasn't considering stories from the previous day's
digest, causing Monday's brief to re-synthesize stories that were already in
Sunday's weekend catch-up. Added 48-hour lookback window to the clustering query.
```

**Bad commit messages:** `update files`, `fix bug`, `WIP`, `changes`, `refactor stuff`

### Commit size and atomicity

- **One logical change per commit.** If you can describe the commit with "and," split it.
- **Every commit should leave the codebase in a working state.** Tests should pass at each commit.
- **Separate refactoring from behavior changes.** Restructure in one commit, add the feature in the next.
- **Never mix formatting/style changes with functional changes.**

### Branch hygiene

- Descriptive branch names: `feat/story-extractor`, `fix/duplicate-clusters`, not `test-branch`
- Delete branches after merging
- Keep branches short-lived

---

## Error Handling

### Philosophy

**Errors are not exceptional — they are part of the design.** This project interacts with Gmail, Anthropic, Voyage AI, Tavily, and Supabase — any of which can fail at any time.

### Rules

1. **Fail fast and loud.** If something is wrong, surface it immediately with a clear error. Do not silently return defaults, empty arrays, or `None` and hope the caller checks.

2. **Error messages must be actionable.** Every error message should answer three questions:
   - *What* happened? ("Failed to fetch emails from Gmail")
   - *Why* it likely happened? ("OAuth token refresh returned 401")
   - *What to do about it?* ("Re-run OAuth flow — token may have been revoked. See CLAUDE.md Environment Variables section.")

   Bad: `Error: API call failed`
   Good: `Error: Anthropic API returned 429 (rate limited) during story synthesis. 23 of 31 stories were synthesized before failure. Consider reducing batch size or adding delay between calls.`

3. **Never swallow errors silently.** These patterns are banned:
   ```python
   # BANNED
   try:
       do_something()
   except:
       pass

   # BANNED
   try:
       result = fetch_data()
   except Exception as e:
       logger.error(e)
       result = []  # silently returns empty
   ```

4. **Catch specific exceptions.** `except httpx.TimeoutException` not `except Exception`. `except KeyError` not bare `except`.

5. **Distinguish between recoverable and unrecoverable errors.**
   - **Recoverable**: Gmail API timeout (retry with backoff), Tavily search fails for one story (skip enrichment for that story, log, continue), single email parse failure (skip that email, log, continue pipeline).
   - **Unrecoverable**: Missing API keys (crash at startup), database connection failure (crash), corrupt schema (crash). Do not add retry logic for things that will never succeed.

6. **Pipeline resilience rule**: A single bad email or a single failed LLM call should never crash the entire daily brief pipeline. Log the failure, skip the item, and continue. But if >50% of items fail, abort the run and send an alert — something systemic is wrong.

7. **Use structured error types, not string matching.** If downstream code needs to branch on error type, use custom exception classes, not `if "timeout" in str(error)`.

8. **Log at the right level.**
   - `ERROR`: Pipeline aborted, email delivery failed, all retries exhausted. Needs human attention.
   - `WARNING`: Single story skipped, one API call retried successfully, email parsed with fallback.
   - `INFO`: Pipeline started/completed, digest sent, N stories synthesized, supervisor processed reply.
   - `DEBUG`: Individual LLM call details, embedding vectors, similarity scores.

---

## Logging and Observability

### Structured logging

All logs must be structured (key-value pairs), not free-text.

```python
# BAD
logger.info(f"Processed {len(stories)} stories for digest {digest_id}")

# GOOD
logger.info("stories_processed", digest_id=digest_id, story_count=len(stories), pipeline="daily_brief")
```

### What to log

- **Every LLM call**: model, prompt token count, completion token count, latency, success/failure. (LangSmith handles this if all calls go through LangChain — but add structured logs for pipeline-level observability too.)
- **Every external API call**: Gmail, Voyage, Tavily, Supabase. Include: endpoint/operation, duration, success/failure, response code.
- **Pipeline lifecycle**: pipeline started (with config: anchor emails found, story count), pipeline completed (stories synthesized, digest word count, delivery status).
- **Supervisor actions**: reply received, classification result, config change applied/queued.
- **Errors and exceptions**: with full context (see Error Handling section).

### What never to log

- **Secrets**: API keys, tokens, OAuth credentials, database connection strings. Ever.
- **Full email bodies in production**: Log sender, subject, byte size — not content (privacy).
- **Full LLM prompts in production** unless debugging a specific issue. LangSmith handles prompt tracing separately.

### Correlation

Every pipeline run should have a unique `run_id` that propagates through all log entries, LLM calls (via LangSmith metadata), and database records. When something breaks, you should be able to grep a single ID and see the full story.

---

## Performance Awareness

Not premature optimization — basic literacy for a system that processes dozens of emails and makes dozens of LLM calls per run.

### Rules

1. **Know your data size.** A typical daily run processes 15-30 newsletter emails, extracts 40-80 raw stories, clusters them into 15-30 canonical stories. Design for 2x this comfortably, panic at 10x.

2. **No unbounded operations.**
   - Database queries: always have a `LIMIT` or date range. Never `SELECT * FROM stories`.
   - LLM calls: always set `max_tokens`. Never let a synthesis call run unbounded.
   - Email fetching: page through Gmail results, don't fetch all at once.
   - Embedding batches: batch Voyage API calls (up to their limit), don't embed one at a time.

3. **Watch for N+1 queries.** If you're calling `db.py` inside a loop, you almost certainly have an N+1 problem. Batch the query.

4. **LLM cost awareness.** Opus is ~15x the cost of Haiku per token. Use Haiku for extraction and classification (high volume, structured output). Use Opus only for synthesis and supervisor reasoning (lower volume, requires nuance). If you're tempted to use Opus for a new call, justify it in DECISIONS.md.

5. **Embedding cost awareness.** Voyage charges per token. Batch embeddings. Don't re-embed stories that already have embeddings in the database — check first.

6. **Lazy over eager.** Don't fetch email bodies until you've classified the sender. Don't embed stories until you've deduplicated by title. Don't enrich with Tavily until you've confirmed it's a single-source story.

---

## Security

### Secrets management

- **Never commit secrets.** No API keys, tokens, passwords, or connection strings in source code. Not even "temporarily." Not even in test files.
- **`.env` for local development**, `.env.example` committed with placeholder values, `.env` in `.gitignore`.
- **Validate all required env vars at startup.** If any are missing, crash immediately listing all missing vars (not just the first one). See the Environment Variables section in Part 1 for the required list.
- **OAuth token handling**: Gmail refresh tokens are sensitive. Store in `.env`, never log them, never include them in error messages.

### Input validation

- **Validate all external input at the boundary.** Email content can contain anything — malformed HTML, scripts, binary attachments, non-UTF-8 encoding. Validate and sanitize before processing.
- **LLM output validation**: LLM responses are external input too. When using `JsonOutputParser`, handle parse failures gracefully. When extracting structured data, validate the schema before using it.
- **Reply detection**: Uses Gmail API polling (every 15 min) on known digest thread IDs — not push notifications. No webhook secret needed.

### Dependency security

- **Pin exact versions in `requirements.txt`.** No `>=` or `~=` in production.
- **Evaluate before adding.** Before adding a dependency: is it actively maintained? Do we actually need it, or can stdlib handle it? Log the decision in DECISIONS.md.

---

## Backward Compatibility and Safe Changes

### Database migration discipline

- **Never delete a column in the same deploy that removes the code using it.** First deploy: stop writing. Second deploy: stop reading. Third: drop column.
- **Never rename a column.** Add new, migrate data, update code, then (much later) drop old.
- **Every migration must be reversible.** Write the rollback at the same time.
- **Schema changes are logged in DECISIONS.md** with before/after and migration strategy.

### Config changes are code changes

Adding, removing, or changing environment variables or `agent_config` keys requires the same care as code changes: update `.env.example`, update CLAUDE.md, add startup validation.

---

## Configuration and Secrets Hygiene

| Type | Where it lives | Example |
|---|---|---|
| **Secrets** | `.env` only, never in code | `ANTHROPIC_API_KEY`, `DATABASE_URL` |
| **Environment-specific config** | `.env` or `agent_config` table | `LOG_LEVEL`, topic weights |
| **Application constants** | Named constants in code | `DEFAULT_COSINE_THRESHOLD = 0.82`, `MAX_STORIES_PER_DIGEST = 30` |
| **Tunable parameters** | `agent_config` table (supervisor-managed) | Word budgets, topic weights, prompt overrides |

### Rules

1. **Every env var documented in `.env.example`** with a description and placeholder showing the expected format.
2. **Validate config at startup, not at point of use.** Crash immediately if anything required is missing.
3. **No magic strings.** Config values used in more than one place must be defined once and imported.
4. **Tunable vs. fixed**: Parameters the supervisor can change live in `agent_config`. Parameters that require a code change are constants. Don't mix these up — if something is a constant today but should be tunable, that's a decision to log.

---

## Code Review (Self-Review Before Every Commit)

### Pre-commit review protocol

Before presenting any code as complete or ready to commit, perform a full self-review. This is a blocking step.

**Review checklist (go through every item):**

1. **Re-read the requirements.** Does the code solve the stated problem? Check against SPEC.md and the relevant phase in the roadmap.
2. **Read every diff line.** For each changed line: Is this necessary? Is this correct? Is this clear?
3. **Check for dead code.** Commented-out code, unused imports, unused variables, unreachable branches, uncalled functions.
4. **Check for hardcoded values.** Should any string, number, or threshold be a constant, config value, or `agent_config` parameter instead?
5. **Check error handling.** Does every error path follow the Error Handling rules? Pipeline resilience maintained?
6. **Check naming.** Self-documenting names. No comments needed to explain what a variable holds.
7. **Check for duplication.** Similar logic in two places → extract. But don't over-abstract.
8. **Check types and contracts.** Clear function signatures. Type hints on all public functions.
9. **Check for security issues.** Secrets in code? Unsanitized email content? Unverified webhooks? Raw SQL?
10. **Check performance.** N+1 queries? Unbounded loops? Opus where Haiku would suffice?
11. **Check backward compatibility.** Schema changes safe? Config changes documented?
12. **Run the tests.** `pytest tests/ -v`. Confirm they pass. If you can't run them, say so explicitly.
13. **Check documentation.** DECISIONS.md, TODO.md, CHANGELOG.md updated? Docstrings current? Prompt documentation present? Orphaned TODOs?
14. **Check git hygiene.** Commit message follows the format? Change is atomic?
15. **Check project conventions.** All LLM calls through LangChain? All DB access through `db.py`? No HTML in digests? No email deletion?

### Review output format

After self-review, state:
- **Changes made during review**: (list anything fixed during the review pass)
- **Docs updated**: (which project files were touched and why)
- **Remaining concerns**: (anything uncertain or warranting human review)
- **Test results**: (pass/fail)

---

## Code Quality and Anti-Bloat Rules

### Size discipline

- **One logical change per commit.**
- **Function length: aim for <30 lines.** Hard ceiling at 40 — extract sub-functions.
- **File length: aim for <300 lines.** Hard ceiling at 400 — split by domain concept.
- **New dependency = DECISIONS.md entry.** Justify what it does, why stdlib/existing deps can't, and its maintenance status.

### Anti-slop rules

The most common failure modes of AI-generated code. Actively guard against all of them:

1. **No premature abstraction.** No interfaces, base classes, factories, or strategy patterns unless there are already two or more concrete use cases.
2. **No placeholder implementations.** Either implement it or flag it in TODO.md with context.
3. **No over-commenting.** Don't restate the code. Comment only on *why*.
4. **No defensive over-engineering.** No retry logic, circuit breakers, or caching unless there's a demonstrated need. (Exception: the pipeline resilience rule in Error Handling — that's a demonstrated need.)
5. **No copy-paste drift.** Extract parameterized functions when duplicating logic.
6. **No import hoarding.** Only import what you use.
7. **No type-soup.** Don't create types/dataclasses for things used once with obvious structure.
8. **No wrapper functions that add nothing.**
9. **String formatting over concatenation.** Always use f-strings or `.format()`.
10. **Consistent patterns.** Read the surrounding code before writing new code. Use existing `db.py` helpers, existing prompt patterns, existing error handling patterns.

### When in doubt

"If I delete this code/file/abstraction, does anything break or become meaningfully harder to understand?" If no, delete it.

---

## Architectural Layer Boundaries

This project has a strict dependency hierarchy. Layers may only import from layers below them. No layer may import from a layer above it. No circular imports.

```
schema.sql          ← data shape definitions (no Python imports)
       ↓
tools/db.py         ← DB helpers only; no pipeline or supervisor imports
       ↓
pipeline/*.py       ← pipeline steps; imports from tools/ only
       ↓
supervisor/*.py     ← supervisor + agents; imports from tools/ and pipeline/
       ↓
main.py             ← FastAPI app; imports and orchestrates all layers
```

**Hard rules:**
- `pipeline/` modules must never import from `supervisor/`
- `tools/db.py` must never import from `pipeline/` or `supervisor/`
- Pipeline steps do not call each other directly — orchestration happens in `daily_brief.py`, `deep_read.py`, `weekend_catchup.py`
- Shared logic needed by multiple layers belongs in `tools/`, not copy-pasted across files

Violations are architectural debt. If you find one, fix it immediately and log it in DECISIONS.md. If a boundary needs to change, log that decision before changing it.

---

## Consistency Sweeps

At the end of any significant work session — or any time a task spans multiple files — run this sweep before presenting work as complete. It catches drift that accumulates silently between code, docs, and configuration.

**Sweep checklist:**

1. **TODO drift** — Are all items in `TODO.md` still valid? Any inline `# TODO` in code without a matching `TODO.md` entry?
2. **Dead imports** — Any `import` statements for modules not referenced in the file?
3. **Dead code** — Any functions, classes, or variables defined but never called?
4. **`.env.example` sync** — Does every `os.environ.get()`/`os.getenv()` call have an entry in `.env.example`? Any `.env.example` entries no longer used in code?
5. **Schema sync** — Does `schema.sql` match what `db.py` queries? Any column referenced in code that doesn't exist in schema?
6. **DECISIONS.md references** — Do all `ref: DECISIONS.md` comments in code point to real, non-superseded entries?
7. **CHANGELOG currency** — Has any user-facing behavior changed without a CHANGELOG entry?

Fix what you find inline. Log anything requiring a non-trivial decision in DECISIONS.md.

---

## Post-Write Simplify Loop

After writing or modifying any code — regardless of scope — run this loop before the self-review checklist. This step is not optional and is not a follow-up: it is part of the implementation.

### The loop

1. **Scan for reuse.** Is any logic already implemented in `db.py`, existing pipeline steps, or existing helpers? If yes, use the existing implementation — do not duplicate.
2. **Scan for duplication.** Is any block of code repeated or near-repeated within the new code? Extract it.
3. **Check efficiency.** N+1 queries? Unnecessary LLM calls? Sequential DB writes that could be batched? Fix them.
4. **Check size.** Any function over 30 lines? Any file over 300 lines? If yes, split.
5. **Check necessity.** Is every line necessary for the stated requirement? Delete anything that isn't.

**If any issues were found and fixed: run the loop again from step 1.**

**Stop only when a full pass finds nothing.** Then proceed to the 15-item self-review checklist.

### Why this is a loop, not a one-time pass

Fixing one issue often reveals another. A function extracted in step 2 may reveal a reuse opportunity (step 1). A deletion in step 5 may allow a simplification in step 3. The loop terminates when a complete pass finds nothing new — not after a single pass.

---

## Workflow

1. **Understand** — Read the request. Read relevant existing code. Read SPEC.md, CLAUDE.md (both parts), DECISIONS.md, TODO.md. Ask clarifying questions if requirements are ambiguous. Do not guess.
2. **Plan** — State your approach before writing code. For changes touching >3 files, outline which files change and why. For non-trivial decisions, draft the DECISIONS.md entry *before* writing code.
3. **Implement** — Write the code, the tests, and the documentation together.
4. **Simplify loop** — Run the Post-Write Simplify Loop above. Fix what you find. Re-run. Repeat until the loop produces no findings. This is a blocking step.
5. **Consistency sweep** — Run the Consistency Sweeps checklist. Fix drift in docs, imports, `.env.example`, schema references. Log decisions where needed.
6. **Self-review** — Run the full 15-item review checklist. Fix issues before presenting.
7. **Present** — Show final code with: summary of changes, test results, doc updates, open concerns.

If you realize the approach is wrong, say so immediately. Rework is cheaper than tech debt.

---

## Summary of project files to maintain

| File | Purpose | Update frequency |
|---|---|---|
| `CLAUDE.md` | Project context + engineering standards | When project-level context changes |
| `SPEC.md` | Full product spec | When requirements change |
| `DECISIONS.md` | Why we chose X over Y | Every non-trivial decision |
| `TODO.md` | Known work, prioritized | Every session |
| `CHANGELOG.md` | Human-readable history | Every behavior change |
| `.env.example` | Env var template with descriptions | When env vars change |
| `schema.sql` | Database schema | When schema changes |
| `tests/` | Test suite | Every functional change |

# News Briefing Agent — Product Specification

---

## Overview

A personal AI-powered news digest system that reads your email newsletters daily, deduplicates overlapping coverage, and delivers clean, readable briefings at multiple time budgets. A supervisory agent learns from your feedback over time to improve output quality.

---

## Jobs To Be Done

### Primary
- **Stay informed without redundancy** — I follow many newsletters that cover the same stories. I want one, balanced version of each story, not five rewrites.
- **Read on a known time budget** — I want to sit down knowing exactly how long my news reading will take (10-20 min daily, 30 min for long-form, 30 min catch-up on weekends).
- **Never miss something important** — Even if a story doesn't get a full treatment, I want to know it happened.

### Secondary
- **Get credit when I don't have time** — If I miss a daily brief, I want it rolled into the weekend catch-up automatically. I shouldn't have to manage what I've read.
- **Shape the system to my preferences** — I want to give feedback naturally (just reply to the email) and have the system learn from it over time without me managing config files.
- **Read without distraction** — No images, no tracking pixels, no marketing formatting. Just clean text I can read in any email client.

---

## Digest Types

### 1. Daily Brief
- **Trigger**: When all anchor sources have arrived in inbox (user defines a short list of 2-3 key newsletters, e.g. Axios AM + Morning Brew). Agent polls periodically; once all anchors are present, pipeline runs. Hard cutoff at 10am if anchors haven't arrived.
- **Sources**: All newsletters detected in inbox — no predefined list required. Agent classifies and routes automatically.
- **Time budget**: 10-20 minutes (~2,000–4,000 words)
- **Format**: Grouped by topic, full paragraph for top stories, one-liner for secondary stories
- **Acknowledgment**: User replies to the email in natural language (e.g. "read" or "done, good brief today") — reply triggers acknowledgment and any inline feedback is forwarded to the supervisor

### 2. Deep Read Digest
- **Trigger**: When long-form queue reaches 5+ unread pieces, send immediately. If Thursday evening arrives and threshold hasn't been hit, send whatever is queued (even if sparse) so nothing accumulates into the following week.
- **Sources**: Long-form newsletters and Substacks detected in inbox — agent classifies based on length, format, and content density
- **Time budget**: 30 minutes (~6,000 words)
- **Format**: 3-5 articles summarized in depth, full context and analysis preserved, original article link included
- **Acknowledgment**: User replies in natural language — same mechanism as Daily Brief

### 3. Weekend Catch-Up
- **Trigger**: Sunday morning
- **Sources**: All unacknowledged Daily Briefs from the week
- **Time budget**: 30 minutes, compressed where possible
- **Format**: Same as Daily Brief but draws only from stories not previously acknowledged as read
- **Acknowledgment**: User replies in natural language — same mechanism as Daily Brief

---

## Workflows

### Source Discovery & Classification

```
On each pipeline run:
1. Fetch all unprocessed emails from inbox
2. For each email:
   a. Check List-Unsubscribe header → strong signal it's a newsletter
   b. Check sender patterns, volume, formatting → secondary signals
   c. Classify: personal email (skip), newsletter/news-brief, or long-form
   d. Route: news-brief → Daily Brief pipeline, long-form → Deep Read queue
   e. Upsert into newsletter_sources registry (new sources auto-discovered)
3. Flag any new sources not seen before → note in digest: "New source detected: [name]"
```

### Daily Brief Pipeline

```
1. Cron triggers at configured time
2. Fetch all inbox emails classified as news-brief since last run
3. For each newsletter:
   a. Strip HTML, extract plain text
   b. LLM extracts individual stories: {title, body, key_facts, source}
4. Embed all extracted stories
5. Cluster by cosine similarity (threshold configurable)
6. For ambiguous clusters: LLM confirms merge or split with context
7. For each confirmed cluster:
   a. LLM synthesizes canonical story from all source versions
   b. Preserves richest details, exact figures, key quotes
   c. If story came from exactly one newsletter source: agent searches web for additional context
      - Queries: headline + date, looks for primary sources, official statements, data
      - Incorporates findings into synthesis; marks web-sourced additions inline
      - Multi-source stories are already cross-validated; no search needed
   d. Attaches source list: which newsletters covered it + any web sources used
8. Ranker scores clusters:
   a. Number of sources covering it (proxy for importance)
   b. User topic preferences (learned over time)
   c. Recency
9. Formatter applies time budget:
   a. Top N clusters → full paragraph treatment
   b. Next M clusters → 2-3 sentence treatment
   c. Remainder → one-liner in "Also Covered" section
   d. Target word count: 2,000–4,000 words
10. Deliver plain text email
11. Log: digest ID, story IDs, timestamp, acknowledged=false
12. Archive all source newsletter emails in Gmail (move out of inbox, apply "Briefed" label)
13. If pipeline fails: retry up to 3 times. On third failure, send alert email. Missed newsletters held for next successful run.
```

### Read Acknowledgment

```
User replies to digest email in natural language ("read", "done", "good one today", etc.)
→ Gmail webhook detects reply to known digest thread
→ LLM classifies reply: is this an acknowledgment, feedback, or both?
→ If acknowledgment: log acknowledged=true, timestamp
→ If feedback present: forward to supervisor agent (same as Feedback Loop)
→ Weekend agent excludes acknowledged digest's stories from catch-up
```

### Feedback Loop

```
User replies to any digest email with natural language
→ Gmail webhook / polling detects reply to known digest thread
→ Supervisor agent receives: original digest + user reply
→ Supervisor reasons over feedback:
   - Identifies what specifically the feedback targets (story, topic, format, length, source)
   - Maps to a changeable parameter (prompt instruction, topic weight, word budget, source status)
   - Proposes a specific change
→ If feedback targets a source ("I don't care about [X]", "[X] is irrelevant"):
   - Supervisor marks source as low-relevance in registry
   - Sends reply: "Got it — want me to unsubscribe from [X]?"
   - If user confirms: agent finds List-Unsubscribe link, executes unsubscribe, marks source inactive
   - If user declines: source deprioritized but emails still archived silently
→ Other changes either:
   - Applied automatically (low-risk: topic preference, word budget)
   - Queued for user approval (higher-risk: structural prompt changes)
→ Log feedback event + applied change for future supervisor review
```

### Weekend Catch-Up Pipeline

```
1. Cron triggers Sunday morning
2. Query read log: all stories from Mon-Fri with acknowledged=false
3. Deduplicate across days (same story may have appeared multiple times)
4. Re-rank by importance (not recency — user already missed these)
5. Apply 30-min time budget
6. Deliver plain text email with note: "Catch-up from [date range]"
7. Log as new digest, same acknowledgment flow
```

### Supervisor Agent

The supervisor runs in two modes:

**Immediate mode** — triggered on every user reply to a digest:
```
1. Gmail detects reply to known digest thread
2. LLM classifies: acknowledgment, feedback, or both
3. If feedback present:
   - Interpret feedback, map to specific parameter
   - Apply low-risk changes immediately (topic weights, word budget, source status)
   - Queue high-risk changes (structural prompt changes) for user approval
   - Log feedback event + action taken
4. If unsubscribe confirmed: execute via List-Unsubscribe header
```

**Weekly pattern sweep** — triggers Sunday morning:
```
1. Pull last 7 days of digests, acknowledgment logs, feedback events, applied changes
2. Reason over patterns:
   - Topics consistently skipped → candidate for deprioritization
   - Digests consistently unacknowledged → timing or format hypothesis
   - Feedback themes not yet addressed → propose structural changes
   - Previous changes → did they improve engagement?
3. Produce weekly review email:
   - Summary of changes applied this week
   - Proposed changes needing approval
   - Observations (e.g. "you haven't read Monday briefs in 3 weeks")
4. Apply approved changes
```

---

## User Behaviors & Interactions

| Behavior | What the system does |
|---|---|
| Replies: "read" or "done" or similar | Logged as acknowledged, excluded from weekend catch-up |
| Ignores daily brief (no reply) | Logged as unread, included in weekend catch-up |
| Replies: "the Fed story was too long" | Supervisor identifies story, shortens synthesis prompt for that story type |
| Replies: "missed the Apple earnings story" | Supervisor investigates: was it in a source? Clustering failure? Adjusts accordingly |
| Replies: "I don't care about crypto" | Topic preference weight updated, crypto deprioritized in ranker |
| Replies: "[source] is irrelevant to me" | Supervisor marks source low-relevance, asks if user wants to unsubscribe |
| Confirms unsubscribe | Agent executes List-Unsubscribe, source marked inactive, future emails auto-archived silently |
| Declines unsubscribe | Source deprioritized but emails still archived without appearing in digest |
| Replies: "great digest this week" | Supervisor logs — no changes to what's working |
| Replies: "this brief was too long" | Supervisor investigates length and adjusts word budget |
| Ignores daily briefs 3+ days in a row | Supervisor flags: timing hypothesis, proposes schedule change |
| Does nothing (no feedback, no acknowledgment) | System continues operating; supervisor notes low engagement as a signal |

---

## Data Model

### `digests`
| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| type | enum | daily_brief, deep_read, weekend_catchup |
| sent_at | timestamp | When delivered |
| acknowledged_at | timestamp | When user clicked "mark as read" (null if not) |
| word_count | int | For tracking vs. time budget |
| story_count | int | Total stories included |

### `stories`
| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| digest_id | UUID | FK to digests |
| title | text | Synthesized story title |
| body | text | Synthesized story body |
| treatment | enum | full, brief, one_liner |
| sources | text[] | Newsletter names that covered this story |
| cluster_id | UUID | FK to story_clusters |
| embedding | vector | For deduplication across days |

### `story_clusters`
| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| canonical_title | text | Best title across sources |
| first_seen_at | timestamp | When first appeared in any digest |
| last_seen_at | timestamp | Most recent appearance |

### `feedback_events`
| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| digest_id | UUID | Which digest triggered the reply |
| raw_reply | text | User's reply verbatim |
| supervisor_interpretation | text | What the supervisor understood |
| proposed_change | text | What the supervisor proposed |
| applied | boolean | Whether change was applied |
| applied_at | timestamp | When applied |

### `agent_config`
| Field | Type | Description |
|---|---|---|
| key | text | Config key (e.g. topic_weights, synthesis_prompt) |
| value | jsonb | Current value |
| updated_at | timestamp | Last changed |
| updated_by | text | supervisor or user |
| previous_value | jsonb | For rollback |

### `newsletter_sources`
| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| name | text | Display name |
| sender_email | text | Detected sender address |
| type | enum | news_brief, long_form |
| trust_weight | float | Supervisor-adjustable quality signal |
| status | enum | active, deprioritized, unsubscribed, ignored |
| first_seen_at | timestamp | When agent first detected this source |
| unsubscribe_header | text | Raw List-Unsubscribe header value, for automated unsubscribe |
| unsubscribed_at | timestamp | When agent executed unsubscribe (null if not) |

---

## Tech Stack

### Backend
- **Runtime**: Python
- **Framework**: FastAPI (job endpoints now, web app + multi-user later)
- **LLM**: Anthropic (`claude-opus-4-6` for synthesis/supervisor, `claude-haiku-4-5` for extraction/classification)
- **Embeddings**: Voyage AI `voyage-3` (Anthropic's recommended embeddings partner)
- **Orchestration**: LangChain + LCEL (linear pipeline steps) + LangGraph (supervisor agent, ambiguous cluster resolution)
- **Tracing**: LangSmith
- **Email**: Gmail API (raw) for everything — reading, archiving, reply detection, and sending. No third-party email service.
- **Web search**: Tavily API (for story enrichment)
- **Database**: PostgreSQL + pgvector (for story embeddings)
- **Scheduling**: Railway cron → hits FastAPI job endpoints (e.g. `POST /jobs/daily-brief`)

### Infrastructure
- **Hosting**: Railway (configured at deployment time)
- **Database**: Supabase (PostgreSQL + pgvector)

### Key LangChain Components Used
- `ChatAnthropic` — all LLM calls
- `VoyageAIEmbeddings` — story embeddings
- `ChatPromptTemplate` + `JsonOutputParser` — structured extraction
- `TavilySearchResults` — web search for story enrichment
- `LCEL chains` — extraction → cluster → synthesis pipeline
- `LangGraph` — supervisor agent (immediate + weekly modes), ambiguous cluster resolution loop
- `LangSmith` — pipeline tracing and debugging

---

## Email Format

All digests delivered as plain text email with minimal HTML structure (no images, no tracking pixels, no decorative formatting).

```
DAILY BRIEF — Wednesday, March 25

─────────────────────────────────
ECONOMY
─────────────────────────────────
Fed holds rates steady amid mixed inflation signals. Core PCE came in
at 2.6%, above the 2.4% forecast. Powell emphasized patience, noting
the committee is "in no hurry" to adjust policy. Markets fell 0.8% on
the news, with rate-sensitive sectors hit hardest.

Sources: Morning Brew, WSJ Daily, The Diff

─────────────────────────────────
TECH
─────────────────────────────────
...

─────────────────────────────────
ALSO COVERED
─────────────────────────────────
• OpenAI launches new enterprise tier — pricing TBD (Morning Brew, The Hustle)
• EU fines Meta €200M for data practices (Axios, WSJ Daily)
• Boeing 737 MAX cleared for new routes (Reuters Daily)

─────────────────────────────────
Reply "read" to acknowledge. Any feedback welcome.
─────────────────────────────────
```

---

## Constraints & Design Decisions

- **"Don't miss anything" vs. 10-20 min**: resolved via tiered treatment. Every story appears — top stories in full, secondary in brief, remainder as one-liners in "Also Covered."
- **Source discovery**: no predefined source list. Agent detects newsletters dynamically via `List-Unsubscribe` headers and sender patterns. New sources are noted in the digest on first appearance.
- **Unsubscribe**: agent uses the `List-Unsubscribe` header (present in virtually all legitimate newsletters by law) to execute unsubscribes without needing to scrape or navigate websites. Unsubscribe is always confirmed by user before execution.
- **Feedback interpretation**: supervisor uses LLM to interpret free-text replies. No structured rating UI required. Natural email reply is the only feedback mechanism.
- **Read tracking**: acknowledgment is a natural language reply to the digest email. An LLM classifies whether the reply is an acknowledgment, feedback, or both. Unacknowledged = unread for catch-up purposes.
- **Supervisor cadence**: runs immediately on every reply (individual feedback), plus a weekly pattern sweep Sunday morning. Sunday ordering is not a concern — supervisor is not a once-weekly batch job.
- **Pipeline failure**: auto-retry 3x on failure, alert email on third failure. Missed newsletters held and processed on next successful run.
- **Web search**: triggered only for single-source stories. Multi-source stories are already cross-validated. Bounded to control cost.
- **Anchor sources**: Axios AM and Morning Brew (both reliably arrive by 7am). Pipeline triggers when both are present. Hard cutoff at 10am regardless.
- **Known daily brief sources**: Axios AI+, Axios AM, Morning Brew, Axios Pro Rata, Axios Markets, Axios Vitals, Rundown AI, TLDR AI. These seed the `newsletter_sources` registry on first run; agent continues to discover additional sources dynamically.
- **Email archiving**: source newsletter emails are archived in Gmail (moved out of inbox, labeled "Briefed") immediately after the digest is delivered. This keeps the news inbox clean without deleting originals.
- **Supervisor changes**: low-risk config changes (topic weights, word budget) applied automatically. Structural prompt changes queued for user review.
- **No UI**: entire system operates through email. No web dashboard required for v1.

---

## Out of Scope (v1)

- Mobile app or web dashboard
- Social media monitoring (Twitter/X, Reddit)
- Podcast or video content summarization
- Multi-user support
- Fine-tuning models on feedback data (prompt-based learning only)
- Real-time alerts (digest is batch, not streaming)

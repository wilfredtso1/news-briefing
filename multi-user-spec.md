# Multi-User Spec — News Briefing Agent

> This document specifies what needs to change to turn the single-tenant News Briefing Agent
> into a multi-user product. It does not cover the core brief pipeline, which is specified in
> SPEC.md. Read SPEC.md first.

---

## Vision

Any person can sign up, connect their Gmail, answer a few setup questions, and start receiving
personalized AI news briefings — without touching a config file, a CLI, or a cron job. The
entire experience runs through email after initial setup.

---

## User Journey

```
Landing page
    ↓
"Sign in with Google" — OAuth consent requests Gmail read/write/send permissions
    ↓
Web setup form (< 1 minute)
  - What email should briefings go to? (defaults to Google account email)
  - Your timezone (auto-detected from browser, editable)
  ↓
Account created — credentials + timezone + delivery email written to DB
    ↓
Agent scans inbox for newsletters (background task, runs immediately)
    ↓
Agent sends onboarding email listing discovered sources grouped by type:
  "Here's what I found in your inbox. Reply to confirm or correct."
  [NEWS BRIEFS]   Morning Brew, Axios AM, Axios Markets, ...
  [LONG-FORM]     Stratechery, The Diff, Lenny's Newsletter, ...
  "Reply to move any source between lists, deprioritize one, or add topics you care about."
    ↓
User replies in natural language
    ↓
process_onboarding_reply() applies trust weights + source type corrections +
  topic interests → seeds agent_config → sets onboarding_complete = true
    ↓
Daily briefs begin the next morning
    ↓
User trains the agent by replying to briefs (same as single-user mode)
```

### Why this split

The web form handles the two things that can't be expressed naturally in email: timezone
(needed to schedule correctly before any email is sent) and delivery address (needed to send
the onboarding email itself). Everything else — topic interests, source corrections, anchor
preferences — is expressed as a reply to the onboarding email, which is the right medium
because the agent can show the user what it actually found in their inbox and let them react
to a concrete list rather than filling out a form in the abstract.

---

## Auth Design

### Google OAuth with Gmail Scopes

Standard OAuth 2.0 flow. No custom email-sharing UI needed — Google handles the consent screen.

**Required Gmail API scopes:**
- `https://www.googleapis.com/auth/gmail.readonly` — read inbox
- `https://www.googleapis.com/auth/gmail.send` — send briefs
- `https://www.googleapis.com/auth/gmail.modify` — archive source emails, apply labels

**Flow:**
1. User clicks "Sign in with Google" on landing page
2. Google OAuth consent screen lists the three Gmail permissions with clear explanations
3. On approval: exchange code for `access_token` + `refresh_token`
4. Store `refresh_token` encrypted in DB, bound to the user record
5. `GmailService` is instantiated per-user, passing that user's credentials

**Session management:**
- Use Google's `id_token` (from the OAuth response) to establish a session cookie
- Session only needed for the web sign-up flow — once onboarding is complete, all interaction happens via email
- Short session lifetime is fine (1 hour); re-auth only if user returns to the web app

**Credential storage:**
- `refresh_token` encrypted at rest using Supabase's built-in encryption or a KMS key
- Never logged, never exposed via API
- On token revocation (user removes app access from Google account settings): catch `401` on next Gmail API call, mark account suspended, send notification email if possible

---

## Data Model Changes

### New table: `users`

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,          -- Google account email
    display_name    TEXT,
    google_sub      TEXT NOT NULL UNIQUE,          -- stable Google user ID
    refresh_token   TEXT NOT NULL,                 -- encrypted
    delivery_email  TEXT NOT NULL,                 -- where briefs are sent (defaults to email)
    status          TEXT NOT NULL DEFAULT 'active', -- active | suspended | deleted
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    onboarding_complete BOOLEAN NOT NULL DEFAULT false,
    last_brief_at   TIMESTAMPTZ
);
```

### Add `user_id` to all existing tables

Every table gets a `user_id UUID NOT NULL REFERENCES users(id)` column. This is the
single largest migration in the multi-user work.

Tables affected:
- `newsletter_sources`
- `digests`
- `stories`
- `story_clusters`
- `feedback_events`
- `agent_config`
- `onboarding_events`

All existing rows get assigned to the original single-tenant user (a seed user created
during migration from the current schema).

**Index strategy**: add `(user_id, ...)` composite indexes on the most-queried paths:
- `newsletter_sources(user_id, sender_email)` — replaces current unique on `sender_email`
- `agent_config(user_id, key)` — replaces current unique on `key`
- `digests(user_id, sent_at DESC)` — for supervisor weekly sweep queries

### `newsletter_sources` unique constraint change

Currently: `UNIQUE(sender_email)` — one row per sender globally.
After: `UNIQUE(user_id, sender_email)` — per-user registry. Two users can both subscribe to
Morning Brew with independent trust weights, type overrides, and status.

### `agent_config` becomes per-user

Currently: global key-value store (one `word_budget` for everyone).
After: `(user_id, key)` primary key. Each user has their own config. Default values are
seeded from a `default_agent_config` template at account creation.

---

## Pipeline Changes

### GmailService: per-user instantiation

Currently: one `GmailService` instance at module level, reading credentials from `.env`.

After: `GmailService(user: User)` — instantiated per-run with that user's stored credentials.
The constructor decrypts the refresh token and builds the OAuth2 credentials object.

```python
# Before
gmail = GmailService()  # reads env vars

# After
gmail = GmailService(user=user)  # user.refresh_token from DB
```

### All pipeline functions gain `user_id` parameter

Every function that touches the DB or Gmail needs to know which user it's running for.
The `user_id` is threaded from the top-level runner down:

```
run_daily_brief(user_id)
    → fetch_emails(gmail, user_id)
    → classify_sources(emails, user_id)
    → extract_stories(emails, user_id)
    → embed_and_cluster(stories, user_id)
    → synthesize(clusters, user_id)
    → enrich(stories, user_id)
    → gap_fill_topics(stories, user_id)   # reads user's web_search_topics config
    → rank(stories, user_id)              # reads user's topic_weights config
    → format_digest(stories, user_id)    # reads user's word_budget config
    → send(digest, gmail, user_id)
    → persist(digest, user_id)
```

### Agent config reads become per-user

`get_config(key)` → `get_config(key, user_id)`. Every call to agent_config in the pipeline
passes `user_id`. This ensures each user's style notes, word budget, and topic weights are
isolated.

### Supervisor: per-user context

The supervisor already receives `digest_id` and `run_id`. The `digest_id` is enough to
look up which user owns it — no additional param needed. All DB writes in supervisor nodes
scope naturally to the owning user.

---

## Scheduling: From Global Cron to Per-User Scheduler

### Current model (single user)
Five Railway cron services hit fixed endpoints on a fixed schedule. Works fine for one user.

### Multi-user model

**Option A: Fan-out endpoint (recommended for <1,000 users)**

Keep the same Railway cron services but change each endpoint to iterate over all active users:

```
POST /jobs/daily-brief
    → query users WHERE status = 'active' AND onboarding_complete = true
    → for each user:
        → check if anchor emails have arrived for this user
        → if yes (or past cutoff): enqueue run_daily_brief(user_id) as background task
```

FastAPI background tasks run concurrently. Each user's pipeline is independent.
Pipeline failure for one user is isolated and doesn't affect others.

**Option B: Per-user cron (for scale or timezone support)**

Create one set of cron services per user — impractical beyond a few dozen users.
Not recommended.

**Option C: Queue-based (for >1,000 users)**

Add a task queue (Celery + Redis, or Railway's built-in queuing). Cron endpoint enqueues
tasks, workers consume them. Adds infrastructure complexity not needed early.

**Recommendation**: start with Option A. It handles hundreds of users without added infrastructure.
Move to Option C when per-user pipeline latency becomes a problem.

### Timezone support

Each user should get their brief at the right local time, not UTC-based.
Add `timezone` field to `users` table (e.g. `"America/New_York"`).
The fan-out endpoint filters: only run for users whose local time is within the brief window.

---

## Web App

The minimum viable web surface. The goal is to get users connected and onboarded — not to
build a dashboard.

### Pages

**`/` — Landing page**
- What the product does (3 sentences)
- "Sign in with Google" button
- No pricing page needed for early access

**`/auth/google` — OAuth redirect**
- Initiates Google OAuth flow
- On callback: create or update user record, store refresh token
- Redirect to `/setup` for new users, `/` for returning users

**`/setup` — Setup form (new users only)**
- Delivery email (pre-filled from Google account, editable). Label: "Where should your brief be delivered?"
- Timezone (auto-detected from browser, editable). Label: "Your timezone — used to schedule your morning brief."
- Submit → creates user record → triggers `/jobs/onboard` for this user as a background task → redirect to `/confirm`

**`/confirm` — Post-setup confirmation (new users, shown immediately after /setup)**
- Heading: "We're scanning your inbox."
- Body: "You'll receive a setup email in the next few minutes listing the newsletters we found.
  Reply to that email to confirm your sources and tell us what topics you care about.
  Your first brief will arrive the morning after you reply."
- No buttons or next steps — just wait for the email.

**`/` (logged in) — Account page**
- Status: "Your brief runs daily at ~7-8am ET"
- Last brief sent: [date]
- Link to pause / delete account
- That's it — config happens through email replies, not a dashboard

**`/unsubscribe?token=...` — One-click unsubscribe from the service**
- Signed token in unsubscribe link included in every brief footer
- Clicking → marks user `status = 'deleted'`, stops all pipeline runs for that user
- No login required

### What the web app does NOT include
- Settings dashboard (config happens via email reply)
- Digest history viewer
- Source management UI
- Any analytics or charts

---

## Email Changes

### Footer

Every digest gets a footer with:
```
─────────────────────────────────
Reply "read" to acknowledge. Any feedback welcome.
Manage your account: https://[app-url]/account
Unsubscribe from this service: https://[app-url]/unsubscribe?token=[signed-token]
─────────────────────────────────
```

The "unsubscribe from this service" link is unsubscribing from the briefing agent itself
(not from individual newsletters, which is a separate in-product flow via supervisor).

### Sender address

For single-user: briefs sent from the user's own Gmail account.
For multi-user: two options:
1. **Send from user's own Gmail** — preserves the "email to yourself" feel; requires their OAuth scope. This is already how it works.
2. **Send from a service address** (`briefs@[yourdomain].com`) — cleaner for a product, but requires a separate Gmail/SendGrid account and loses the personal feel.

**Recommendation**: keep sending from the user's own Gmail. It's already implemented, it keeps briefs in the same thread as their other email, and it makes reply detection trivial (replies land in the same inbox the agent is monitoring).

---

## Credential Security

- `refresh_token` encrypted at rest using AES-256. Key stored in Railway env vars, not in DB.
- Token never appears in logs, error messages, or API responses.
- On `401` from Gmail API: mark user suspended, stop pipeline, attempt to notify via any available channel.
- User can revoke access at any time from Google account settings (`myaccount.google.com/permissions`). The agent detects this on the next pipeline run.
- No other user's data is accessible — all DB queries are scoped to `user_id` from the session or the digest's owning user.

---

## Migration Path from Single-User

1. Create `users` table; insert one row for the existing user (wilfred)
2. Add `user_id` column (nullable) to all tables; backfill to wilfred's user ID; add NOT NULL constraint
3. Update unique indexes to include `user_id`
4. Update all pipeline functions to accept and pass `user_id`
5. Update `get_config` / `set_config` to scope to `user_id`
6. Update `GmailService` to accept per-user credentials
7. Build web app (landing + OAuth + setup + account pages)
8. Update cron endpoints to fan-out over active users
9. Add `timezone` to `users` and filter fan-out by local time window

Steps 1–6 can be done with zero user-facing changes (wilfred's existing setup continues
working throughout). Steps 7–9 are what enable new users to join.

---

## Open Questions

1. **Pricing model**: free? waitlist? paid? This affects whether the sign-up flow needs payment,
   rate limiting, or invite codes.

2. **Gmail send-as**: should briefs come from the user's own Gmail address or a central
   `briefs@[domain].com`? Tradeoffs above. Needs a decision before building the web app.

3. **Google OAuth app verification**: Google requires app review to grant sensitive Gmail scopes
   to external users at scale. During development and for up to 100 test users, unverified apps
   work fine. Production launch requires submitting for Google's verification process
   (typically 1-4 weeks, requires a privacy policy and demo of how scopes are used).

4. **Per-user anchor sources**: currently hardcoded to Axios AM + Morning Brew. In multi-user,
   different users subscribe to different newsletters. The onboarding form should let users
   specify which 2-3 newsletters are their "anchors" — the ones to wait for before sending.
   Could also be auto-detected (most consistent senders in the inbox).

5. **Shared newsletter source knowledge**: `newsletter_sources` is currently per-user.
   Could have a global `known_senders` table that pre-classifies common newsletters
   (Morning Brew = news_brief, Stratechery = long_form, etc.) so new users don't need to
   wait for the heuristic to learn their sources. Separate from per-user overrides.

---

## Out of Scope for Multi-User v1

- Team accounts (shared brief for a team)
- Source marketplace (subscribe to curated source lists)
- Custom domains for brief delivery
- API access for third-party integrations
- White-labeling
- Analytics dashboard
- Social/referral features

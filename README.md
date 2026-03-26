# News Briefing Agent

A personal AI news digest system. Reads all newsletters from a Gmail inbox daily, deduplicates overlapping coverage across sources, synthesizes canonical stories with source attribution, and delivers clean plain-text email digests. A supervisor agent learns from natural-language email replies and improves output over time.

## What It Does

- **Daily Brief** — synthesizes 15–30 newsletters into a 10–15 minute read, grouped by topic (AI, markets, health, VC, etc.)
- **Deep Read** — queues long-form newsletters (Stratechery, etc.) for a separate 30-minute digest
- **Weekend Catch-Up** — Sunday digest of anything you missed or didn't acknowledge during the week
- **Supervisor Agent** — reply to any digest in plain English to adjust preferences, deprioritize sources, or request unsubscribes

## Tech Stack

| Layer | Tool |
|---|---|
| LLM | Anthropic claude-opus-4-6 (synthesis, supervisor), claude-haiku-4-5 (extraction) |
| Embeddings | Voyage AI voyage-3 |
| Orchestration | LangChain + LCEL, LangGraph |
| Tracing | LangSmith |
| Email | Gmail API (read, archive, send) |
| Web search | Tavily API |
| Database | Supabase (PostgreSQL + pgvector) |
| Hosting | Railway |

## Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/wilfredtso1/news-briefing.git
cd news-briefing-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

Required keys:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `VOYAGE_API_KEY` | [dash.voyageai.com](https://dash.voyageai.com) |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) |
| `LANGCHAIN_API_KEY` | [smith.langchain.com](https://smith.langchain.com) |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` | Google Cloud Console (Gmail API, OAuth 2.0) |
| `DATABASE_URL` | Supabase project → Settings → Database → Session pooler URL |
| `GMAIL_SEND_AS` | Your Gmail address (e.g. `you@gmail.com`) |

### 3. Set up the database

Run the schema against your Supabase project (requires pgvector extension enabled first):

```bash
psql "$DATABASE_URL" -f schema.sql
```

### 4. Verify the setup

```bash
# Check app starts cleanly
uvicorn main:app --reload

# Check Gmail OAuth connects
python -c "from gmail_service import GmailService; GmailService(); print('Gmail OK')"

# Run the test suite
pytest tests/ -v
```

## Running Locally

```bash
# Start the API server
uvicorn main:app --reload

# Trigger a pipeline run manually (dry run — no email sent, no DB writes)
curl -X POST http://localhost:8000/jobs/daily-brief

# Health check
curl http://localhost:8000/health
```

## Project Structure

```
news-briefing-agent/
├── main.py                 # FastAPI app — job endpoints triggered by Railway cron
├── gmail_service.py        # Gmail API wrapper (read, archive, send, thread detection)
├── source_classifier.py    # Newsletter detection and routing
├── config.py               # Env var validation (crashes at startup if anything missing)
├── schema.sql              # Full DB schema with pgvector HNSW index
├── pipeline/
│   ├── daily_brief.py      # Main orchestrator — runs the full daily brief pipeline
│   ├── extractor.py        # LLM story extraction from newsletter HTML/text
│   ├── embedder.py         # Voyage AI embeddings + cosine similarity clustering
│   ├── disambiguator.py    # LangGraph — resolves ambiguous cluster merges
│   ├── synthesizer.py      # LLM synthesis — multi-source → canonical story
│   ├── enricher.py         # Tavily web search for single-source stories
│   ├── ranker.py           # Story ranking by topic weight + source count
│   ├── formatter.py        # Plain-text digest formatting with word budget
│   ├── weekend_catchup.py  # (Phase 4) Sunday catch-up from unacknowledged stories
│   └── deep_read.py        # (Phase 4) Long-form queue pipeline
├── supervisor/
│   ├── immediate.py        # (Phase 3) LangGraph reply-triggered supervisor
│   └── weekly.py           # (Phase 5) Weekly pattern sweep supervisor
├── tools/
│   ├── db.py               # All database helpers
│   ├── tracing.py          # (Phase 5) LangSmith tracing decorator
│   ├── retry.py            # (Phase 5) Retry wrapper with error discrimination
│   └── alerts.py           # (Phase 5) Alert email on pipeline failure
└── tests/                  # Unit + integration tests (124 passing)
```

## Deployment (Railway)

1. Push to GitHub
2. Connect repo to Railway
3. Set all environment variables in Railway dashboard
4. Configure cron jobs to hit the job endpoints:

| Cron | Endpoint | Schedule |
|---|---|---|
| Daily brief poll | `POST /jobs/daily-brief` | Every 15 min, 6–10am |
| Reply poll | `POST /jobs/poll-replies` | Every 15 min |
| Weekend catch-up | `POST /jobs/weekend-catchup` | Sunday 8am |
| Weekly supervisor | `POST /jobs/supervisor-weekly` | Sunday 7am |

## Documentation

- `CLAUDE.md` — full project context and engineering standards
- `SPEC.md` — product specification
- `AGENTS.md` — concurrent agent build plan for Phases 3–5
- `DECISIONS.md` — architectural decision log
- `CHANGELOG.md` — change history
- `TODO.md` — prioritized work tracker

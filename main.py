"""
FastAPI application.

Exposes job endpoints triggered by Railway cron.
Each endpoint runs one pipeline job and returns immediately.

Job endpoints (POST):
  /jobs/daily-brief        — run daily brief pipeline (checks anchors first)
  /jobs/poll-replies       — poll digest threads for user replies
  /jobs/deep-read          — run deep read pipeline if queue threshold met
  /jobs/weekend-catchup    — run weekend catch-up pipeline
  /jobs/supervisor-weekly  — run weekly supervisor pattern sweep

Utility:
  GET /health              — health check (used by Railway)
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Config is validated at import time — crashes immediately if env vars are missing
from config import settings  # noqa: F401

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app_startup", project=settings.langchain_project)
    yield
    log.info("app_shutdown")


app = FastAPI(
    title="News Briefing Agent",
    description="Personal AI news digest system",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Railway uses this to determine if the deployment is healthy."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Job endpoints
# All jobs run in the background so the HTTP response returns immediately.
# Railway cron does not wait for job completion.
# ---------------------------------------------------------------------------

@app.post("/jobs/daily-brief")
async def job_daily_brief(background_tasks: BackgroundTasks):
    """
    Trigger the daily brief pipeline.
    Checks whether anchor sources have arrived before running.
    Railway cron should call this every 15 minutes from 6am to 10am.
    """
    run_id = str(uuid.uuid4())
    log.info("job_triggered", job="daily_brief", run_id=run_id)
    background_tasks.add_task(_run_daily_brief, run_id)
    return {"job": "daily_brief", "run_id": run_id, "status": "queued"}


@app.post("/jobs/poll-replies")
async def job_poll_replies(background_tasks: BackgroundTasks):
    """
    Poll recent digest threads for user replies.
    Railway cron should call this every 15 minutes.
    """
    run_id = str(uuid.uuid4())
    log.info("job_triggered", job="poll_replies", run_id=run_id)
    background_tasks.add_task(_run_poll_replies, run_id)
    return {"job": "poll_replies", "run_id": run_id, "status": "queued"}


@app.post("/jobs/deep-read")
async def job_deep_read(background_tasks: BackgroundTasks):
    """
    Trigger deep read pipeline if queue threshold is met.
    Railway cron should call this daily (Thursday evening as fallback).
    """
    run_id = str(uuid.uuid4())
    log.info("job_triggered", job="deep_read", run_id=run_id)
    background_tasks.add_task(_run_deep_read, run_id)
    return {"job": "deep_read", "run_id": run_id, "status": "queued"}


@app.post("/jobs/weekend-catchup")
async def job_weekend_catchup(background_tasks: BackgroundTasks):
    """
    Trigger weekend catch-up pipeline.
    Railway cron should call this Sunday morning.
    """
    run_id = str(uuid.uuid4())
    log.info("job_triggered", job="weekend_catchup", run_id=run_id)
    background_tasks.add_task(_run_weekend_catchup, run_id)
    return {"job": "weekend_catchup", "run_id": run_id, "status": "queued"}


@app.post("/jobs/supervisor-weekly")
async def job_supervisor_weekly(background_tasks: BackgroundTasks):
    """
    Trigger the supervisor's weekly pattern sweep.
    Railway cron should call this Sunday morning (before weekend catch-up).
    """
    run_id = str(uuid.uuid4())
    log.info("job_triggered", job="supervisor_weekly", run_id=run_id)
    background_tasks.add_task(_run_supervisor_weekly, run_id)
    return {"job": "supervisor_weekly", "run_id": run_id, "status": "queued"}


# ---------------------------------------------------------------------------
# Background task implementations
# Stubs for Phase 1 — pipeline logic is added in Phase 2+
# ---------------------------------------------------------------------------

def _run_daily_brief(run_id: str) -> None:
    """
    Run the daily brief pipeline. Checks anchor sources before running.
    """
    from gmail_service import GmailService
    from pipeline import daily_brief

    log.info("daily_brief_start", run_id=run_id)
    try:
        gmail = GmailService()
        anchors_ready = gmail.check_anchor_sources_present(settings.anchor_sources)
        if not anchors_ready:
            log.info("daily_brief_skipped_anchors_not_ready", run_id=run_id, anchors=settings.anchor_sources)
            return
        log.info("daily_brief_anchors_ready", run_id=run_id)
        daily_brief.run(run_id=run_id)
    except Exception as e:
        log.error("daily_brief_failed", run_id=run_id, error=str(e))
        raise


def _run_poll_replies(run_id: str) -> None:
    """Phase 1 stub. Reply detection and supervisor wired in Phase 3."""
    log.info("poll_replies_start", run_id=run_id)
    # TODO(phase3): query recent digests, check threads for replies, invoke supervisor


def _run_deep_read(run_id: str) -> None:
    """Run the deep read pipeline if the long-form queue meets the configured threshold."""
    from pipeline.deep_read import run_deep_read

    log.info("deep_read_start", run_id=run_id)
    try:
        result = run_deep_read(run_id=run_id)
        log.info("deep_read_finished", run_id=run_id, status=result.get("status"))
    except Exception as e:
        log.error("deep_read_failed", run_id=run_id, error=str(e))
        raise


def _run_weekend_catchup(run_id: str) -> None:
    """Run the weekend catch-up pipeline drawing from unacknowledged Mon–Fri stories."""
    from pipeline.weekend_catchup import run_weekend_catchup

    log.info("weekend_catchup_start", run_id=run_id)
    try:
        result = run_weekend_catchup(run_id=run_id)
        log.info("weekend_catchup_finished", run_id=run_id, status=result.get("status"))
    except Exception as e:
        log.error("weekend_catchup_failed", run_id=run_id, error=str(e))
        raise


def _run_supervisor_weekly(run_id: str) -> None:
    """Phase 1 stub. Weekly supervisor sweep wired in Phase 5."""
    log.info("supervisor_weekly_start", run_id=run_id)
    # TODO(phase5): pull last 7 days of feedback/engagement, reason over patterns

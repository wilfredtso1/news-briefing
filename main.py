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

import hmac
import hashlib
import base64
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeSerializer
from pydantic import BaseModel

# Config is validated at import time — crashes immediately if env vars are missing
from config import settings  # noqa: F401
from tools.alerts import send_alert

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _get_signer() -> URLSafeSerializer:
    if not settings.session_secret_key:
        raise HTTPException(status_code=503, detail="SESSION_SECRET_KEY not configured")
    return URLSafeSerializer(settings.session_secret_key)


def _sign_session(user_id: str) -> str:
    return _get_signer().dumps(str(user_id))


def _require_session(request: Request) -> dict:
    """Return the user dict for the session cookie, or raise 401."""
    from tools.db import get_user_by_id
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401)
    try:
        user_id = _get_signer().loads(token)
    except Exception:
        raise HTTPException(status_code=401)
    user = get_user_by_id(user_id)
    if not user or user["status"] == "deleted":
        raise HTTPException(status_code=401)
    return user


def _make_unsubscribe_token(user_id: str) -> str:
    """Return a URL-safe signed token embedding the user_id."""
    if not settings.unsubscribe_secret_key:
        raise RuntimeError("UNSUBSCRIBE_SECRET_KEY not configured")
    sig = hmac.new(
        settings.unsubscribe_secret_key.encode(),
        user_id.encode(),
        hashlib.sha256,
    ).digest()
    payload = f"{user_id}:{base64.b64encode(sig).decode()}"
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _verify_unsubscribe_token(token: str) -> str:
    """Decode and verify an unsubscribe token. Returns user_id or raises 400."""
    if not settings.unsubscribe_secret_key:
        raise HTTPException(status_code=503, detail="UNSUBSCRIBE_SECRET_KEY not configured")
    try:
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, sig_b64 = payload.rsplit(":", 1)
        sig = base64.b64decode(sig_b64.encode())
        expected = hmac.new(
            settings.unsubscribe_secret_key.encode(),
            user_id.encode(),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("invalid signature")
        return user_id
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired unsubscribe token")


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
# Pydantic request models
# ---------------------------------------------------------------------------

class SetupRequest(BaseModel):
    delivery_email: str
    timezone: str


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Railway uses this to determine if the deployment is healthy."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Auth + API endpoints (web app)
# ---------------------------------------------------------------------------

@app.get("/auth/google")
async def auth_google():
    """Redirect browser to Google OAuth consent screen requesting Gmail scopes."""
    if not settings.google_oauth_client_id or not settings.google_oauth_redirect_uri:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join([
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
        ]),
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@app.get("/auth/google/callback")
async def auth_google_callback(code: str, response: Response):
    """Exchange OAuth code for tokens, upsert user, set session cookie, redirect."""
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
    from tools.db import upsert_user

    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        })
    tokens = token_resp.json()
    if "error" in tokens:
        log.error("oauth_token_exchange_failed", error=tokens.get("error"))
        raise HTTPException(status_code=400, detail="OAuth token exchange failed")

    try:
        claims = google_id_token.verify_oauth2_token(
            tokens["id_token"],
            google_requests.Request(),
            settings.google_oauth_client_id,
        )
    except Exception as e:
        log.error("oauth_id_token_verification_failed", error=str(e))
        raise HTTPException(status_code=400, detail="Failed to verify Google identity")

    user = upsert_user(
        google_sub=claims["sub"],
        email=claims["email"],
        display_name=claims.get("name"),
        refresh_token=tokens.get("refresh_token", ""),
    )

    session_token = _sign_session(str(user["id"]))
    redirect_url = "/account" if user.get("onboarding_complete") else "/setup"
    redirect_response = RedirectResponse(redirect_url)
    redirect_response.set_cookie(
        "session", session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    log.info("user_authenticated", user_id=str(user["id"]), email=user["email"])
    return redirect_response


@app.get("/api/me")
async def get_me(request: Request):
    """Return current user data. 401 if no valid session cookie."""
    user = _require_session(request)
    display_name = user.get("display_name") or ""
    first_name = display_name.split()[0] if display_name else user["email"]
    last_brief_at = user.get("last_brief_at")
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "delivery_email": user.get("delivery_email") or user["email"],
        "display_name": display_name,
        "first_name": first_name,
        "timezone": user.get("timezone", "America/New_York"),
        "status": user["status"],
        "onboarding_complete": user.get("onboarding_complete", False),
        "last_brief_at": last_brief_at.isoformat() if last_brief_at else None,
    }


@app.post("/api/setup")
async def api_setup(request: Request, background_tasks: BackgroundTasks, body: SetupRequest):
    """Save delivery email + timezone, then trigger onboarding in background."""
    from tools.db import update_user_setup
    user = _require_session(request)
    update_user_setup(str(user["id"]), delivery_email=body.delivery_email, timezone=body.timezone)
    run_id = str(uuid.uuid4())
    background_tasks.add_task(_run_onboard, run_id, user_id=str(user["id"]))
    return {"ok": True}


@app.post("/api/pause")
async def api_pause(request: Request):
    """Pause briefings for the current user."""
    from tools.db import set_user_status
    user = _require_session(request)
    set_user_status(str(user["id"]), "paused")
    return {"ok": True}


@app.delete("/api/account")
async def api_delete_account(request: Request):
    """Revoke Gmail token, mark user deleted, clear session cookie."""
    from tools.db import set_user_status
    user = _require_session(request)
    refresh_token = user.get("refresh_token", "")
    if refresh_token:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": refresh_token},
                )
        except Exception as e:
            log.warning("oauth_revoke_failed", user_id=str(user["id"]), error=str(e))
    set_user_status(str(user["id"]), "deleted")
    json_response = JSONResponse({"ok": True})
    json_response.delete_cookie("session")
    return json_response


@app.get("/api/unsubscribe")
async def one_click_unsubscribe(token: str):
    """
    Validate signed unsubscribe token from brief footer link.
    Marks user deleted, then redirects to the /unsubscribe SPA page.
    Email footer links should point to /api/unsubscribe?token=...
    """
    from tools.db import set_user_status
    user_id = _verify_unsubscribe_token(token)
    set_user_status(user_id, "deleted")
    return RedirectResponse("/unsubscribe")


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


@app.post("/jobs/onboard")
async def job_onboard(background_tasks: BackgroundTasks):
    """
    Trigger the onboarding flow.
    Scans inbox for newsletters and sends a setup email asking the user to
    identify their most important sources. Idempotent — no-ops if onboarding
    is already complete or a setup email is already pending a reply.
    """
    run_id = str(uuid.uuid4())
    log.info("job_triggered", job="onboard", run_id=run_id)
    background_tasks.add_task(_run_onboard, run_id)
    return {"job": "onboard", "run_id": run_id, "status": "queued"}


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
    Skips if onboarding has not been completed — the user's preferences
    are needed before the pipeline runs for the first time.
    """
    from gmail_service import GmailService
    from pipeline import daily_brief
    from tools.db import get_config

    log.info("daily_brief_start", run_id=run_id)
    try:
        if not get_config("onboarding_complete"):
            log.info("daily_brief_skipped_onboarding_incomplete", run_id=run_id)
            return

        gmail = GmailService()
        anchors_ready = gmail.check_anchor_sources_present(settings.anchor_sources)
        if not anchors_ready:
            log.info("daily_brief_skipped_anchors_not_ready", run_id=run_id, anchors=settings.anchor_sources)
            return
        log.info("daily_brief_anchors_ready", run_id=run_id)
        daily_brief.run(run_id=run_id)
    except Exception as e:
        log.error("daily_brief_failed", run_id=run_id, error=str(e))
        send_alert("daily_brief", e, run_id)
        raise


def _run_poll_replies(run_id: str) -> None:
    """
    Poll Gmail for replies to recent digest threads and run the immediate supervisor.

    Fetches all sent, unacknowledged digests from the last 7 days.
    For each digest with a known Gmail thread ID, checks for new replies.
    Each reply is processed by the immediate supervisor graph, which classifies
    the reply, applies low-risk config changes, and queues high-risk ones.
    Marks digests as acknowledged when the reply type is 'acknowledge' or 'both'
    (the supervisor graph handles the DB write via mark_digest_acknowledged).

    Non-fatal errors (single reply processing failure) are logged and skipped.
    If the Gmail service fails to initialise, the entire job fails loudly.
    """
    from gmail_service import GmailService
    from supervisor.immediate import run_immediate_supervisor
    from tools.db import get_unacknowledged_digests

    log.info("poll_replies_start", run_id=run_id)
    gmail = GmailService()

    # Fetch recent unacknowledged digests — they are the only ones that can receive replies
    digests = get_unacknowledged_digests(digest_type="daily_brief", days_back=7)
    log.info("poll_replies_digests_fetched", run_id=run_id, digest_count=len(digests))

    processed_replies = 0
    for digest in digests:
        digest_id = str(digest["id"])
        # thread_id is stored on the digest row (populated by the daily brief pipeline at send time)
        # If the thread_id column is absent or null, skip — we cannot poll without it
        thread_id = digest.get("thread_id")
        sent_message_id = digest.get("sent_message_id")

        if not thread_id or not sent_message_id:
            log.debug(
                "poll_replies_digest_skipped_no_thread",
                run_id=run_id,
                digest_id=digest_id,
            )
            continue

        try:
            replies = gmail.get_thread_replies(
                thread_id=thread_id,
                after_message_id=sent_message_id,
            )
        except Exception as e:
            log.warning(
                "poll_replies_thread_fetch_failed",
                run_id=run_id,
                digest_id=digest_id,
                thread_id=thread_id,
                error=str(e),
            )
            continue

        for reply in replies:
            try:
                result = run_immediate_supervisor(
                    digest_id=digest_id,
                    raw_reply=reply.body_text,
                    thread_id=thread_id,
                )
                log.info(
                    "poll_replies_supervisor_complete",
                    run_id=run_id,
                    digest_id=digest_id,
                    reply_type=result.reply_type,
                    action_taken=result.action_taken,
                )
                processed_replies += 1
            except Exception as e:
                log.warning(
                    "poll_replies_supervisor_failed",
                    run_id=run_id,
                    digest_id=digest_id,
                    error=str(e),
                )

    log.info(
        "poll_replies_complete",
        run_id=run_id,
        digests_checked=len(digests),
        replies_processed=processed_replies,
    )

    # Check for a reply to the onboarding setup email (runs before full pipeline access)
    _check_onboarding_reply(run_id, gmail)

    # Failsafe: detect self-addressed command emails the user sent to themselves
    _check_inbox_commands(run_id, gmail)


def _check_onboarding_reply(run_id: str, gmail) -> None:
    """
    Poll for a user reply to the onboarding setup email.

    Looks up the most recent pending onboarding event (applied=False with a
    thread_id). If a reply exists, passes it to process_onboarding_reply which
    applies preferences and marks onboarding complete.

    Non-fatal: failures are logged and skipped. The next poll cycle will retry.
    """
    from pipeline.onboarding import process_onboarding_reply
    from tools.db import get_pending_onboarding_event

    pending = get_pending_onboarding_event()
    if not pending:
        return

    thread_id = pending.get("thread_id")
    sent_message_id = pending.get("sent_message_id")
    if not thread_id or not sent_message_id:
        log.debug("onboarding_reply_check_no_thread", run_id=run_id, event_id=str(pending["id"]))
        return

    try:
        replies = gmail.get_thread_replies(thread_id=thread_id, after_message_id=sent_message_id)
    except Exception as e:
        log.warning("onboarding_reply_fetch_failed", run_id=run_id, error=str(e))
        return

    if not replies:
        return

    # Process only the first reply — onboarding is a one-shot flow
    reply = replies[0]
    try:
        result = process_onboarding_reply(
            event_id=str(pending["id"]),
            raw_reply=reply.body_text,
            run_id=run_id,
        )
        log.info(
            "onboarding_reply_processed",
            run_id=run_id,
            applied_count=len(result.get("applied_changes", [])),
            notes=result.get("notes", ""),
        )
    except Exception as e:
        log.error("onboarding_reply_process_failed", run_id=run_id, error=str(e))
        send_alert("onboarding_reply", e, run_id)


def _check_inbox_commands(run_id: str, gmail) -> None:
    """
    Scan inbox for self-addressed command emails and trigger the requested pipeline.

    Failsafe path for on-demand triggers when no digest exists to reply to
    (e.g. the pipeline has never run, or the user wants to trigger from scratch).
    The user sends an email from/to their own address (settings.gmail_send_as)
    with a subject or body like "send brief" or "deep read".

    After processing any command (successfully or not), the email is archived
    to prevent the next polling cycle from re-triggering the pipeline.
    Non-fatal: individual failures are logged and skipped.
    """
    from supervisor.immediate import classify_command

    query = f"from:{settings.gmail_send_as} to:{settings.gmail_send_as} in:inbox"
    try:
        command_messages = gmail.list_messages_with_query(query, max_results=10)
    except Exception as e:
        log.warning("inbox_command_scan_failed", run_id=run_id, error=str(e))
        return

    if not command_messages:
        return

    log.info("inbox_commands_found", run_id=run_id, count=len(command_messages))

    for msg in command_messages:
        # Use subject + body so short subjects like "send brief" are classified correctly
        text = f"{msg.subject}\n{msg.body_text}".strip()
        try:
            command_target = classify_command(text)
        except Exception as e:
            log.warning(
                "inbox_command_classify_failed",
                run_id=run_id,
                message_id=msg.message_id,
                error=str(e),
            )
            gmail.archive_messages([msg.message_id])
            continue

        cmd_run_id = str(uuid.uuid4())
        log.info(
            "inbox_command_executing",
            run_id=run_id,
            command_target=command_target,
            cmd_run_id=cmd_run_id,
        )

        try:
            if command_target == "deep_read":
                from pipeline.deep_read import run_deep_read
                run_deep_read(run_id=cmd_run_id, force=True)
            else:
                from pipeline.daily_brief import run as run_daily_brief
                run_daily_brief(run_id=cmd_run_id)
            log.info(
                "inbox_command_complete",
                run_id=run_id,
                command_target=command_target,
                cmd_run_id=cmd_run_id,
            )
        except Exception as e:
            log.error(
                "inbox_command_pipeline_failed",
                run_id=run_id,
                command_target=command_target,
                cmd_run_id=cmd_run_id,
                error=str(e),
            )
            send_alert(f"inbox_command_{command_target}", e, cmd_run_id)
        finally:
            # Always archive — prevents re-triggering even if the pipeline failed
            gmail.archive_messages([msg.message_id])


def _run_onboard(run_id: str, user_id: Optional[str] = None) -> None:
    """
    Run the onboarding flow. Idempotent — no-ops if already complete.
    Scans inbox for newsletters and sends a setup email to the user.
    user_id is passed when triggered from the web /api/setup endpoint.
    """
    from pipeline.onboarding import run_onboarding

    log.info("onboard_start", run_id=run_id, user_id=user_id)
    try:
        result = run_onboarding(run_id=run_id)
        log.info("onboard_finished", run_id=run_id, status=result.get("status"))
    except Exception as e:
        log.error("onboard_failed", run_id=run_id, error=str(e))
        send_alert("onboarding", e, run_id)
        raise


def _run_deep_read(run_id: str) -> None:
    """Run the deep read pipeline if the long-form queue meets the configured threshold."""
    from pipeline.deep_read import run_deep_read

    log.info("deep_read_start", run_id=run_id)
    try:
        result = run_deep_read(run_id=run_id)
        log.info("deep_read_finished", run_id=run_id, status=result.get("status"))
    except Exception as e:
        log.error("deep_read_failed", run_id=run_id, error=str(e))
        send_alert("deep_read", e, run_id)
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
        send_alert("weekend_catchup", e, run_id)
        raise


def _run_supervisor_weekly(run_id: str) -> None:
    """Run the weekly supervisor pattern sweep and send a review email."""
    from supervisor.weekly import run_weekly_supervisor

    log.info("supervisor_weekly_start", run_id=run_id)
    try:
        result = run_weekly_supervisor(run_id=run_id)
        log.info(
            "supervisor_weekly_finished",
            run_id=run_id,
            action_taken=result.action_taken,
            email_sent=result.email_sent,
        )
    except Exception as e:
        log.error("supervisor_weekly_failed", run_id=run_id, error=str(e))
        send_alert("supervisor_weekly", e, run_id)
        raise


# ---------------------------------------------------------------------------
# Static file serving (SPA)
# MUST be last. Serves static assets by path, falls back to index.html
# for all other routes so React Router handles client-side navigation.
# ---------------------------------------------------------------------------

import os as _os
from pathlib import Path as _Path
from fastapi.responses import FileResponse as _FileResponse

# Absolute path to static/ relative to this file — works regardless of CWD
_STATIC_DIR = _Path(__file__).parent / "static"

if _STATIC_DIR.is_dir():
    # Mount asset subdirectories for direct file serving
    for _subdir in ("assets", "fonts", "images"):
        _subdir_path = _STATIC_DIR / _subdir
        if _subdir_path.is_dir():
            app.mount(f"/{_subdir}", StaticFiles(directory=str(_subdir_path)), name=_subdir)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve static files by path; fall back to index.html for all SPA routes."""
        candidate = _STATIC_DIR / full_path
        if candidate.is_file():
            return _FileResponse(str(candidate))
        return _FileResponse(str(_STATIC_DIR / "index.html"))

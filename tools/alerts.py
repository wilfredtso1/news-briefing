"""
Pipeline failure alert emails.

Sends a plain-text alert email to ALERT_EMAIL when a pipeline fails.
Designed to be called from the except block of any job endpoint.

Key safety properties:
- If ALERT_EMAIL env var is not set: logs and returns silently (no crash).
- If gmail_service.send_message() raises: logs the error and returns silently.
- Never re-raises any exception — alerts must not crash the caller that is
  already handling a pipeline failure.

Usage::

    from tools.alerts import send_alert

    try:
        run_pipeline(run_id)
    except Exception as exc:
        send_alert("daily_brief", exc, run_id)
        raise  # or handle as appropriate
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from gmail_service import GmailService

log = structlog.get_logger(__name__)

_ALERT_SUBJECT = "Pipeline failure: {pipeline_name}"
_TRACEBACK_TAIL_CHARS = 500


def send_alert(
    pipeline_name: str,
    error: Exception,
    run_id: str,
    *,
    _gmail_service: "GmailService | None" = None,
) -> None:
    """
    Send a plain-text failure alert email via Gmail.

    Args:
        pipeline_name: Human-readable name of the failed pipeline
                       (e.g. "daily_brief", "deep_read").
        error: The exception that caused the failure.
        run_id: Unique identifier for the failed pipeline run.
        _gmail_service: Optional pre-built GmailService instance.
                        If None, a new instance is created from env credentials.
                        This parameter exists for testing — callers should not
                        pass it in production.

    The function catches and logs all exceptions internally and never raises.
    If ALERT_EMAIL is not configured, the alert is skipped silently.
    """
    recipient = os.environ.get("ALERT_EMAIL", "")
    if not recipient:
        log.info(
            "alert_skipped",
            reason="ALERT_EMAIL not set",
            pipeline=pipeline_name,
            run_id=run_id,
        )
        return

    try:
        body = _build_body(pipeline_name, error, run_id)
        subject = _ALERT_SUBJECT.format(pipeline_name=pipeline_name)
        service = _gmail_service or _get_gmail_service()
        service.send_message(to=recipient, subject=subject, body=body)
        log.info(
            "alert_sent",
            pipeline=pipeline_name,
            run_id=run_id,
            recipient=recipient,
        )
    except Exception as exc:
        # Alerts must never crash the caller — log and swallow
        log.error(
            "alert_send_failed",
            pipeline=pipeline_name,
            run_id=run_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def _build_body(pipeline_name: str, error: Exception, run_id: str) -> str:
    """Build the plain-text alert email body."""
    tb_full = traceback.format_exc()
    tb_tail = tb_full[-_TRACEBACK_TAIL_CHARS:] if len(tb_full) > _TRACEBACK_TAIL_CHARS else tb_full

    timestamp = datetime.now(tz=timezone.utc).isoformat()

    return (
        f"Pipeline failure alert\n"
        f"======================\n\n"
        f"Pipeline:   {pipeline_name}\n"
        f"Run ID:     {run_id}\n"
        f"Error type: {type(error).__name__}\n"
        f"Timestamp:  {timestamp}\n\n"
        f"Traceback (last {_TRACEBACK_TAIL_CHARS} chars):\n"
        f"{tb_tail}"
    )


def _get_gmail_service() -> "GmailService":
    """Lazily import and instantiate GmailService. Deferred to avoid import-time auth."""
    from gmail_service import GmailService  # noqa: PLC0415
    return GmailService()

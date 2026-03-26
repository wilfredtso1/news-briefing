"""
Gmail API service wrapper.
Handles all Gmail interactions: reading, archiving, sending, and reply detection.

Uses raw Gmail API v1 throughout — LangChain's GmailLoader is not used because
it exposes only email content and cannot archive, detect thread replies, inspect
headers, or send messages.

Auth: OAuth2 with a long-lived refresh token stored in .env.
      The token is refreshed automatically by the Google auth library.
"""

from __future__ import annotations

import base64
import email as email_lib
import re
from dataclasses import dataclass
from email.mime.text import MIMEText

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings

log = structlog.get_logger(__name__)

BRIEFED_LABEL = "Briefed"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


@dataclass
class EmailMessage:
    """Parsed representation of a Gmail message."""
    message_id: str       # Gmail message ID
    thread_id: str        # Gmail thread ID
    subject: str
    sender: str           # "Name <email@example.com>" or "email@example.com"
    sender_email: str     # Extracted email address only
    body_text: str        # Plain text body (HTML stripped)
    body_html: str        # Raw HTML body (may be empty)
    list_unsubscribe: str | None  # Raw List-Unsubscribe header value
    list_id: str | None   # Raw List-Id header value
    date: str
    labels: list[str]


class GmailService:
    def __init__(self) -> None:
        self._service = self._build_service()
        self._briefed_label_id: str | None = None

    def _build_service(self):
        """Initialise Gmail API service with OAuth2 credentials."""
        creds = Credentials(
            token=None,
            refresh_token=settings.gmail_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret,
            scopes=SCOPES,
        )
        # Refresh immediately to surface auth errors at startup, not mid-pipeline
        creds.refresh(Request())
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # ---------------------------------------------------------------------------
    # Label management
    # ---------------------------------------------------------------------------

    def get_or_create_briefed_label(self) -> str:
        """
        Return the Gmail label ID for "Briefed", creating it if it doesn't exist.
        Cached after first call.
        """
        if self._briefed_label_id:
            return self._briefed_label_id

        labels = self._service.users().labels().list(userId="me").execute()
        for label in labels.get("labels", []):
            if label["name"] == BRIEFED_LABEL:
                self._briefed_label_id = label["id"]
                return self._briefed_label_id

        # Label doesn't exist — create it
        created = self._service.users().labels().create(
            userId="me",
            body={"name": BRIEFED_LABEL, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        ).execute()
        self._briefed_label_id = created["id"]
        log.info("gmail_label_created", label=BRIEFED_LABEL, label_id=self._briefed_label_id)
        return self._briefed_label_id

    # ---------------------------------------------------------------------------
    # Reading
    # ---------------------------------------------------------------------------

    def list_inbox_messages(self, max_results: int = 100) -> list[str]:
        """
        Return message IDs for unread messages currently in the inbox.
        Paginated — fetches up to max_results (hard cap to prevent unbounded reads).
        """
        message_ids: list[str] = []
        page_token = None

        while len(message_ids) < max_results:
            result = self._service.users().messages().list(
                userId="me",
                labelIds=["INBOX", "UNREAD"],
                maxResults=min(100, max_results - len(message_ids)),
                pageToken=page_token,
            ).execute()

            message_ids.extend(m["id"] for m in result.get("messages", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return message_ids

    def get_message(self, message_id: str) -> EmailMessage:
        """
        Fetch and parse a single Gmail message by ID.
        Raises HttpError if the message does not exist.
        """
        raw = self._service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()
        return self._parse_message(raw)

    def get_messages(self, message_ids: list[str]) -> list[EmailMessage]:
        """
        Fetch and parse multiple messages. Skips messages that fail to load
        (logs a warning) so a single bad email doesn't crash the pipeline.
        """
        messages = []
        for msg_id in message_ids:
            try:
                messages.append(self.get_message(msg_id))
            except HttpError as e:
                log.warning("gmail_message_fetch_failed", message_id=msg_id, error=str(e))
        return messages

    # ---------------------------------------------------------------------------
    # Archiving
    # ---------------------------------------------------------------------------

    def archive_message(self, message_id: str) -> None:
        """
        Move a message out of INBOX and apply the "Briefed" label.
        Does NOT delete the email — originals are preserved.
        """
        briefed_label_id = self.get_or_create_briefed_label()
        self._service.users().messages().modify(
            userId="me",
            id=message_id,
            body={
                "addLabelIds": [briefed_label_id],
                "removeLabelIds": ["INBOX", "UNREAD"],
            },
        ).execute()
        log.info("gmail_message_archived", message_id=message_id)

    def archive_messages(self, message_ids: list[str]) -> None:
        """Archive multiple messages. Logs failures but continues."""
        for msg_id in message_ids:
            try:
                self.archive_message(msg_id)
            except HttpError as e:
                log.warning("gmail_archive_failed", message_id=msg_id, error=str(e))

    # ---------------------------------------------------------------------------
    # Sending
    # ---------------------------------------------------------------------------

    def send_message(
        self, to: str, subject: str, body: str, thread_id: str | None = None
    ) -> tuple[str, str]:
        """
        Send a plain text email via the Gmail API.
        Pass thread_id to send as a reply within an existing thread.
        Returns (message_id, thread_id) — both needed to poll for replies later.
        """
        mime = MIMEText(body, "plain", "utf-8")
        mime["to"] = to
        mime["from"] = settings.gmail_send_as
        mime["subject"] = subject

        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        body_payload: dict = {"raw": raw}
        if thread_id:
            body_payload["threadId"] = thread_id

        sent = self._service.users().messages().send(
            userId="me",
            body=body_payload,
        ).execute()
        message_id = sent["id"]
        sent_thread_id = sent["threadId"]
        log.info("gmail_message_sent", to=to, subject=subject, message_id=message_id, thread_id=sent_thread_id)
        return message_id, sent_thread_id

    # ---------------------------------------------------------------------------
    # Reply detection (polling-based — no webhooks)
    # ---------------------------------------------------------------------------

    def get_thread_replies(self, thread_id: str, after_message_id: str) -> list[EmailMessage]:
        """
        Return messages in the thread that came AFTER after_message_id.
        Used to detect user replies to digest emails.

        Polling strategy: called periodically (e.g. every 15 min) for each
        sent digest thread. More reliable than Gmail push notifications for
        a single-user personal tool.
        """
        thread = self._service.users().threads().get(
            userId="me",
            id=thread_id,
            format="full",
        ).execute()

        messages = thread.get("messages", [])
        # Find the position of the sent digest message
        sent_index = next(
            (i for i, m in enumerate(messages) if m["id"] == after_message_id),
            None,
        )
        if sent_index is None:
            log.warning("gmail_thread_anchor_not_found", thread_id=thread_id, after_message_id=after_message_id)
            return []

        return [self._parse_message(m) for m in messages[sent_index + 1:]]

    # ---------------------------------------------------------------------------
    # Anchor detection
    # ---------------------------------------------------------------------------

    def list_messages_with_query(self, q: str, max_results: int = 10) -> list[EmailMessage]:
        """
        Return parsed EmailMessage objects matching an arbitrary Gmail search query.

        Uses the Gmail API q= parameter — supports the same syntax as the Gmail
        search bar (e.g. "from:me to:me is:unread", "subject:brief is:unread").

        Fetches up to max_results messages. Skips individual messages that fail
        to parse so a single bad email doesn't abort the scan.
        """
        result = self._service.users().messages().list(
            userId="me",
            q=q,
            maxResults=max_results,
        ).execute()

        message_ids = [m["id"] for m in result.get("messages", [])]
        if not message_ids:
            return []

        messages = []
        for msg_id in message_ids:
            try:
                messages.append(self.get_message(msg_id))
            except HttpError as e:
                log.warning("gmail_query_message_fetch_failed", message_id=msg_id, error=str(e))
        return messages

    def check_anchor_sources_present(self, anchor_emails: tuple[str, ...]) -> bool:
        """
        Return True if all anchor sender addresses have a message in the inbox
        since midnight today. Used to decide whether to trigger the daily pipeline.
        """
        for anchor_email in anchor_emails:
            result = self._service.users().messages().list(
                userId="me",
                q=f"from:{anchor_email} newer_than:1d",
                maxResults=1,
            ).execute()
            if not result.get("messages"):
                log.debug("anchor_not_yet_arrived", anchor=anchor_email)
                return False
        log.info("all_anchors_present", anchors=anchor_emails)
        return True

    # ---------------------------------------------------------------------------
    # Parsing (private)
    # ---------------------------------------------------------------------------

    def _parse_message(self, raw: dict) -> EmailMessage:
        """Parse a raw Gmail API message into an EmailMessage dataclass."""
        headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}

        sender_raw = headers.get("from", "")
        sender_email = _extract_email(sender_raw)
        body_text, body_html = _extract_body(raw.get("payload", {}))

        return EmailMessage(
            message_id=raw["id"],
            thread_id=raw["threadId"],
            subject=headers.get("subject", ""),
            sender=sender_raw,
            sender_email=sender_email,
            body_text=body_text,
            body_html=body_html,
            list_unsubscribe=headers.get("list-unsubscribe"),
            list_id=headers.get("list-id"),
            date=headers.get("date", ""),
            labels=raw.get("labelIds", []),
        )


# ---------------------------------------------------------------------------
# Helpers (module-level, pure functions — easy to unit test)
# ---------------------------------------------------------------------------

def _extract_email(sender: str) -> str:
    """
    Extract a bare email address from a sender string.
    Handles both "Name <email>" and plain "email" formats.
    """
    match = re.search(r"<([^>]+)>", sender)
    return match.group(1).lower().strip() if match else sender.lower().strip()


def _extract_body(payload: dict) -> tuple[str, str]:
    """
    Recursively extract plain text and HTML body parts from a Gmail payload.
    Returns (plain_text, html) — either may be empty string.
    """
    body_text = ""
    body_html = ""

    mime_type = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")

    if data:
        decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        if mime_type == "text/plain":
            body_text = decoded
        elif mime_type == "text/html":
            body_html = decoded

    for part in payload.get("parts", []):
        part_text, part_html = _extract_body(part)
        body_text = body_text or part_text
        body_html = body_html or part_html

    return body_text, body_html

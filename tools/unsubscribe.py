"""
Unsubscribe executor.

Parses the List-Unsubscribe header stored in newsletter_sources and executes
the unsubscribe — either sending a mailto: or making an HTTP GET request.
Marks the source as unsubscribed in the DB only after the action succeeds.

RFC 2369 List-Unsubscribe header format:
  <mailto:unsub@example.com?subject=unsubscribe>, <https://example.com/unsub?token=...>

Execution preference: mailto over URL. Mailto is simpler, broadly supported, and
does not require browser rendering or cookie state. If only a URL is present, we
send an HTTP GET.

This function is called by the supervisor after the user confirms an unsubscribe
request. It should never be called without explicit user confirmation.
"""

from __future__ import annotations

import re
import urllib.parse

import httpx
import structlog

from tools.db import get_source_by_email, mark_source_unsubscribed

log = structlog.get_logger(__name__)

# Timeout for HTTP unsubscribe requests — long enough for slow senders, short
# enough not to stall the pipeline.
_HTTP_TIMEOUT_SECS = 15


class UnsubscribeError(Exception):
    """
    Raised when unsubscribe execution fails before the source was marked inactive.
    The source remains active in the DB — caller should surface this to the user.
    """


def execute_unsubscribe(sender_email: str, gmail=None) -> str:
    """
    Execute the unsubscribe action for a newsletter source and mark it inactive in DB.

    Looks up the source's List-Unsubscribe header, parses it, executes the
    unsubscribe (mailto preferred over URL), then calls mark_source_unsubscribed.
    The DB is only updated after the action succeeds — a failed HTTP request or
    send error leaves the source active.

    Args:
        sender_email: Sender address of the newsletter to unsubscribe from.
        gmail: GmailService instance for sending mailto unsubscribes. If None,
               a new GmailService is created (requires Gmail env vars to be set).

    Returns:
        Human-readable description of the action taken (e.g. "sent mailto to unsub@example.com").

    Raises:
        UnsubscribeError: If no source or header is found, or the action fails.
    """
    source = get_source_by_email(sender_email)
    if not source:
        raise UnsubscribeError(
            f"No newsletter source found for sender: {sender_email}. "
            "Cannot unsubscribe — source may not be registered in newsletter_sources."
        )

    unsubscribe_header = source.get("unsubscribe_header")
    if not unsubscribe_header:
        raise UnsubscribeError(
            f"Source {sender_email} has no List-Unsubscribe header stored. "
            "Cannot unsubscribe automatically — remove this source manually."
        )

    parsed = _parse_unsubscribe_header(unsubscribe_header)
    log.info(
        "unsubscribe_header_parsed",
        sender_email=sender_email,
        has_mailto=bool(parsed["mailto"]),
        has_url=bool(parsed["url"]),
    )

    if parsed["mailto"]:
        description = _execute_mailto(parsed["mailto"], gmail)
    elif parsed["url"]:
        description = _execute_url(parsed["url"])
    else:
        raise UnsubscribeError(
            f"List-Unsubscribe header for {sender_email} contains no parseable mailto: or https: URI. "
            f"Raw header: {unsubscribe_header!r}"
        )

    mark_source_unsubscribed(sender_email)
    log.info("unsubscribe_complete", sender_email=sender_email, method=description)
    return description


def _parse_unsubscribe_header(header: str) -> dict[str, str | None]:
    """
    Extract the first mailto: and first https: URI from a List-Unsubscribe header.

    Header format (RFC 2369): comma-separated <URI> tokens.
    Example: '<mailto:unsub@example.com?subject=unsubscribe>, <https://example.com/unsub>'

    Returns {"mailto": str | None, "url": str | None}.
    """
    mailto: str | None = None
    url: str | None = None
    for match in re.finditer(r"<([^>]+)>", header):
        uri = match.group(1).strip()
        if uri.lower().startswith("mailto:") and mailto is None:
            mailto = uri
        elif (uri.lower().startswith("https://") or uri.lower().startswith("http://")) and url is None:
            url = uri
    return {"mailto": mailto, "url": url}


def _execute_mailto(mailto_uri: str, gmail) -> str:
    """
    Send an unsubscribe email using the address and parameters from a mailto: URI.

    Parses subject and body from the URI query string. Falls back to "unsubscribe"
    as the subject if not specified. Returns a human-readable action description.
    """
    parsed = urllib.parse.urlparse(mailto_uri)
    to_address = parsed.path
    if not to_address:
        raise UnsubscribeError(
            f"mailto URI has no address: {mailto_uri!r}. Cannot send unsubscribe email."
        )

    params = urllib.parse.parse_qs(parsed.query)
    subject = params.get("subject", ["unsubscribe"])[0]
    body = params.get("body", [""])[0]

    if gmail is None:
        from gmail_service import GmailService
        gmail = GmailService()

    gmail.send_message(to=to_address, subject=subject, body=body)
    log.info("unsubscribe_mailto_sent", to=to_address, subject=subject)
    return f"sent unsubscribe mailto to {to_address}"


def _execute_url(url: str) -> str:
    """
    Send an HTTP GET to the unsubscribe URL.

    Follows redirects. Raises UnsubscribeError on timeout, HTTP error, or
    network failure. Returns a human-readable action description.
    """
    try:
        response = httpx.get(url, follow_redirects=True, timeout=_HTTP_TIMEOUT_SECS)
        response.raise_for_status()
        log.info("unsubscribe_url_success", url=url, status_code=response.status_code)
        return f"GET {url} → {response.status_code}"
    except httpx.TimeoutException as e:
        raise UnsubscribeError(
            f"HTTP unsubscribe timed out after {_HTTP_TIMEOUT_SECS}s: {url}. "
            "Source was NOT marked unsubscribed. Retry or unsubscribe manually."
        ) from e
    except httpx.HTTPStatusError as e:
        raise UnsubscribeError(
            f"HTTP unsubscribe failed with {e.response.status_code}: {url}. "
            "Source was NOT marked unsubscribed."
        ) from e
    except httpx.RequestError as e:
        raise UnsubscribeError(
            f"HTTP unsubscribe request error for {url}: {e}. "
            "Source was NOT marked unsubscribed."
        ) from e

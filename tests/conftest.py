"""
Shared fixtures for all tests.

LLM calls: use LangChain's FakeListChatModel — never call real Anthropic API in tests.
Gmail: use fixture EmailMessage objects — never call real Gmail API in tests.
Database: tests that need DB access should use a separate test database or mock db.py.
"""

import pytest
from gmail_service import EmailMessage


# ---------------------------------------------------------------------------
# Email fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def news_brief_email() -> EmailMessage:
    """A typical Morning Brew news brief email."""
    return EmailMessage(
        message_id="msg_001",
        thread_id="thread_001",
        subject="Morning Brew ☕ Wednesday",
        sender="Morning Brew <morningbrew@morningbrew.com>",
        sender_email="morningbrew@morningbrew.com",
        body_text="Fed holds rates. Apple earnings beat. Tech layoffs continue. " * 50,
        body_html="<p>Fed holds rates...</p>",
        list_unsubscribe="<https://morningbrew.com/unsubscribe>",
        list_id="<morning-brew.morningbrew.com>",
        date="Wed, 26 Mar 2026 06:15:00 -0500",
        labels=["INBOX", "UNREAD"],
    )


@pytest.fixture
def long_form_email() -> EmailMessage:
    """A Stratechery essay — long body, known long_form sender."""
    return EmailMessage(
        message_id="msg_002",
        thread_id="thread_002",
        subject="Stratechery: The Platform Wars",
        sender="Stratechery <newsletters@stratechery.com>",
        sender_email="newsletters@stratechery.com",
        body_text=("This is a detailed analysis of the platform wars. " * 100),
        body_html="",
        list_unsubscribe="<mailto:unsubscribe@stratechery.com>",
        list_id="<stratechery.stratechery.com>",
        date="Wed, 26 Mar 2026 08:00:00 -0500",
        labels=["INBOX", "UNREAD"],
    )


@pytest.fixture
def personal_email() -> EmailMessage:
    """A personal email with no bulk-mail headers."""
    return EmailMessage(
        message_id="msg_003",
        thread_id="thread_003",
        subject="Lunch tomorrow?",
        sender="John Smith <john@example.com>",
        sender_email="john@example.com",
        body_text="Hey, want to grab lunch tomorrow at noon?",
        body_html="",
        list_unsubscribe=None,
        list_id=None,
        date="Wed, 26 Mar 2026 09:00:00 -0500",
        labels=["INBOX", "UNREAD"],
    )


@pytest.fixture
def transactional_email() -> EmailMessage:
    """A noreply transactional email."""
    return EmailMessage(
        message_id="msg_004",
        thread_id="thread_004",
        subject="Your order has shipped",
        sender="noreply@amazon.com",
        sender_email="noreply@amazon.com",
        body_text="Your order #123 has shipped.",
        body_html="",
        list_unsubscribe=None,
        list_id=None,
        date="Wed, 26 Mar 2026 07:00:00 -0500",
        labels=["INBOX", "UNREAD"],
    )


@pytest.fixture
def unknown_newsletter_email() -> EmailMessage:
    """An unknown newsletter sender with List-Unsubscribe but short body → news_brief."""
    return EmailMessage(
        message_id="msg_005",
        thread_id="thread_005",
        subject="The Weekly Roundup",
        sender="Weekly Roundup <hello@weeklyroundup.io>",
        sender_email="hello@weeklyroundup.io",
        body_text="Top stories this week: AI raises $1B. Markets rally. " * 30,
        body_html="",
        list_unsubscribe="<https://weeklyroundup.io/unsubscribe?token=abc>",
        list_id=None,
        date="Wed, 26 Mar 2026 07:30:00 -0500",
        labels=["INBOX", "UNREAD"],
    )


@pytest.fixture
def axios_am_email() -> EmailMessage:
    """Axios AM — one of the two anchor sources."""
    return EmailMessage(
        message_id="msg_006",
        thread_id="thread_006",
        subject="Axios AM",
        sender="Axios <axiosam@axios.com>",
        sender_email="axiosam@axios.com",
        body_text="Good morning. Here is what matters today. " * 40,
        body_html="",
        list_unsubscribe="<https://axios.com/unsubscribe>",
        list_id="<axios-am.axios.com>",
        date="Wed, 26 Mar 2026 06:00:00 -0500",
        labels=["INBOX", "UNREAD"],
    )

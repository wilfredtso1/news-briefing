"""
Application configuration with startup validation.
All env vars are validated here at import time — the app crashes immediately
if anything required is missing, rather than failing mid-pipeline.
"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # Anthropic
    anthropic_api_key: str

    # Voyage AI
    voyage_api_key: str

    # Tavily
    tavily_api_key: str

    # LangSmith
    langchain_api_key: str
    langchain_project: str

    # Gmail OAuth2
    gmail_client_id: str
    gmail_client_secret: str
    gmail_refresh_token: str
    gmail_send_as: str

    # Database
    database_url: str

    # Pipeline behaviour
    anchor_sources: tuple[str, ...]
    anchor_cutoff_hour: int  # Hard cutoff — run regardless of anchors after this hour (local time)
    deep_read_threshold: int  # Number of long-form pieces before triggering Deep Read
    cosine_similarity_threshold: float

    # Optional — code change agent notification email
    code_change_notify_email: Optional[str] = None


def _require(key: str) -> str:
    """Return env var value or raise with a clear, actionable message."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"Add it to your .env file. See .env.example for the expected format."
        )
    return value


def _load() -> Config:
    missing: list[str] = []
    values: dict = {}

    required = [
        "ANTHROPIC_API_KEY",
        "VOYAGE_API_KEY",
        "TAVILY_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_PROJECT",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "GMAIL_REFRESH_TOKEN",
        "GMAIL_SEND_AS",
        "DATABASE_URL",
    ]

    for key in required:
        value = os.getenv(key)
        if not value:
            missing.append(key)
        else:
            values[key] = value

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Add them to your .env file. See .env.example for expected formats."
        )

    # Set LangSmith env vars so LangChain picks them up automatically
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = values["LANGCHAIN_API_KEY"]
    os.environ["LANGCHAIN_PROJECT"] = values["LANGCHAIN_PROJECT"]

    return Config(
        anthropic_api_key=values["ANTHROPIC_API_KEY"],
        voyage_api_key=values["VOYAGE_API_KEY"],
        tavily_api_key=values["TAVILY_API_KEY"],
        langchain_api_key=values["LANGCHAIN_API_KEY"],
        langchain_project=values["LANGCHAIN_PROJECT"],
        gmail_client_id=values["GMAIL_CLIENT_ID"],
        gmail_client_secret=values["GMAIL_CLIENT_SECRET"],
        gmail_refresh_token=values["GMAIL_REFRESH_TOKEN"],
        gmail_send_as=values["GMAIL_SEND_AS"],
        database_url=values["DATABASE_URL"],
        # Pipeline defaults — tunable via agent_config table at runtime
        anchor_sources=tuple(
            s.strip()
            for s in os.getenv("ANCHOR_SOURCES", "axiosam@axios.com,morningbrew@morningbrew.com").split(",")
        ),
        anchor_cutoff_hour=int(os.getenv("ANCHOR_CUTOFF_HOUR", "10")),
        deep_read_threshold=int(os.getenv("DEEP_READ_THRESHOLD", "5")),
        cosine_similarity_threshold=float(os.getenv("COSINE_SIMILARITY_THRESHOLD", "0.82")),
        code_change_notify_email=os.getenv("CODE_CHANGE_NOTIFY_EMAIL") or os.getenv("ALERT_EMAIL"),
    )


# Singleton — loaded once at startup, fails fast if config is broken
settings = _load()

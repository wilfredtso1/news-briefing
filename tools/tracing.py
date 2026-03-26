"""
LangSmith tracing utilities.

Provides @traced(name) decorator that wraps sync and async callables with
a LangSmith trace. Designed as a drop-in with zero-crash fallback:

- If LANGSMITH_API_KEY is absent or empty: decorator passes through with no tracing.
- If the langsmith package is not installed: logs a warning once, then passes through.

Usage::

    from tools.tracing import traced

    @traced("story_synthesizer")
    def synthesize(stories):
        ...

    @traced("story_extractor")
    async def extract_async(email):
        ...
"""

from __future__ import annotations

import asyncio
import functools
import os
from typing import Any, Callable

import structlog

log = structlog.get_logger(__name__)

# Attempt to import langsmith once at module load time.
# If unavailable, _langsmith_trace is None and the decorator becomes a no-op.
try:
    from langsmith import trace as _langsmith_trace  # type: ignore[import-untyped]
except ImportError:
    _langsmith_trace = None
    log.warning(
        "langsmith_not_installed",
        message="langsmith package is not installed — @traced decorator is a no-op. "
                "Install it with: pip install langsmith",
    )


def traced(name: str) -> Callable:
    """
    Decorator factory that wraps a callable with a LangSmith trace named `name`.

    Works on both sync and async functions. When tracing is unavailable (missing
    API key or missing package), returns the original callable unchanged — callers
    never need to handle the absent-tracing case.

    Args:
        name: The trace name shown in the LangSmith UI.

    Returns:
        A decorator that, when applied, wraps the function with tracing if available.
    """
    def decorator(fn: Callable) -> Callable:
        # No-op if langsmith is missing or key is not configured
        api_key = os.environ.get("LANGSMITH_API_KEY", "")
        if _langsmith_trace is None or not api_key:
            return fn

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with _langsmith_trace(name=name):
                    return await fn(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with _langsmith_trace(name=name):
                    return fn(*args, **kwargs)
            return sync_wrapper

    return decorator

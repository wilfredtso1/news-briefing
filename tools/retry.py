"""
Retry wrapper for pipeline steps.

Provides with_retry(fn, max_attempts, delay) which transparently handles both
sync and async callables. Retries only transient/recoverable errors — fatal
errors are re-raised immediately without consuming retry budget.

Retryable errors:
  - httpx.NetworkError (and subclasses) — transient connectivity issues
  - Any exception whose HTTP status code is 429 (rate limit)
  - Any exception whose message contains "rate limit" (case-insensitive)

Fatal errors (raised immediately, no retry):
  - AuthenticationError — credentials are wrong; retrying won't help
  - ValueError, TypeError — caller error in arguments or schema; not transient
  - Any other exception not matching retryable criteria

Each attempt is logged with: attempt number, error type, will_retry flag.
After all retries are exhausted, the last exception is re-raised.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

import structlog

log = structlog.get_logger(__name__)

# Attempt to import httpx — it is in requirements.txt, but guard anyway
try:
    import httpx
    _HTTPX_NETWORK_ERROR = httpx.NetworkError
except ImportError:
    _HTTPX_NETWORK_ERROR = None  # type: ignore[assignment,misc]

# Attempt to import requests — not in requirements, but guard gracefully
try:
    import requests
    _REQUESTS_CONNECTION_ERROR = requests.exceptions.ConnectionError
except ImportError:
    _REQUESTS_CONNECTION_ERROR = None  # type: ignore[assignment,misc]


# Fatal error types: re-raise immediately without retry
_FATAL_TYPES = (ValueError, TypeError)

# Authentication errors may come from various SDK classes.
# We match by type name to avoid hard-coupling to Anthropic's SDK.
_FATAL_TYPE_NAMES = frozenset({"AuthenticationError"})


def _is_fatal(exc: BaseException) -> bool:
    """Return True if this error should never be retried."""
    if isinstance(exc, _FATAL_TYPES):
        return True
    if type(exc).__name__ in _FATAL_TYPE_NAMES:
        return True
    return False


def with_retry(
    fn: Callable,
    max_attempts: int = 3,
    delay: float = 5.0,
) -> Callable:
    """
    Return a wrapper around `fn` that retries on transient errors.

    Args:
        fn: Any sync or async callable to wrap.
        max_attempts: Total number of attempts (including the first). Must be >= 1.
        delay: Seconds to wait between attempts. Uses time.sleep for sync,
               asyncio.sleep for async.

    Returns:
        A wrapper with the same signature as `fn`.

    Raises:
        The last exception after all retries are exhausted.
        Fatal errors (AuthenticationError, ValueError, TypeError) are re-raised
        on the first occurrence without consuming retry budget.
    """
    if asyncio.iscoroutinefunction(fn):
        return _async_wrapper(fn, max_attempts, delay)
    return _sync_wrapper(fn, max_attempts, delay)


def _sync_wrapper(fn: Callable, max_attempts: int, delay: float) -> Callable:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: BaseException | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return fn(*args, **kwargs)
            except BaseException as exc:
                last_exc = exc
                is_last = attempt == max_attempts
                will_retry = not is_last and not _is_fatal(exc)

                log.warning(
                    "retry_attempt",
                    fn=fn.__name__,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_type=type(exc).__name__,
                    will_retry=will_retry,
                )

                if _is_fatal(exc):
                    raise

                if will_retry:
                    time.sleep(delay)
                else:
                    raise

        # Should not be reached, but satisfies type checker
        raise last_exc  # type: ignore[misc]

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    return wrapper


def _async_wrapper(fn: Callable, max_attempts: int, delay: float) -> Callable:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: BaseException | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await fn(*args, **kwargs)
            except BaseException as exc:
                last_exc = exc
                is_last = attempt == max_attempts
                will_retry = not is_last and not _is_fatal(exc)

                log.warning(
                    "retry_attempt",
                    fn=fn.__name__,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_type=type(exc).__name__,
                    will_retry=will_retry,
                )

                if _is_fatal(exc):
                    raise

                if will_retry:
                    await asyncio.sleep(delay)
                else:
                    raise

        raise last_exc  # type: ignore[misc]

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    return wrapper

"""
Tests for tools/retry.py

Covers:
- Successful call on first attempt returns result
- Retryable errors: retried up to max_attempts, then raised
- Fatal errors (ValueError, TypeError, AuthenticationError): raised immediately, no retry
- Rate-limit detection: by status_code=429 and by "rate limit" in message
- Retry count: exactly N-1 retries before raising
- Exhaustion: last exception is raised after all attempts
- Sync and async function support
- Delay argument: sleep is called between retries (not before first, not after last)
- with_retry returns a wrapper with the same name as the original function
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from tools.retry import with_retry


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class NetworkError(Exception):
    """Simulates httpx.NetworkError."""
    pass


class RateLimitError(Exception):
    """Simulates a 429 response from an LLM API."""
    def __init__(self, msg: str = "Rate limit exceeded"):
        super().__init__(msg)
        self.status_code = 429


class RateLimitByMessageError(Exception):
    """Simulates a rate limit error identified by message text."""
    def __init__(self):
        super().__init__("API error: rate limit reached, please slow down")


class AuthenticationError(Exception):
    """Simulates Anthropic's AuthenticationError (fatal)."""
    pass


def _make_failing_fn(exception: Exception, succeed_on: int | None = None):
    """
    Return a sync function that raises `exception` on each call.
    If succeed_on is given, succeeds (returns "ok") on that attempt number (1-indexed).
    """
    calls = [0]

    def fn(*args: Any, **kwargs: Any) -> str:
        calls[0] += 1
        if succeed_on is not None and calls[0] == succeed_on:
            return "ok"
        raise exception

    fn.__name__ = "failing_fn"
    fn.__qualname__ = "failing_fn"
    return fn


def _make_async_failing_fn(exception: Exception, succeed_on: int | None = None):
    """Async version of _make_failing_fn."""
    calls = [0]

    async def fn(*args: Any, **kwargs: Any) -> str:
        calls[0] += 1
        if succeed_on is not None and calls[0] == succeed_on:
            return "ok"
        raise exception

    fn.__name__ = "async_failing_fn"
    fn.__qualname__ = "async_failing_fn"
    return fn


# ---------------------------------------------------------------------------
# Tests: successful calls
# ---------------------------------------------------------------------------

class TestWithRetrySuccess:
    def test_sync_success_on_first_attempt_returns_result(self):
        """A function that succeeds immediately returns its value unchanged."""
        def fn(x: int) -> int:
            return x * 2

        wrapped = with_retry(fn, max_attempts=3, delay=0)
        assert wrapped(5) == 10

    def test_async_success_on_first_attempt_returns_result(self):
        """An async function that succeeds immediately returns its value unchanged."""
        async def fn(x: int) -> int:
            return x + 1

        wrapped = with_retry(fn, max_attempts=3, delay=0)
        result = asyncio.get_event_loop().run_until_complete(wrapped(9))
        assert result == 10

    def test_sync_succeeds_on_second_attempt(self):
        """Function that fails once then succeeds returns the successful result."""
        import httpx

        exc = httpx.NetworkError("connection refused")
        fn = _make_failing_fn(exc, succeed_on=2)

        with patch("tools.retry.time.sleep"):
            wrapped = with_retry(fn, max_attempts=3, delay=0.001)
            assert wrapped() == "ok"

    def test_async_succeeds_on_second_attempt(self):
        """Async function that fails once then succeeds returns the successful result."""
        import httpx

        exc = httpx.NetworkError("connection refused")
        fn = _make_async_failing_fn(exc, succeed_on=2)

        with patch("tools.retry.asyncio.sleep", new_callable=AsyncMock):
            wrapped = with_retry(fn, max_attempts=3, delay=0.001)
            result = asyncio.get_event_loop().run_until_complete(wrapped())
        assert result == "ok"


# ---------------------------------------------------------------------------
# Tests: retryable errors
# ---------------------------------------------------------------------------

class TestWithRetryRetryableErrors:
    def test_network_error_retried_up_to_max_attempts(self):
        """httpx.NetworkError triggers retries up to max_attempts."""
        import httpx

        exc = httpx.NetworkError("connection refused")
        fn = _make_failing_fn(exc)
        call_count = [0]
        original_fn = fn

        def counting_fn(*args, **kwargs):
            call_count[0] += 1
            return original_fn(*args, **kwargs)

        counting_fn.__name__ = "counting_fn"
        counting_fn.__qualname__ = "counting_fn"

        with patch("tools.retry.time.sleep"):
            wrapped = with_retry(counting_fn, max_attempts=3, delay=0.001)
            with pytest.raises(httpx.NetworkError):
                wrapped()

        assert call_count[0] == 3, f"Expected 3 attempts, got {call_count[0]}"

    def test_rate_limit_by_status_code_retried(self):
        """Error with status_code=429 is treated as retryable."""
        exc = RateLimitError()
        fn = _make_failing_fn(exc)

        with patch("tools.retry.time.sleep"):
            wrapped = with_retry(fn, max_attempts=2, delay=0.001)
            with pytest.raises(RateLimitError):
                wrapped()

    def test_rate_limit_by_message_retried(self):
        """Error with 'rate limit' in message is treated as retryable."""
        exc = RateLimitByMessageError()
        fn = _make_failing_fn(exc)

        with patch("tools.retry.time.sleep"):
            wrapped = with_retry(fn, max_attempts=2, delay=0.001)
            with pytest.raises(RateLimitByMessageError):
                wrapped()

    def test_rate_limit_message_is_case_insensitive(self):
        """'Rate Limit' and 'RATE LIMIT' in message are both detected."""
        class UpperRateLimit(Exception):
            def __init__(self):
                super().__init__("RATE LIMIT exceeded")

        exc = UpperRateLimit()
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise exc

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.time.sleep"):
            wrapped = with_retry(fn, max_attempts=3, delay=0)
            with pytest.raises(UpperRateLimit):
                wrapped()

        assert call_count[0] == 3

    def test_async_network_error_retried(self):
        """Async: httpx.NetworkError triggers retries."""
        import httpx

        exc = httpx.NetworkError("timeout")
        fn = _make_async_failing_fn(exc)
        call_count = [0]

        async def counting_fn():
            call_count[0] += 1
            raise exc

        counting_fn.__name__ = "counting_fn"
        counting_fn.__qualname__ = "counting_fn"

        with patch("tools.retry.asyncio.sleep", new_callable=AsyncMock):
            wrapped = with_retry(counting_fn, max_attempts=3, delay=0.001)
            with pytest.raises(httpx.NetworkError):
                asyncio.get_event_loop().run_until_complete(wrapped())

        assert call_count[0] == 3


# ---------------------------------------------------------------------------
# Tests: fatal errors — raised immediately
# ---------------------------------------------------------------------------

class TestWithRetryFatalErrors:
    def test_value_error_raised_immediately(self):
        """ValueError is fatal — first occurrence raises without retry."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise ValueError("bad input schema")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        wrapped = with_retry(fn, max_attempts=3, delay=0)
        with pytest.raises(ValueError, match="bad input schema"):
            wrapped()

        assert call_count[0] == 1, f"Expected 1 attempt (no retry), got {call_count[0]}"

    def test_type_error_raised_immediately(self):
        """TypeError is fatal — first occurrence raises without retry."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise TypeError("wrong type")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        wrapped = with_retry(fn, max_attempts=3, delay=0)
        with pytest.raises(TypeError):
            wrapped()

        assert call_count[0] == 1

    def test_authentication_error_raised_immediately(self):
        """AuthenticationError (matched by type name) is fatal — no retry."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise AuthenticationError("invalid API key")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        wrapped = with_retry(fn, max_attempts=3, delay=0)
        with pytest.raises(AuthenticationError):
            wrapped()

        assert call_count[0] == 1

    def test_async_value_error_raised_immediately(self):
        """Async: ValueError is fatal — raised immediately."""
        call_count = [0]

        async def fn():
            call_count[0] += 1
            raise ValueError("schema mismatch")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        wrapped = with_retry(fn, max_attempts=3, delay=0)
        with pytest.raises(ValueError):
            asyncio.get_event_loop().run_until_complete(wrapped())

        assert call_count[0] == 1

    def test_async_authentication_error_raised_immediately(self):
        """Async: AuthenticationError is fatal — raised immediately."""
        call_count = [0]

        async def fn():
            call_count[0] += 1
            raise AuthenticationError("bad credentials")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        wrapped = with_retry(fn, max_attempts=3, delay=0)
        with pytest.raises(AuthenticationError):
            asyncio.get_event_loop().run_until_complete(wrapped())

        assert call_count[0] == 1


# ---------------------------------------------------------------------------
# Tests: retry count and exhaustion
# ---------------------------------------------------------------------------

class TestWithRetryExhaustion:
    def test_exactly_max_attempts_are_made(self):
        """with_retry makes exactly max_attempts total (not max_attempts - 1)."""
        import httpx

        call_count = [0]

        def fn():
            call_count[0] += 1
            raise httpx.NetworkError("down")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.time.sleep"):
            wrapped = with_retry(fn, max_attempts=5, delay=0.001)
            with pytest.raises(httpx.NetworkError):
                wrapped()

        assert call_count[0] == 5

    def test_last_exception_is_raised_after_exhaustion(self):
        """The exception raised after exhaustion is the last one — not a wrapped error."""
        import httpx

        def fn():
            raise httpx.NetworkError("specific message")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.time.sleep"):
            wrapped = with_retry(fn, max_attempts=2, delay=0.001)
            with pytest.raises(httpx.NetworkError, match="specific message"):
                wrapped()

    def test_sleep_called_between_attempts_not_after_last(self):
        """Sleep is called max_attempts - 1 times (between attempts, not after the last)."""
        import httpx

        def fn():
            raise httpx.NetworkError("fail")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.time.sleep") as mock_sleep:
            wrapped = with_retry(fn, max_attempts=4, delay=5)
            with pytest.raises(httpx.NetworkError):
                wrapped()

        # 4 attempts → 3 sleeps (between 1→2, 2→3, 3→4; none after attempt 4)
        assert mock_sleep.call_count == 3
        mock_sleep.assert_called_with(5)

    def test_async_sleep_called_between_attempts(self):
        """Async: asyncio.sleep is called max_attempts - 1 times."""
        import httpx

        async def fn():
            raise httpx.NetworkError("fail")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            wrapped = with_retry(fn, max_attempts=3, delay=2)
            with pytest.raises(httpx.NetworkError):
                asyncio.get_event_loop().run_until_complete(wrapped())

        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2)

    def test_max_attempts_one_does_not_retry(self):
        """max_attempts=1 means a single attempt — no retries even for retryable errors."""
        import httpx

        call_count = [0]

        def fn():
            call_count[0] += 1
            raise httpx.NetworkError("fail")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.time.sleep") as mock_sleep:
            wrapped = with_retry(fn, max_attempts=1, delay=5)
            with pytest.raises(httpx.NetworkError):
                wrapped()

        assert call_count[0] == 1
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: logging
# ---------------------------------------------------------------------------

class TestWithRetryLogging:
    def test_each_attempt_is_logged(self):
        """with_retry logs a warning for each failed attempt."""
        import httpx

        def fn():
            raise httpx.NetworkError("fail")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.time.sleep"), \
             patch("tools.retry.log") as mock_log:
            wrapped = with_retry(fn, max_attempts=3, delay=0.001)
            with pytest.raises(httpx.NetworkError):
                wrapped()

        assert mock_log.warning.call_count == 3

    def test_log_includes_will_retry_true_for_non_last_attempt(self):
        """Log entry for non-final attempts has will_retry=True."""
        import httpx

        def fn():
            raise httpx.NetworkError("fail")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.time.sleep"), \
             patch("tools.retry.log") as mock_log:
            wrapped = with_retry(fn, max_attempts=3, delay=0.001)
            with pytest.raises(httpx.NetworkError):
                wrapped()

        # First call: attempt=1, will_retry=True
        first_call_kwargs = mock_log.warning.call_args_list[0][1]
        assert first_call_kwargs["will_retry"] is True
        assert first_call_kwargs["attempt"] == 1

    def test_log_includes_will_retry_false_for_last_attempt(self):
        """Log entry for the final attempt has will_retry=False."""
        import httpx

        def fn():
            raise httpx.NetworkError("fail")

        fn.__name__ = "fn"
        fn.__qualname__ = "fn"

        with patch("tools.retry.time.sleep"), \
             patch("tools.retry.log") as mock_log:
            wrapped = with_retry(fn, max_attempts=3, delay=0.001)
            with pytest.raises(httpx.NetworkError):
                wrapped()

        # Last call: attempt=3, will_retry=False
        last_call_kwargs = mock_log.warning.call_args_list[2][1]
        assert last_call_kwargs["will_retry"] is False
        assert last_call_kwargs["attempt"] == 3


# ---------------------------------------------------------------------------
# Tests: wrapper metadata
# ---------------------------------------------------------------------------

class TestWithRetryMetadata:
    def test_sync_wrapper_preserves_function_name(self):
        """with_retry(fn).__name__ matches the original function name."""
        def my_pipeline_step():
            pass

        wrapped = with_retry(my_pipeline_step, max_attempts=3, delay=0)
        assert wrapped.__name__ == "my_pipeline_step"

    def test_async_wrapper_preserves_function_name(self):
        """with_retry(async fn).__name__ matches the original function name."""
        async def my_async_step():
            pass

        wrapped = with_retry(my_async_step, max_attempts=3, delay=0)
        assert wrapped.__name__ == "my_async_step"

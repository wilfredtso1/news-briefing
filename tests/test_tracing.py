"""
Tests for tools/tracing.py

Covers:
- @traced wraps sync functions and passes return value through
- @traced wraps async functions and passes return value through
- @traced is a no-op when LANGSMITH_API_KEY is absent or empty
- @traced is a no-op when langsmith is unavailable (simulated via monkeypatch)
- Decorated function still raises exceptions normally
- Original function metadata is preserved (functools.wraps)
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_tracing():
    """Re-import tools.tracing so module-level import state is fresh."""
    if "tools.tracing" in sys.modules:
        del sys.modules["tools.tracing"]
    import tools.tracing  # noqa: PLC0415
    return tools.tracing


# ---------------------------------------------------------------------------
# Tests: no-op when LANGSMITH_API_KEY is absent or empty
# ---------------------------------------------------------------------------

class TestTracedNoOpWithoutKey:
    def test_sync_function_returned_unchanged_when_key_absent(self, monkeypatch):
        """@traced passes sync function through unchanged if LANGSMITH_API_KEY is not set."""
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

        # Reload so the module picks up the monkeypatched env
        mod = _reload_tracing()

        @mod.traced("test_op")
        def my_fn(x: int) -> int:
            return x * 2

        assert my_fn(5) == 10

    def test_sync_function_returned_unchanged_when_key_empty(self, monkeypatch):
        """@traced is a no-op when LANGSMITH_API_KEY is an empty string."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "")

        mod = _reload_tracing()

        @mod.traced("test_op")
        def my_fn(x: int) -> int:
            return x * 3

        assert my_fn(4) == 12

    def test_async_function_returned_unchanged_when_key_absent(self, monkeypatch):
        """@traced passes async function through unchanged if LANGSMITH_API_KEY is not set."""
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

        mod = _reload_tracing()

        @mod.traced("test_async_op")
        async def my_async_fn(x: int) -> int:
            return x + 10

        result = asyncio.get_event_loop().run_until_complete(my_async_fn(5))
        assert result == 15

    def test_no_op_does_not_require_langsmith_package(self, monkeypatch):
        """If langsmith is not installed, decorator is still a no-op — no ImportError crash."""
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

        # Simulate missing langsmith package by patching _langsmith_trace to None
        mod = _reload_tracing()
        with patch.object(mod, "_langsmith_trace", None):
            @mod.traced("test_op")
            def my_fn() -> str:
                return "hello"

            assert my_fn() == "hello"


# ---------------------------------------------------------------------------
# Tests: tracing active when key is present
# ---------------------------------------------------------------------------

class TestTracedWithKey:
    def _make_mock_trace_context(self):
        """Return a mock context manager for langsmith.trace()."""
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    def test_sync_function_return_value_passes_through(self, monkeypatch):
        """Traced sync function returns correct value."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key-123")
        mod = _reload_tracing()

        ctx = self._make_mock_trace_context()
        mock_trace = MagicMock(return_value=ctx)

        with patch.object(mod, "_langsmith_trace", mock_trace):
            @mod.traced("my_op")
            def compute(a: int, b: int) -> int:
                return a + b

            result = compute(3, 4)

        assert result == 7

    def test_sync_function_enters_and_exits_trace_context(self, monkeypatch):
        """Traced sync function enters and exits the LangSmith context manager."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key-123")
        mod = _reload_tracing()

        ctx = self._make_mock_trace_context()
        mock_trace = MagicMock(return_value=ctx)

        with patch.object(mod, "_langsmith_trace", mock_trace):
            @mod.traced("my_op")
            def compute() -> int:
                return 42

            compute()

        mock_trace.assert_called_once_with(name="my_op")
        ctx.__enter__.assert_called_once()
        ctx.__exit__.assert_called_once()

    def test_async_function_return_value_passes_through(self, monkeypatch):
        """Traced async function returns correct value."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key-123")
        mod = _reload_tracing()

        ctx = self._make_mock_trace_context()
        mock_trace = MagicMock(return_value=ctx)

        with patch.object(mod, "_langsmith_trace", mock_trace):
            @mod.traced("async_op")
            async def fetch(val: str) -> str:
                return f"result:{val}"

            result = asyncio.get_event_loop().run_until_complete(fetch("x"))

        assert result == "result:x"

    def test_async_function_enters_and_exits_trace_context(self, monkeypatch):
        """Traced async function enters and exits the LangSmith context manager."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key-123")
        mod = _reload_tracing()

        ctx = self._make_mock_trace_context()
        mock_trace = MagicMock(return_value=ctx)

        with patch.object(mod, "_langsmith_trace", mock_trace):
            @mod.traced("async_op")
            async def fetch() -> int:
                return 1

            asyncio.get_event_loop().run_until_complete(fetch())

        mock_trace.assert_called_once_with(name="async_op")
        ctx.__enter__.assert_called_once()
        ctx.__exit__.assert_called_once()

    def test_trace_name_passed_correctly(self, monkeypatch):
        """The name argument to @traced is forwarded to langsmith.trace()."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key")
        mod = _reload_tracing()

        ctx = self._make_mock_trace_context()
        mock_trace = MagicMock(return_value=ctx)

        with patch.object(mod, "_langsmith_trace", mock_trace):
            @mod.traced("synthesizer_run")
            def fn():
                pass

            fn()

        mock_trace.assert_called_with(name="synthesizer_run")


# ---------------------------------------------------------------------------
# Tests: exception propagation
# ---------------------------------------------------------------------------

class TestTracedExceptionPropagation:
    def test_sync_exception_propagates_through_trace(self, monkeypatch):
        """Exceptions from wrapped sync functions propagate normally."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key")
        mod = _reload_tracing()

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_trace = MagicMock(return_value=ctx)

        with patch.object(mod, "_langsmith_trace", mock_trace):
            @mod.traced("boom")
            def blow_up():
                raise ValueError("test error")

            with pytest.raises(ValueError, match="test error"):
                blow_up()

    def test_async_exception_propagates_through_trace(self, monkeypatch):
        """Exceptions from wrapped async functions propagate normally."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key")
        mod = _reload_tracing()

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_trace = MagicMock(return_value=ctx)

        with patch.object(mod, "_langsmith_trace", mock_trace):
            @mod.traced("async_boom")
            async def blow_up():
                raise RuntimeError("async fail")

            with pytest.raises(RuntimeError, match="async fail"):
                asyncio.get_event_loop().run_until_complete(blow_up())

    def test_no_op_exception_propagates(self, monkeypatch):
        """Exceptions propagate even when tracing is a no-op."""
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        mod = _reload_tracing()

        @mod.traced("irrelevant")
        def blow_up():
            raise KeyError("missing key")

        with pytest.raises(KeyError, match="missing key"):
            blow_up()


# ---------------------------------------------------------------------------
# Tests: functools.wraps — metadata preservation
# ---------------------------------------------------------------------------

class TestTracedFunctoolsWraps:
    def test_sync_wrapper_preserves_function_name(self, monkeypatch):
        """@traced preserves __name__ for sync functions when tracing is active."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key")
        mod = _reload_tracing()

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch.object(mod, "_langsmith_trace", MagicMock(return_value=ctx)):
            @mod.traced("op")
            def my_special_function():
                pass

            assert my_special_function.__name__ == "my_special_function"

    def test_async_wrapper_preserves_function_name(self, monkeypatch):
        """@traced preserves __name__ for async functions when tracing is active."""
        monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key")
        mod = _reload_tracing()

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch.object(mod, "_langsmith_trace", MagicMock(return_value=ctx)):
            @mod.traced("op")
            async def my_async_function():
                pass

            assert my_async_function.__name__ == "my_async_function"

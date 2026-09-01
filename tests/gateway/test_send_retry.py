"""
Tests for BasePlatformAdapter._send_with_retry and _is_retryable_error.

Verifies that:
- Transient network errors trigger retry with backoff
- Permanent errors fall back to plain-text immediately (no retry)
- User receives a delivery-failure notice when all retries are exhausted
- Successful sends on retry return success
- SendResult.retryable flag is respected
"""
import pytest
from unittest.mock import AsyncMock, patch

from gateway.platforms.base import BasePlatformAdapter, SendResult, _RETRYABLE_ERROR_PATTERNS
from gateway.platforms.base import Platform, PlatformConfig


# ---------------------------------------------------------------------------
# Minimal concrete adapter for testing (no real network)
# ---------------------------------------------------------------------------

class _StubAdapter(BasePlatformAdapter):
    def __init__(self):
        cfg = PlatformConfig()
        super().__init__(cfg, Platform.TELEGRAM)
        self._send_results = []   # queue of SendResult to return per call
        self._send_calls = []     # record of (chat_id, content) sent

    def _next_result(self) -> SendResult:
        if self._send_results:
            return self._send_results.pop(0)
        return SendResult(success=True, message_id="ok")

    async def send(self, chat_id, content, reply_to=None, metadata=None, **kwargs) -> SendResult:
        self._send_calls.append((chat_id, content))
        return self._next_result()

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        return True

    async def disconnect(self) -> None:
        pass

    async def send_typing(self, chat_id, metadata=None) -> None:
        pass

    async def get_chat_info(self, chat_id):
        return {"name": "test", "type": "direct", "chat_id": chat_id}


# ---------------------------------------------------------------------------
# _is_retryable_error
# ---------------------------------------------------------------------------

class TestIsRetryableError:
    def test_none_is_not_retryable(self):
        assert not _StubAdapter._is_retryable_error(None)

    def test_empty_string_is_not_retryable(self):
        assert not _StubAdapter._is_retryable_error("")


    def test_permission_error_not_retryable(self):
        assert not _StubAdapter._is_retryable_error("Forbidden: bot was blocked by the user")


# ---------------------------------------------------------------------------
# _is_timeout_error
# ---------------------------------------------------------------------------

class TestIsTimeoutError:
    def test_none_is_not_timeout(self):
        assert not _StubAdapter._is_timeout_error(None)

    def test_empty_is_not_timeout(self):
        assert not _StubAdapter._is_timeout_error("")


# ---------------------------------------------------------------------------
# _send_with_retry — success on first attempt
# ---------------------------------------------------------------------------

class TestSendWithRetrySuccess:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        adapter = _StubAdapter()
        adapter._send_results = [SendResult(success=True, message_id="123")]
        result = await adapter._send_with_retry("chat1", "hello")
        assert result.success
        assert len(adapter._send_calls) == 1


# ---------------------------------------------------------------------------
# _send_with_retry — network error with successful retry
# ---------------------------------------------------------------------------

class TestSendWithRetryNetworkRetry:
    @pytest.mark.asyncio
    async def test_retries_on_connect_error_and_succeeds(self):
        adapter = _StubAdapter()
        adapter._send_results = [
            SendResult(success=False, error="httpx.ConnectError: connection refused"),
            SendResult(success=True, message_id="ok"),
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter._send_with_retry("chat1", "hello", max_retries=2, base_delay=0)
        assert result.success
        assert len(adapter._send_calls) == 2  # initial + 1 retry

    @pytest.mark.asyncio
    async def test_timeout_not_retried_to_prevent_duplicates(self):
        """ReadTimeout is NOT retried because the request may have reached
        the server — retrying a non-idempotent send risks duplicate delivery.
        It also skips plain-text fallback (timeout is not a formatting issue)."""
        adapter = _StubAdapter()
        adapter._send_results = [
            SendResult(success=False, error="ReadTimeout: request timed out"),
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await adapter._send_with_retry("chat1", "hello", max_retries=3, base_delay=0)
        # No retry, no fallback — timeout returns failure immediately
        mock_sleep.assert_not_called()
        assert not result.success
        assert len(adapter._send_calls) == 1


# ---------------------------------------------------------------------------
# _send_with_retry — all retries exhausted → user notification
# ---------------------------------------------------------------------------

class TestSendWithRetryExhausted:
    @pytest.mark.asyncio
    async def test_sends_user_notice_after_exhaustion(self):
        adapter = _StubAdapter()
        network_err = SendResult(success=False, error="httpx.ConnectError: host unreachable")
        # initial + 2 retries + notice attempt
        adapter._send_results = [network_err, network_err, network_err, SendResult(success=True)]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter._send_with_retry("chat1", "hello", max_retries=2, base_delay=0)
        # Result is the last failed one (before notice)
        assert not result.success
        # 4 total calls: 1 initial + 2 retries + 1 notice
        assert len(adapter._send_calls) == 4
        # The notice content should mention delivery failure
        notice_content = adapter._send_calls[-1][1]
        assert "delivery failed" in notice_content.lower() or "Message delivery failed" in notice_content


# ---------------------------------------------------------------------------
# _send_with_retry — non-network failure → plain-text fallback (no retry)
# ---------------------------------------------------------------------------

class TestSendWithRetryFallback:
    @pytest.mark.asyncio
    async def test_non_network_error_falls_back_immediately(self):
        adapter = _StubAdapter()
        adapter._send_results = [
            SendResult(success=False, error="Bad Request: can't parse entities"),
            SendResult(success=True, message_id="fallback_ok"),
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await adapter._send_with_retry("chat1", "**bold**", max_retries=2, base_delay=0)
        # No sleep — no retry loop for non-network errors
        mock_sleep.assert_not_called()
        assert result.success
        assert len(adapter._send_calls) == 2
        # Fallback content should be plain-text notice
        assert "plain text" in adapter._send_calls[1][1].lower()


# ---------------------------------------------------------------------------
# _send_with_retry — retry_after honor
# ---------------------------------------------------------------------------

class TestSendWithRetryAfter:
    @pytest.mark.asyncio
    async def test_retry_after_honored_on_first_retry(self):
        """When the initial result has retry_after, the first retry waits that long."""
        adapter = _StubAdapter()
        adapter._send_results = [
            SendResult(success=False, error="Flood control exceeded. Retry in 37 seconds",
                       retryable=True, retry_after=37.0),
            SendResult(success=True, message_id="ok"),
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await adapter._send_with_retry("chat1", "hello", max_retries=2, base_delay=2.0)
        assert result.success
        # First sleep should use retry_after (~37s + jitter), not base_delay (~2s)
        first_sleep = mock_sleep.call_args_list[0][0][0]
        assert first_sleep >= 36.0  # 37 - 1 (max jitter)

    @pytest.mark.asyncio
    async def test_retry_after_from_subsequent_result(self):
        """If a retry itself returns retry_after, the next retry honors it."""
        adapter = _StubAdapter()
        adapter._send_results = [
            SendResult(success=False, error="ConnectError", retryable=True),
            SendResult(success=False, error="Flood control exceeded. Retry in 30 seconds",
                       retryable=True, retry_after=30.0),
            SendResult(success=True, message_id="ok"),
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await adapter._send_with_retry("chat1", "hello", max_retries=3, base_delay=2.0)
        assert result.success
        # Second sleep should use the retry_after from the second result
        second_sleep = mock_sleep.call_args_list[1][0][0]
        assert second_sleep >= 29.0  # 30 - 1 (max jitter)


# ---------------------------------------------------------------------------
# _send_with_retry — flood result with retry_after but retryable=False
# ---------------------------------------------------------------------------

class TestSendWithRetryFloodCap:
    """Regression: the Telegram adapter's ``_flood_cap_result`` returns a
    SendResult carrying ``retry_after`` (the server's FloodWait) but does NOT
    set ``retryable=True``. ``_send_with_retry`` must still honor that
    server-requested ``retry_after`` by backing off and retrying, instead of
    falling straight through to an immediate plain-text fallback send that
    re-hits the same flood ban (renewing it) while the bot is rate-limited.
    """

    @pytest.mark.asyncio
    async def test_retry_after_honored_when_retryable_false(self):
        adapter = _StubAdapter()
        # First result mirrors _flood_cap_result(wait=30): retry_after set,
        # retryable left False. A plain-text fallback would be a wasteful second
        # trip into the ban; the correct behaviour is to back off ~retry_after
        # and retry the SAME content.
        adapter._send_results = [
            SendResult(success=False, error="flood_control:30.0", retry_after=30.0),
            SendResult(success=True, message_id="ok"),
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await adapter._send_with_retry("chat1", "hello", max_retries=2, base_delay=2.0)
        assert result.success
        # Exactly one retry happened (no plain-text fallback): 2 sends total.
        assert len(adapter._send_calls) == 2
        # The retry kept the ORIGINAL content (not the "(Response formatting failed…)" fallback).
        assert adapter._send_calls[1][1] == "hello"
        # The sleep honored the server retry_after (~30s), not base_delay (~2s).
        first_sleep = mock_sleep.call_args_list[0][0][0]
        assert first_sleep >= 29.0  # 30 - 1 (max jitter)

    @pytest.mark.asyncio
    async def test_flood_on_retry_keeps_backing_off(self):
        """A flood result that comes back ON a retry attempt (retryable=False,
        retry_after set) must keep the retry loop going with the new backoff,
        not break out to the plain-text fallback (which would re-hit the ban).
        """
        adapter = _StubAdapter()
        adapter._send_results = [
            SendResult(success=False, error="flood_control:20.0", retry_after=20.0),
            # The retry itself is also flood-capped (ban still active).
            SendResult(success=False, error="flood_control:10.0", retry_after=10.0),
            SendResult(success=True, message_id="ok"),
        ]
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await adapter._send_with_retry("chat1", "hello", max_retries=3, base_delay=2.0)
        assert result.success
        # 3 sends total: initial + 2 retries. No plain-text fallback.
        assert len(adapter._send_calls) == 3
        assert all(call[1] == "hello" for call in adapter._send_calls)
        # Both sleeps honored the server retry_after values, not base_delay.
        sleeps = [c[0][0] for c in mock_sleep.call_args_list]
        assert len(sleeps) == 2
        assert sleeps[0] >= 19.0  # 20 - 1 (max jitter)
        assert sleeps[1] >= 9.0   # 10 - 1 (max jitter)

"""Rich-only Telegram messages must enter the normal authenticated text path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform, PlatformConfig


def _make_adapter():
    from plugins.platforms.telegram.adapter import TelegramAdapter

    adapter = object.__new__(TelegramAdapter)
    adapter._platform = Platform.TELEGRAM
    adapter.platform = Platform.TELEGRAM
    adapter.config = PlatformConfig(enabled=True, token="test-token")
    adapter._running = True
    adapter._pending_text_batches = {}
    adapter._pending_text_batch_tasks = {}
    adapter._pending_photo_batches = {}
    adapter._pending_photo_batch_tasks = {}
    adapter._media_group_events = {}
    adapter._media_group_tasks = {}
    adapter._text_batch_delay_seconds = 0.1
    adapter._active_sessions = {}
    adapter._pending_messages = {}
    adapter._held_inbound_events = []
    adapter.HELD_INBOUND_MAX = 64
    adapter.handle_message = AsyncMock()
    return adapter


def _rich_update(text: str = "rich content", *, with_text: bool = False):
    blocks = [{"type": "paragraph", "text": [{"type": "plain", "text": text}]}]
    msg = SimpleNamespace(
        text=text if with_text else None,
        caption=None,
        api_kwargs={"rich_message": {"blocks": blocks}},
        chat=SimpleNamespace(id=1, type="private", title=None),
        from_user=SimpleNamespace(id=1, full_name="T", is_bot=False),
        message_id=10,
        date=None,
    )
    return SimpleNamespace(update_id=1, message=msg)


@pytest.mark.asyncio
async def test_rich_only_message_recovered_as_text(monkeypatch):
    adapter = _make_adapter()
    monkeypatch.setattr(adapter, "_is_user_authorized_from_message", lambda _m: True)
    monkeypatch.setattr(adapter, "_should_process_message", lambda _m, **_k: True)
    monkeypatch.setattr(adapter, "_ensure_forum_commands", AsyncMock())
    monkeypatch.setattr(adapter, "_cache_replied_media", AsyncMock())
    monkeypatch.setattr(
        adapter, "_apply_telegram_group_observe_attribution", lambda event: event
    )
    monkeypatch.setattr(adapter, "_clean_bot_trigger_text", lambda text: text)
    monkeypatch.setattr(
        adapter,
        "_build_message_event",
        lambda _msg, _type, update_id=None: SimpleNamespace(text=""),
    )
    enqueued = []
    monkeypatch.setattr(adapter, "_enqueue_text_event", enqueued.append)

    await adapter._handle_rich_only_message(_rich_update(), context=None)

    assert len(enqueued) == 1
    assert enqueued[0].text == "rich content"


@pytest.mark.asyncio
async def test_plain_message_is_not_double_enqueued(monkeypatch):
    adapter = _make_adapter()
    enqueued = []
    monkeypatch.setattr(adapter, "_enqueue_text_event", enqueued.append)

    await adapter._handle_rich_only_message(
        _rich_update(with_text=True), context=None
    )

    assert enqueued == []

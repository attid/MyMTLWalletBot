"""Tests for Redis-backed pending-notification keyboard badges."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, create_autospec

import fakeredis.aioredis
import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

from infrastructure.services.notification_badge_service import (
    NotificationBadgeService,
    UiMarkupLockUnavailable,
)
from infrastructure.services.notification_redis_store import NotificationRedisStore
from infrastructure.utils.telegram_utils import send_message


@pytest.fixture
async def badge_service():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    bot = create_autospec(Bot, instance=True, spec_set=True)
    service = NotificationBadgeService(bot=bot, redis=redis, store=store)
    yield service, store, bot
    await redis.aclose()


@pytest.mark.asyncio
async def test_refresh_appends_singular_badge_without_storing_it_as_base(badge_service):
    service, store, bot = badge_service
    base = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data="Return")]]
    )
    await service.capture_base_markup(42, 7, base)
    await store.enqueue(42, _notification(42, "one"))

    await service.refresh(42)

    markup = bot.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[-1][0].text == "🔔 1 pending notification"
    assert markup.inline_keyboard[-1][0].callback_data == "notification_pending:flush"
    stored = await service.get_base_markup(42)
    assert stored is not None
    assert stored.reply_markup == base


@pytest.mark.asyncio
async def test_refresh_restores_base_and_never_duplicates_badge(badge_service):
    service, store, bot = badge_service
    base = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Menu", callback_data="menu")]]
    )
    await service.capture_base_markup(42, 9, base)
    await store.enqueue(42, _notification(42, "one"))
    await store.enqueue(42, _notification(42, "two"))

    await service.refresh(42)
    await service.refresh(42)
    second_markup = bot.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    assert len(second_markup.inline_keyboard) == 2
    assert second_markup.inline_keyboard[-1][0].text == "🔔 2 pending notifications"

    await store.acknowledge(42, _notification(42, "one"))
    await store.acknowledge(42, _notification(42, "two"))
    await service.refresh(42)
    restored = bot.edit_message_reply_markup.await_args.kwargs["reply_markup"]
    assert restored == base


@pytest.mark.asyncio
async def test_capture_clears_base_when_current_screen_has_no_inline_keyboard(
    badge_service,
):
    service, _, _ = badge_service
    base = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Menu", callback_data="menu")]]
    )
    await service.capture_base_markup(42, 9, base)

    await service.capture_base_markup(42, 10, None)

    assert await service.get_base_markup(42) is None


@pytest.mark.asyncio
async def test_capture_never_persists_a_derived_badge_as_base(badge_service):
    service, _, _ = badge_service
    markup_with_badge = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Menu", callback_data="menu")],
            [
                InlineKeyboardButton(
                    text="🔔 2 pending notifications",
                    callback_data="notification_pending:flush",
                )
            ],
        ]
    )

    await service.capture_base_markup(42, 9, markup_with_badge)

    base = await service.get_base_markup(42)
    assert base is not None
    assert base.reply_markup.inline_keyboard == [
        [InlineKeyboardButton(text="Menu", callback_data="menu")]
    ]


@pytest.mark.asyncio
async def test_failed_markup_edit_is_nonfatal(badge_service):
    service, store, bot = badge_service
    bot.edit_message_reply_markup = AsyncMock(side_effect=RuntimeError("gone"))
    await service.capture_base_markup(
        42,
        7,
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Menu", callback_data="menu")]]
        ),
    )
    await store.enqueue(42, _notification(42, "one"))

    await service.refresh(42)

    assert await service.get_base_markup(42) is not None


@pytest.mark.asyncio
async def test_identical_markup_response_is_logged_as_a_debug_noop(badge_service):
    service, store, bot = badge_service
    bot.edit_message_reply_markup = AsyncMock(
        side_effect=TelegramBadRequest(
            method=MagicMock(),
            message="Bad Request: message is not modified: specified new message "
            "content and reply markup are exactly the same",
        )
    )
    await service.capture_base_markup(
        42,
        7,
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Menu", callback_data="menu")]]
        ),
    )
    await store.enqueue(42, _notification(42, "one"))
    records = []
    sink_id = logger.add(lambda message: records.append(message.record), level="DEBUG")
    try:
        await service.refresh(42)
    finally:
        logger.remove(sink_id)

    events = [record["extra"].get("event") for record in records]
    assert "notification_badge_already_current" in events
    assert "notification_badge_edit_failed" not in events


@pytest.mark.asyncio
async def test_ui_render_waits_for_refresh_before_replacing_its_base_markup(
    badge_service,
) -> None:
    """A stale refresh must finish before a newer UI render installs its base."""
    service, store, bot = badge_service
    bot.id = 1
    old_base = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Old", callback_data="old")]]
    )
    new_base = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="New", callback_data="new")]]
    )
    await service.capture_base_markup(42, 7, old_base)
    await store.enqueue(42, _notification(42, "one"))

    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()
    final_markup: InlineKeyboardMarkup | None = None

    async def block_stale_refresh(**kwargs):
        refresh_started.set()
        await release_refresh.wait()

    async def record_new_render(**kwargs):
        nonlocal final_markup
        final_markup = kwargs["reply_markup"]

    bot.edit_message_reply_markup = AsyncMock(side_effect=block_stale_refresh)
    bot.edit_message_text = AsyncMock(side_effect=record_new_render)
    dispatcher = Dispatcher(storage=MemoryStorage())
    app_context = MagicMock(bot=bot, dispatcher=dispatcher)
    app_context.notification_badge_service = service
    await dispatcher.storage.update_data(
        key=StorageKey(bot_id=1, chat_id=42, user_id=42),
        data={"last_message_id": 7},
    )

    refresh_task = asyncio.create_task(service.refresh(42))
    await refresh_started.wait()
    render_task = asyncio.create_task(
        send_message(
            None, 42, "new screen", reply_markup=new_base, app_context=app_context
        )
    )
    await asyncio.sleep(0)
    assert not render_task.done()

    release_refresh.set()
    await asyncio.gather(refresh_task, render_task)

    stored = await service.get_base_markup(42)
    assert stored is not None
    assert stored.message_id == 7
    assert stored.reply_markup == new_base
    assert final_markup is not None
    assert final_markup.inline_keyboard == [
        [InlineKeyboardButton(text="New", callback_data="new")],
        [
            InlineKeyboardButton(
                text="🔔 1 pending notification",
                callback_data="notification_pending:flush",
            )
        ],
    ]


@pytest.mark.asyncio
async def test_refresh_does_not_mutate_telegram_when_its_lease_is_already_lost(
    badge_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale refresher must not edit markup after losing ownership."""
    service, store, bot = badge_service
    await service.capture_base_markup(
        42,
        7,
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Menu", callback_data="menu")]]
        ),
    )
    await store.enqueue(42, _notification(42, "one"))
    lease_lost = asyncio.Event()
    lease_lost.set()

    @asynccontextmanager
    async def lost_lock(_user_id: int):
        yield lease_lost

    monkeypatch.setattr(service, "ui_markup_lock", lost_lock)

    await service.refresh(42)

    bot.edit_message_reply_markup.assert_not_awaited()


@pytest.mark.asyncio
async def test_ui_render_does_not_mutate_telegram_when_its_lease_is_already_lost(
    badge_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale renderer must not edit text after losing ownership."""
    service, _, bot = badge_service
    bot.id = 1
    lease_lost = asyncio.Event()
    lease_lost.set()

    @asynccontextmanager
    async def lost_lock(_user_id: int):
        yield lease_lost

    monkeypatch.setattr(service, "ui_markup_lock", lost_lock)
    dispatcher = Dispatcher(storage=MemoryStorage())
    app_context = MagicMock(bot=bot, dispatcher=dispatcher)
    app_context.notification_badge_service = service
    await dispatcher.storage.update_data(
        key=StorageKey(bot_id=1, chat_id=42, user_id=42),
        data={"last_message_id": 7},
    )

    await send_message(
        None,
        42,
        "stale screen",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Stale", callback_data="stale")]
            ]
        ),
        app_context=app_context,
    )

    bot.edit_message_text.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_ui_render_falls_back_without_badge_when_markup_lock_is_busy(
    badge_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Badge contention is cosmetic and must not fail a user-facing render."""
    service, _, bot = badge_service
    bot.id = 1
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=8))

    @asynccontextmanager
    async def unavailable_lock(_user_id: int):
        raise UiMarkupLockUnavailable("busy")
        yield

    monkeypatch.setattr(service, "ui_markup_lock", unavailable_lock)
    dispatcher = Dispatcher(storage=MemoryStorage())
    app_context = MagicMock(bot=bot, dispatcher=dispatcher)
    app_context.notification_badge_service = service
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Menu", callback_data="menu")]]
    )

    await send_message(None, 42, "screen", reply_markup=markup, app_context=app_context)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["reply_markup"] == markup
    data = await dispatcher.storage.get_data(
        StorageKey(bot_id=1, chat_id=42, user_id=42)
    )
    assert data["last_message_id"] == 8


@pytest.mark.asyncio
async def test_ui_render_cancels_after_lease_loss_without_overwriting_newer_base(
    badge_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A render blocked in Telegram must stop before its stale base is captured."""
    service, _, bot = badge_service
    bot.id = 1
    stale_base = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Stale", callback_data="stale")]]
    )
    newer_base = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="New", callback_data="new")]]
    )
    lease_lost = asyncio.Event()
    telegram_started = asyncio.Event()
    telegram_cancelled = asyncio.Event()

    @asynccontextmanager
    async def lease_lock(_user_id: int):
        yield lease_lost

    async def block_telegram_edit(**_kwargs) -> None:
        telegram_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            telegram_cancelled.set()
            raise

    monkeypatch.setattr(service, "ui_markup_lock", lease_lock)
    bot.edit_message_text = AsyncMock(side_effect=block_telegram_edit)
    dispatcher = Dispatcher(storage=MemoryStorage())
    app_context = MagicMock(bot=bot, dispatcher=dispatcher)
    app_context.notification_badge_service = service
    await dispatcher.storage.update_data(
        key=StorageKey(bot_id=1, chat_id=42, user_id=42),
        data={"last_message_id": 7},
    )

    render_task = asyncio.create_task(
        send_message(
            None, 42, "stale screen", reply_markup=stale_base, app_context=app_context
        )
    )
    await telegram_started.wait()
    lease_lost.set()
    await service.capture_base_markup_locked(42, 7, newer_base)

    await asyncio.wait_for(render_task, timeout=0.2)

    assert telegram_cancelled.is_set()
    stored = await service.get_base_markup(42)
    assert stored is not None
    assert stored.reply_markup == newer_base


def _notification(user_id: int, suffix: str):
    from core.models.blockchain_notification import BlockchainNotification

    return BlockchainNotification(
        notification_id=f"notification-{suffix}",
        user_id=user_id,
        event_type="payment",
        text="Pending",
        created_at=1,
        transaction_hash=f"transaction-{suffix}",
        event_index=0,
    )

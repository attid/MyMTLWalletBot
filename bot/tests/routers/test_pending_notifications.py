"""Router tests for the pending-notification badge callback."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Dispatcher
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from conftest import RouterTestMiddleware, create_callback_update, get_telegram_request
from middleware.old_buttons import CheckOldButtonCallbackMiddleware
from routers.pending_notifications import router


class ActiveFlow(StatesGroup):
    waiting_for_amount = State()


@pytest.mark.asyncio
async def test_badge_click_flushes_without_mutating_active_fsm_or_ui_tracking(
    mock_telegram, router_app_context
):
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    dispatcher.include_router(deepcopy(router))
    router_app_context.dispatcher = dispatcher
    router_app_context.notification_coordinator = AsyncMock()
    key = StorageKey(bot_id=router_app_context.bot.id, chat_id=42, user_id=42)
    data = {"last_message_id": 7, "active_flow": "send"}
    await storage.set_data(key, data)
    await storage.set_state(key, ActiveFlow.waiting_for_amount.state)

    await dispatcher.feed_update(
        router_app_context.bot,
        create_callback_update(42, "notification_pending:flush"),
        app_context=router_app_context,
    )

    router_app_context.notification_coordinator.flush.assert_awaited_once_with(
        42, ignore_hold=True, reason="manual_badge_click"
    )
    assert await storage.get_data(key) == data
    assert await storage.get_state(key) == ActiveFlow.waiting_for_amount.state
    assert get_telegram_request(mock_telegram, "answerCallbackQuery") is not None


@pytest.mark.asyncio
async def test_badge_callback_answers_before_flush_failure_and_preserves_fsm(
    mock_telegram, router_app_context
) -> None:
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    dispatcher.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dispatcher.include_router(deepcopy(router))
    router_app_context.dispatcher = dispatcher
    key = StorageKey(bot_id=router_app_context.bot.id, chat_id=42, user_id=42)
    data = {"last_message_id": 7, "active_flow": "send"}
    await storage.set_data(key, data)
    await storage.set_state(key, ActiveFlow.waiting_for_amount.state)

    async def failing_flush(*args, **kwargs) -> None:
        assert get_telegram_request(mock_telegram, "answerCallbackQuery") is not None
        raise RuntimeError("redis unavailable")

    router_app_context.notification_coordinator = MagicMock()
    router_app_context.notification_coordinator.flush = AsyncMock(
        side_effect=failing_flush
    )

    await dispatcher.feed_update(
        router_app_context.bot,
        create_callback_update(42, "notification_pending:flush", message_id=7),
    )

    assert await storage.get_data(key) == data
    assert await storage.get_state(key) == ActiveFlow.waiting_for_amount.state
    assert get_telegram_request(mock_telegram, "answerCallbackQuery") is not None


@pytest.mark.asyncio
async def test_old_button_middleware_accepts_current_badge_and_rejects_stale_badge(
    mock_telegram, router_app_context
) -> None:
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    dispatcher.callback_query.middleware(CheckOldButtonCallbackMiddleware(MagicMock()))
    dispatcher.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dispatcher.include_router(deepcopy(router))
    router_app_context.dispatcher = dispatcher
    router_app_context.notification_coordinator = MagicMock()
    router_app_context.notification_coordinator.flush = AsyncMock()
    key = StorageKey(bot_id=router_app_context.bot.id, chat_id=42, user_id=42)
    await storage.set_data(key, {"last_message_id": 7})

    await dispatcher.feed_update(
        router_app_context.bot,
        create_callback_update(42, "notification_pending:flush", message_id=7),
    )
    router_app_context.notification_coordinator.flush.assert_awaited_once_with(
        42, ignore_hold=True, reason="manual_badge_click"
    )

    router_app_context.notification_coordinator.flush.reset_mock()
    await dispatcher.feed_update(
        router_app_context.bot,
        create_callback_update(
            42, "notification_pending:flush", update_id=2, message_id=6
        ),
    )

    router_app_context.notification_coordinator.flush.assert_not_awaited()
    stale_answer = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert stale_answer is not None
    assert stale_answer["data"]["show_alert"] == "true"
    assert get_telegram_request(mock_telegram, "editMessageReplyMarkup") is not None

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Chat, Message, User
from routers.common_setting import LangCallbackData
from routers.wallet_setting import (
    AddressBookCallbackData,
    AssetVisibilityCallbackData,
    MDCallbackData,
)

from middleware.notification_activity import (
    NotificationActivityMiddleware,
    should_touch_callback,
)
from keyboards.common_keyboards import get_notification_keyboard


def callback(data: str) -> CallbackQuery:
    user = User(id=42, is_bot=False, first_name="Test")
    message = Message(
        message_id=1,
        date=0,
        chat=Chat(id=42, type="private"),
        from_user=user,
        text="menu",
    )
    return CallbackQuery(
        id="callback", from_user=user, chat_instance="chat", data=data, message=message
    )


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("Send", True),
        ("Market", True),
        ("NewOrder", True),
        ("WalletSetting", True),
        ("send_asset_:XLM", True),
        ("SaleAssetCallbackData:XLM", True),
        ("EditOrderCallbackData:42", True),
        ("AddressBookCallbackData:edit:1", True),
        (AssetVisibilityCallbackData(action="page").pack(), True),
        (AddressBookCallbackData(action="edit", idx=1).pack(), True),
        (MDCallbackData(uuid_callback="abc").pack(), True),
        (LangCallbackData(action="en").pack(), True),
        ("NotificationSettings", True),
        ("notif_menu:list:0", True),
        ("notif_filter:info:1", True),
        ("create_filter_from:abc123", True),
        ("add_filter_menu", True),
        ("toggle_token_notify", True),
        ("change_amount", True),
        ("toggle_wallets_notify", True),
        ("SealedBoxMenu", True),
        ("SealedBoxEncrypt", True),
        ("SealedBoxDecrypt", True),
        ("SealedBoxRecipient:7", True),
        ("save_filter", False),
        ("notification_pending:flush", False),
        ("Return", False),
        ("FlowBack", False),
        ("DeleteReturn", False),
        ("Yes_send_xdr", True),
        ("cancel_biometric_sign:tx", False),
    ],
)
def test_should_touch_callback_classifies_interactive_flow_controls(data, expected):
    assert should_touch_callback(data) is expected


def test_flow_back_touches_only_with_an_active_fsm():
    assert should_touch_callback("FlowBack") is False
    assert should_touch_callback("FlowBack", fsm_active=True) is True


def test_notification_keyboard_remains_isolated_from_flow_back():
    keyboard = get_notification_keyboard(
        42, localization_service=MagicMock(get_text=lambda *_: "text")
    )

    assert [
        button.callback_data for row in keyboard.inline_keyboard for button in row
    ] == [
        "NotificationSettings",
        "Return",
    ]


@pytest.mark.asyncio
async def test_callback_in_interactive_flow_touches_coordinator():
    coordinator = MagicMock(touch=AsyncMock())
    middleware = NotificationActivityMiddleware()
    handler = AsyncMock()

    await middleware(
        handler,
        callback("NewOrder"),
        {"app_context": MagicMock(notification_coordinator=coordinator)},
    )

    coordinator.touch.assert_awaited_once_with(42)
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_fsm_message_touches_coordinator():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=42, user_id=42)
    await storage.set_state(key, "StateSaleToken:editing_amount")
    state = FSMContext(storage=storage, key=key)
    coordinator = MagicMock(touch=AsyncMock())
    event = callback("ignored").message
    assert event is not None

    await NotificationActivityMiddleware()(
        AsyncMock(),
        event,
        {
            "state": state,
            "app_context": MagicMock(notification_coordinator=coordinator),
        },
    )

    coordinator.touch.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_start_command_does_not_touch_while_fsm_is_active():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=42, user_id=42)
    await storage.set_state(key, "StateSendToken:sending_sum")
    state = FSMContext(storage=storage, key=key)
    coordinator = MagicMock(touch=AsyncMock())
    event = callback("ignored").message.model_copy(update={"text": "/start"})

    await NotificationActivityMiddleware()(
        AsyncMock(),
        event,
        {
            "state": state,
            "app_context": MagicMock(notification_coordinator=coordinator),
        },
    )

    coordinator.touch.assert_not_awaited()


@pytest.mark.asyncio
async def test_inactive_fsm_message_does_not_touch_coordinator():
    coordinator = MagicMock(touch=AsyncMock())
    event = callback("ignored").message
    assert event is not None

    await NotificationActivityMiddleware()(
        AsyncMock(),
        event,
        {"app_context": MagicMock(notification_coordinator=coordinator)},
    )

    coordinator.touch.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_handler_transitioning_to_active_fsm_touches_coordinator_once():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=42, user_id=42)
    state = FSMContext(storage=storage, key=key)
    coordinator = MagicMock(touch=AsyncMock())
    event = callback("ignored").message
    assert event is not None

    async def activate_flow(*_args, **_kwargs):
        await state.set_state("StateSendToken:sending_for")

    await NotificationActivityMiddleware()(
        activate_flow,
        event,
        {
            "state": state,
            "app_context": MagicMock(notification_coordinator=coordinator),
        },
    )

    coordinator.touch.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_message_handler_without_fsm_transition_does_not_touch_coordinator():
    coordinator = MagicMock(touch=AsyncMock())
    event = callback("ignored").message.model_copy(update={"text": "/unknown"})
    assert event is not None

    await NotificationActivityMiddleware()(
        AsyncMock(),
        event,
        {"app_context": MagicMock(notification_coordinator=coordinator)},
    )

    coordinator.touch.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminal_and_badge_callbacks_do_not_touch_even_with_active_fsm():
    coordinator = MagicMock(touch=AsyncMock())
    handler = AsyncMock()
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=42, user_id=42)
    await storage.set_state(key, "StateSendToken:sending_sum")
    state = FSMContext(storage=storage, key=key)

    await NotificationActivityMiddleware()(
        handler,
        callback("SendTr"),
        {
            "state": state,
            "app_context": MagicMock(notification_coordinator=coordinator),
        },
    )

    coordinator.touch.assert_not_awaited()
    handler.assert_awaited_once()

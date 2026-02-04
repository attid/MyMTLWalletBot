
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.storage.base import StorageKey

from routers.ton import (
    router as ton_router,
    StateSendTon,
    StateSendTonUSDT,
)
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if ton_router.parent_router:
        ton_router._parent_router = None

@pytest.fixture
def setup_ton_mocks(router_app_context):
    """
    Common mock setup for TON router tests.
    """
    class TonMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default secret service mock
            self.secret_service = AsyncMock()
            self.secret_service.is_ton_wallet.return_value = True
            self.secret_service.get_ton_mnemonic.return_value = "test mnemonic"
            self.ctx.use_case_factory.create_wallet_secret_service.return_value = self.secret_service

            # Default ton service mock
            self.ton_service = MagicMock()
            self.ton_service.from_mnemonic = MagicMock()
            self.ton_service.send_ton = AsyncMock(return_value=True)
            self.ton_service.send_usdt = AsyncMock(return_value=True)
            self.ctx.ton_service = self.ton_service

    return TonMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')]
    return msgs[-1] if msgs else None


@pytest.mark.asyncio
async def test_send_ton_full_flow_success(mock_telegram, router_app_context, setup_ton_mocks):
    """Test full flow of sending TON: Start -> Address -> Sum -> Confirm."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(ton_router)

    user_id = 123
    bot = router_app_context.bot
    state_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)

    # 1. Start TON sending
    await dp.feed_update(bot, create_callback_update(user_id, "SendTon"))
    assert await dp.storage.get_state(state_key) == StateSendTon.sending_for
    req = get_latest_msg(mock_telegram)
    assert "Enter recipient's address" in req["data"]["text"]

    # 2. Enter Address
    valid_address = "EQD" + ("A" * 45)
    await dp.feed_update(bot, create_message_update(user_id, valid_address, message_id=2, update_id=2))
    assert await dp.storage.get_state(state_key) == StateSendTon.sending_sum
    req = get_latest_msg(mock_telegram)
    assert "Enter amount to send" in req["data"]["text"]

    # 3. Enter Sum
    await dp.feed_update(bot, create_message_update(user_id, "1.5", message_id=3, update_id=3))
    assert await dp.storage.get_state(state_key) == StateSendTon.sending_confirmation
    req = get_latest_msg(mock_telegram)
    assert "confirm sending 1.5 TON" in req["data"]["text"]

    # 4. Confirm (Yes)
    await dp.feed_update(bot, create_callback_update(user_id, "ton_yes", update_id=4))
    
    # Verify ton_service calls
    setup_ton_mocks.ton_service.send_ton.assert_called_once_with(valid_address, 1.5)
    
    # Verify success message
    all_texts = " ".join([m["data"].get("text", "") + m["data"].get("caption", "") for m in mock_telegram if m['method'] in ('sendMessage', 'editMessageText')])
    assert "Successfully sent 1.5 TON" in all_texts
    
    # State should be cleared (thanks to our fix)
    assert await dp.storage.get_state(state_key) is None


@pytest.mark.asyncio
async def test_send_ton_usdt_full_flow_success(mock_telegram, router_app_context, setup_ton_mocks):
    """Test full flow of sending USDT on TON."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(ton_router)

    user_id = 123
    bot = router_app_context.bot
    state_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)

    # 1. Start USDT
    await dp.feed_update(bot, create_callback_update(user_id, "SendTonUSDt"))
    assert await dp.storage.get_state(state_key) == StateSendTonUSDT.sending_for

    # 2. Address
    valid_address = "EQD" + ("B" * 45)
    await dp.feed_update(bot, create_message_update(user_id, valid_address, message_id=2, update_id=2))
    assert await dp.storage.get_state(state_key) == StateSendTonUSDT.sending_sum

    # 3. Sum
    await dp.feed_update(bot, create_message_update(user_id, "10.0", message_id=3, update_id=3))
    assert await dp.storage.get_state(state_key) == StateSendTonUSDT.sending_confirmation

    # 4. Confirm
    await dp.feed_update(bot, create_callback_update(user_id, "ton_yes", update_id=4))
    
    setup_ton_mocks.ton_service.send_usdt.assert_called_once_with(valid_address, 10.0)
    all_texts = " ".join([m["data"].get("text", "") for m in mock_telegram if m['method'] in ('sendMessage', 'editMessageText')])
    assert "Successfully sent 10.0 USDT" in all_texts
    assert await dp.storage.get_state(state_key) is None


@pytest.mark.asyncio
async def test_send_ton_cancel(mock_telegram, router_app_context, setup_ton_mocks):
    """Test cancelling TON transaction."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(ton_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    
    await dp.storage.set_state(state_key, StateSendTon.sending_confirmation)
    
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "ton_no"))
    
    req = get_latest_msg(mock_telegram)
    assert "Transaction cancelled" in req["data"]["text"]
    assert await dp.storage.get_state(state_key) is None


@pytest.mark.asyncio
async def test_send_ton_invalid_address(mock_telegram, router_app_context, setup_ton_mocks):
    """Test entering invalid TON address."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(ton_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(state_key, StateSendTon.sending_for)

    await dp.feed_update(router_app_context.bot, create_message_update(user_id, "short_address"))
    
    req = get_latest_msg(mock_telegram)
    assert "Invalid address" in req["data"]["text"]
    # Should stay in same state
    assert await dp.storage.get_state(state_key) == StateSendTon.sending_for

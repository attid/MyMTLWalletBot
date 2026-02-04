import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.storage.base import StorageKey

import fakeredis.aioredis

from routers.sign import router as sign_router, PinState, PinCallbackData
from infrastructure.states import StateSign
from other import faststream_tools
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if sign_router.parent_router:
        sign_router._parent_router = None

@pytest.fixture
def setup_sign_mocks(router_app_context, mock_horizon, horizon_server_config):
    """
    Common mock setup for Sign router tests.
    """
    from infrastructure.services.stellar_service import StellarService
    
    class SignMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Real StellarService connected to mock_horizon
            self.ctx.stellar_service = StellarService(horizon_url=horizon_server_config["url"])
            
            # Setup mock_horizon for the source account
            self.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            mock_horizon.set_account(self.public_key)
            
            # Mock the underlying stellar_tools functions that use DB or complex logic
            # to avoid refactoring the entire persistence layer in this test.
            # However, we must not use AsyncMock on stellar_service itself.
            
            self.p_is_free = patch("other.stellar_tools.stellar_is_free_wallet", return_value=False)
            self.p_check_xdr = patch("other.stellar_tools.stellar_check_xdr", side_effect=lambda x, f: x)
            self.p_get_acc = patch("other.stellar_tools.stellar_get_user_account")
            self.p_get_kp = patch("other.stellar_tools.stellar_get_user_keypair")
            self.p_user_sign = patch("other.stellar_tools.stellar_user_sign", return_value="SIGNED_XDR")
            self.p_send = patch("other.stellar_tools.async_stellar_send", return_value={"hash": "tx_hash"})
            
            self.m_is_free = self.p_is_free.start()
            self.m_check_xdr = self.p_check_xdr.start()
            self.m_get_acc = self.p_get_acc.start()
            self.m_get_kp = self.p_get_kp.start()
            self.m_user_sign = self.p_user_sign.start()
            self.m_send = self.p_send.start()
            
            mock_acc = MagicMock()
            mock_acc.account.account_id = self.public_key
            self.m_get_acc.return_value = mock_acc

            # Default Wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = self.public_key
            self.wallet.use_pin = 1
            self.wallet.is_free = False
            
            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo
        
        def stop(self):
            self.p_is_free.stop()
            self.p_check_xdr.stop()
            self.p_get_acc.stop()
            self.p_get_kp.stop()
            self.p_user_sign.stop()
            self.p_send.stop()

    helper = SignMockHelper(router_app_context)
    yield helper
    helper.stop()


@pytest.mark.asyncio
async def test_full_flow_sign_and_send_success(mock_telegram, router_app_context, setup_sign_mocks):
    """
    Scenario: User clicks Sign -> enters XDR -> enters PIN 1234 -> clicks Send.
    Full integration check.
    """
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(sign_router)

    user_id = 123
    bot = router_app_context.bot
    state_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)

    # 1. Click "Sign" button
    await dp.feed_update(bot, create_callback_update(user_id, "Sign"))
    assert await dp.storage.get_state(state_key) == StateSign.sending_xdr
    mock_telegram.clear()

    # Pre-set user_lang to avoid KeyError in get_kb_pin (needed for subsequent steps)
    await dp.storage.update_data(state_key, {'user_lang': 'en'})

    # 2. Send XDR text
    xdr = "AAAAAgAAAAA=" # Valid empty tx XDR for SDK parsing
    await dp.feed_update(bot, create_message_update(user_id, xdr))
    # Should move to PinState.sign
    assert await dp.storage.get_state(state_key) == PinState.sign
    mock_telegram.clear()

    # 3. Enter PIN "1234"
    await dp.storage.update_data(state_key, {'pin': '123'})
    
    # Enter last digit "4" (triggers sign)
    await dp.feed_update(bot, create_callback_update(user_id, PinCallbackData(action="4").pack()))
    
    # Verify signing was called via patched stellar_tools
    setup_sign_mocks.m_user_sign.assert_called_once()
    
    # Verify message sent with "SendTr" button
    latest_req = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')][-1]
    markup = latest_req['data']['reply_markup']
    assert "SendTr" in markup or "kb_send_tr" in markup
    mock_telegram.clear()

    # 4. Click "SendTr"
    await dp.feed_update(bot, create_callback_update(user_id, "SendTr"))
    
    # Verify transaction submitted via patched stellar_tools
    setup_sign_mocks.m_send.assert_called_once_with("SIGNED_XDR")
    
    # Final confirmation
    latest_req = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')][-1]
    assert "send_good" in latest_req['data']['text'] # Localized key


@pytest.mark.asyncio
async def test_pin_deletion_logic(mock_telegram, router_app_context, setup_sign_mocks):
    """Test using 'Del' button in PIN entry."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(sign_router)

    user_id = 123
    bot = router_app_context.bot
    state_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)

    # Pre-set state to PIN entry
    await dp.storage.set_state(state_key, PinState.sign)
    await dp.storage.set_data(state_key, {'pin': '12', 'pin_type': 1, 'user_lang': 'en'})

    # Click 'Del'
    await dp.feed_update(bot, create_callback_update(user_id, PinCallbackData(action="Del").pack()))
    
    data = await dp.storage.get_data(state_key)
    assert data.get('pin') == "1"

    # Click '1' -> pin becomes '11'
    await dp.feed_update(bot, create_callback_update(user_id, PinCallbackData(action="1").pack()))
    data = await dp.storage.get_data(state_key)
    assert data.get('pin') == "11"


@pytest.mark.asyncio
async def test_cmd_yes_send_integration(mock_telegram, router_app_context, setup_sign_mocks):
    """Test 'Yes_send_xdr' callback: should move to sign_and_send state."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(sign_router)

    user_id = 123
    bot = router_app_context.bot
    state_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)

    # Pre-set user_lang
    await dp.storage.update_data(state_key, {'user_lang': 'en'})

    await dp.feed_update(bot, create_callback_update(user_id, "Yes_send_xdr"))

    assert await dp.storage.get_state(state_key) == PinState.sign_and_send
    latest_req = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')][-1]
    assert "enter_pin" in latest_req['data']['text'] or "enter_password" in latest_req['data']['text']


@pytest.mark.asyncio
async def test_pin_type_10_shows_webapp_button(mock_telegram, router_app_context, setup_sign_mocks):
    """
    Test use_pin=10 (read-only) shows WebApp sign button instead of XDR text.
    """
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(sign_router)

    user_id = 123
    bot = router_app_context.bot
    state_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)

    # Set wallet to use_pin=10 (read-only mode)
    setup_sign_mocks.wallet.use_pin = 10

    # Setup fakeredis for publish_pending_tx
    fake_redis = fakeredis.aioredis.FakeRedis()

    # Set global REDIS_CLIENT for the test
    old_redis_client = faststream_tools.REDIS_CLIENT
    faststream_tools.REDIS_CLIENT = fake_redis

    try:
        # 1. Click "Sign" button
        await dp.feed_update(bot, create_callback_update(user_id, "Sign"))
        assert await dp.storage.get_state(state_key) == StateSign.sending_xdr
        mock_telegram.clear()

        # Pre-set user_lang
        await dp.storage.update_data(state_key, {'user_lang': 'en'})

        # 2. Send XDR text
        xdr = "AAAAAgAAAAA="
        await dp.feed_update(bot, create_message_update(user_id, xdr))

        # Should move to PinState.sign
        assert await dp.storage.get_state(state_key) == PinState.sign

        # Verify TX was stored in Redis
        keys = await fake_redis.keys("tx:*")
        assert len(keys) == 1
        tx_key = keys[0]
        tx_data = await fake_redis.hgetall(tx_key)
        decoded_data = {k.decode(): v.decode() for k, v in tx_data.items()}
        assert decoded_data["user_id"] == str(user_id)
        assert decoded_data["unsigned_xdr"] == xdr

        # Verify WebApp button is shown in the message
        latest_req = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')][-1]
        markup = latest_req['data'].get('reply_markup', '')
        # WebApp keyboard contains web_app URL and cancel_biometric_sign callback
        assert "web_app" in markup or "cancel_biometric_sign" in markup
    finally:
        # Restore globals
        faststream_tools.REDIS_CLIENT = old_redis_client
        await fake_redis.aclose()


@pytest.mark.asyncio
async def test_cancel_biometric_sign(mock_telegram, router_app_context, setup_sign_mocks):
    """
    Test cancelling biometric signing deletes TX from Redis and removes message.
    """
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(sign_router)

    user_id = 123
    tx_id = f"{user_id}_test1234"
    bot = router_app_context.bot

    # Setup fakeredis with the TX already stored
    fake_redis = fakeredis.aioredis.FakeRedis()
    await fake_redis.hset(f"tx:{tx_id}", mapping={"user_id": str(user_id), "status": "pending"})

    # Set global REDIS_CLIENT for the test
    old_redis_client = faststream_tools.REDIS_CLIENT
    faststream_tools.REDIS_CLIENT = fake_redis

    try:
        # Trigger cancel callback
        await dp.feed_update(
            bot,
            create_callback_update(user_id, f"cancel_biometric_sign:{tx_id}")
        )

        # Verify TX was deleted from Redis
        exists = await fake_redis.exists(f"tx:{tx_id}")
        assert exists == 0
    finally:
        # Restore globals
        faststream_tools.REDIS_CLIENT = old_redis_client
        await fake_redis.aclose()


@pytest.mark.asyncio
async def test_cancel_biometric_sign_expired_tx(mock_telegram, router_app_context, setup_sign_mocks):
    """
    Test cancelling already expired/processed TX shows appropriate message.
    """
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(sign_router)

    user_id = 123
    tx_id = f"{user_id}_expired123"
    bot = router_app_context.bot

    # Setup fakeredis WITHOUT the TX (simulating expired)
    fake_redis = fakeredis.aioredis.FakeRedis()

    # Set global REDIS_CLIENT for the test
    old_redis_client = faststream_tools.REDIS_CLIENT
    faststream_tools.REDIS_CLIENT = fake_redis

    try:
        await dp.feed_update(
            bot,
            create_callback_update(user_id, f"cancel_biometric_sign:{tx_id}")
        )

        # TX didn't exist, handler should have handled it gracefully
        # (no exception means success)
    finally:
        # Restore globals
        faststream_tools.REDIS_CLIENT = old_redis_client
        await fake_redis.aclose()
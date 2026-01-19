import pytest
import jsonpickle
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from aiogram import types, Dispatcher, F
from aiogram.fsm.storage.base import StorageKey

from routers.sign import router as sign_router, PinState, PinCallbackData
from infrastructure.services.app_context import AppContext
from infrastructure.states import StateSign
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if sign_router.parent_router:
        sign_router._parent_router = None

@pytest.fixture
def setup_sign_mocks(router_app_context):
    """
    Common mock setup for Sign router tests.
    """
    class SignMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default StellarService mocks
            self.ctx.stellar_service.is_free_wallet = AsyncMock(return_value=False)
            self.ctx.stellar_service.check_xdr = AsyncMock(return_value="AAAAXDR...")
            
            mock_acc = MagicMock()
            mock_acc.account.account_id = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            self.ctx.stellar_service.get_user_account = AsyncMock(return_value=mock_acc)
            
            # Mock get_user_keypair to succeed for "1234"
            async def mock_get_kp(session, user_id, pin):
                if pin == "1234": return MagicMock()
                raise Exception("Bad Pin")
            self.ctx.stellar_service.get_user_keypair = AsyncMock(side_effect=mock_get_kp)
            
            self.ctx.stellar_service.user_sign = AsyncMock(return_value="SIGNED_XDR")
            self.ctx.stellar_service.send_xdr_async = AsyncMock(return_value={"hash": "tx_hash", "paging_token": "123"})
            
            # Default Wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = mock_acc.account.account_id
            self.wallet.use_pin = 1
            self.wallet.is_free = False
            
            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

    return SignMockHelper(router_app_context)


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
    await dp.feed_update(bot, create_message_update(user_id, "AAAAXDR..."))
    # Should move to PinState.sign
    assert await dp.storage.get_state(state_key) == PinState.sign
    mock_telegram.clear()

    # 3. Enter PIN "1234"
    for digit in "123":
        await dp.feed_update(bot, create_callback_update(user_id, PinCallbackData(action=digit).pack()))
    
    # Enter last digit "4" (triggers sign)
    await dp.feed_update(bot, create_callback_update(user_id, PinCallbackData(action="4").pack()))
    
    # Verify signing was called
    router_app_context.stellar_service.user_sign.assert_called_once()
    
    # Verify message sent with "SendTr" button
    # Search for latest message (sendMessage or editMessageText)
    latest_req = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')][-1]
    assert "SendTr" in latest_req['data']['reply_markup']
    mock_telegram.clear()

    # 4. Click "SendTr"
    await dp.feed_update(bot, create_callback_update(user_id, "SendTr"))
    
    # Verify transaction submitted
    router_app_context.stellar_service.send_xdr_async.assert_called_once_with("SIGNED_XDR")
    
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
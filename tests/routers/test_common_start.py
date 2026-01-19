import pytest
import jsonpickle
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.storage.base import StorageKey

from routers.common_start import (
    router as start_router,
    SettingState,
)
from core.domain.value_objects import Balance, PaymentResult
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
    if start_router.parent_router:
        start_router._parent_router = None

@pytest.fixture
def setup_common_start_mocks(router_app_context):
    """
    Common mock setup for common_start router tests.
    """
    class CommonStartMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # User Repo
            self.user = MagicMock()
            self.user.user_id = 123
            self.user.lang = 'en'
            self.user.can_5000 = 0
            self.user.default_address = None
            self.user_repo = MagicMock()
            self.user_repo.get_by_id = AsyncMock(return_value=self.user)
            self.user_repo.update = AsyncMock()
            self.ctx.repository_factory.get_user_repository.return_value = self.user_repo

            # Wallet Repo
            self.wallet = MagicMock()
            self.wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            self.wallet.is_free = False
            self.wallet.assets_visibility = "{}"
            self.wallet_repo = MagicMock()
            self.wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.wallet_repo.get_info = AsyncMock(return_value="[Info]")
            self.wallet_repo.reset_balance_cache = AsyncMock()
            self.ctx.repository_factory.get_wallet_repository.return_value = self.wallet_repo

            # Secret Service
            self.secret_service = AsyncMock()
            self.secret_service.is_ton_wallet.return_value = False
            self.ctx.use_case_factory.create_wallet_secret_service.return_value = self.secret_service

            # Balance Use Case
            self.balances = [
                Balance(asset_code="EURMTL", balance="100.0", asset_issuer="GISS", asset_type="credit_alphanum12"),
            ]
            self.balance_uc = MagicMock()
            self.balance_uc.execute = AsyncMock(return_value=self.balances)
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = self.balance_uc

            # Update Profile Use Case
            self.update_profile_uc = MagicMock()
            self.update_profile_uc.execute = AsyncMock()
            self.ctx.use_case_factory.create_update_user_profile.return_value = self.update_profile_uc

            # Register User Use Case
            self.register_uc = MagicMock()
            self.register_uc.execute = AsyncMock()
            self.ctx.use_case_factory.create_register_user.return_value = self.register_uc
            
            # Encryption Service
            self.ctx.encryption_service.encrypt = MagicMock(return_value="ENCRYPTED")

    return CommonStartMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')]
    return msgs[-1] if msgs else None

def get_all_texts(mock_telegram):
    """Helper to get all texts from mock_telegram."""
    return " ".join([m["data"].get("text", "") for m in mock_telegram if m['method'] in ('sendMessage', 'editMessageText')])


@pytest.mark.asyncio
async def test_cmd_start_existing_user(mock_telegram, router_app_context, setup_common_start_mocks):
    """Test /start for existing user: should show balance."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123
    
    with patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")):
        await dp.feed_update(router_app_context.bot, create_message_update(user_id, "/start"))

    texts = get_all_texts(mock_telegram)
    assert "your_balance" in texts
    assert "EURMTL" in texts


@pytest.mark.asyncio
async def test_cmd_start_new_user(mock_telegram, router_app_context, setup_common_start_mocks):
    """Test /start for new user: should register and show language selection."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123
    
    with patch("routers.common_start.check_user_lang", AsyncMock(return_value=None)), \
         patch("routers.common_start.cmd_language", AsyncMock()) as mock_lang:
        
        await dp.feed_update(router_app_context.bot, create_message_update(user_id, "/start"))

    # Verify registration called
    setup_common_start_mocks.register_uc.execute.assert_called_once()
    # Verify encryption called
    setup_common_start_mocks.ctx.encryption_service.encrypt.assert_called_once()
    # Verify language selection triggered
    mock_lang.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_start_sign_flow(mock_telegram, router_app_context, setup_common_start_mocks):
    """Test /start sign_... flow: should transition to signing."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123
    
    with patch("routers.common_start.check_user_id", AsyncMock(return_value=True)), \
         patch("routers.common_start.cmd_check_xdr", AsyncMock()) as mock_check:
        
        await dp.feed_update(router_app_context.bot, create_message_update(user_id, "/start sign_12345"))

    mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_cb_return_to_main(mock_telegram, router_app_context, setup_common_start_mocks):
    """Test clicking 'Return' button: should show balance."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "Return"))
    
    req = get_latest_msg(mock_telegram)
    assert "your_balance" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_donate_start(mock_telegram, router_app_context, setup_common_start_mocks):
    """Test /donate command."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123
    await dp.feed_update(router_app_context.bot, create_message_update(user_id, "/donate"))
    
    req = get_latest_msg(mock_telegram)
    assert "Choose how much you want to send" in req["data"]["text"]
    
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    assert await dp.storage.get_state(state_key) == SettingState.send_donate_sum


@pytest.mark.asyncio
async def test_cb_set_limit_toggle(mock_telegram, router_app_context, setup_common_start_mocks):
    """Test toggling limits via OffLimits callback."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123
    setup_common_start_mocks.user.can_5000 = 0
    
    # 1. Toggle ON
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "OffLimits"))
    assert setup_common_start_mocks.user.can_5000 == 1
    
    # 2. Toggle OFF
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "OffLimits", update_id=2))
    assert setup_common_start_mocks.user.can_5000 == 0


@pytest.mark.asyncio
async def test_cmd_refresh_balances(mock_telegram, router_app_context, setup_common_start_mocks):
    """Test Refresh button: should reset cache and show balance."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "Refresh"))
    
    setup_common_start_mocks.wallet_repo.reset_balance_cache.assert_called_once()
    texts = get_all_texts(mock_telegram)
    assert "your_balance" in texts


@pytest.mark.asyncio
async def test_cq_show_more_toggle(mock_telegram, router_app_context, setup_common_start_mocks):
    """Test ShowMoreToggle callback."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    
    # Initial: False
    await dp.storage.update_data(state_key, {'show_more': False})

    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "ShowMoreToggle"))
    
    data = await dp.storage.get_data(state_key)
    assert data['show_more'] is True
    
    # Verify message was edited (editMessageText)
    req = get_latest_msg(mock_telegram)
    assert req['method'] == 'editMessageText'
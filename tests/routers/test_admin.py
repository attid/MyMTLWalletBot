import pytest
import os
from unittest.mock import MagicMock, AsyncMock
from aiogram.fsm.storage.base import StorageKey

from routers.admin import router as admin_router, ExitState
from other.config_reader import config
from tests.conftest import (
    RouterTestMiddleware,
    create_message_update,
    get_telegram_request,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached and admin config is restored after each test."""
    # Store original config values
    original_admins = list(config.admins)
    original_horizon_url = config.horizon_url
    
    # Set test admins for filtering
    config.admins.clear()
    config.admins.append(123)
    
    yield
    
    # Restore original config
    config.admins.clear()
    config.admins.extend(original_admins)
    config.horizon_url = original_horizon_url
    
    if admin_router.parent_router:
        admin_router._parent_router = None

@pytest.fixture
def setup_admin_mocks(router_app_context):
    """
    Common mock setup for Admin router tests.
    """
    class AdminMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self.mock_session = MagicMock()
            self._setup_defaults()

        def _setup_defaults(self):
            # Setup async session methods
            self.mock_session.execute = AsyncMock()
            self.mock_session.commit = AsyncMock()
            
            # Default result mock
            self.result_mock = MagicMock()
            self.mock_session.execute.return_value = self.result_mock
            
            # Default return values
            self.result_mock.scalar.return_value = 0
            self.result_mock.scalars.return_value.all.return_value = []
            self.result_mock.all.return_value = []
            self.result_mock.scalar_one_or_none.return_value = None
            
            # Keep query_mock for complex setups if needed, 
            # but usually we just configure result_mock for execute()
            self.query_mock = MagicMock()

        def set_stats_data(self, top_ops):
            """Configure data for /stats command."""
            # The last query in cmd_stats calls .all()
            self.result_mock.all.return_value = top_ops

        def set_user_wallets(self, user, wallets):
            """Configure data for /user_wallets command."""
            # First query fetches user via scalar_one_or_none
            # Second query fetches wallets via scalars().all()
            
            # We need to distinguish between calls or just return what's needed.
            # Since user fetch calls scalar_one_or_none and wallets fetch calls scalars().all(),
            # we can set them independently on the same mock object since they use different methods.
            self.result_mock.scalar_one_or_none.return_value = user
            self.result_mock.scalars.return_value.all.return_value = wallets

        def set_address_info(self, wallet_user_tuple):
            """Configure data for /address_info command."""
            # This is tricky because it calls scalar_one_or_none twice (for wallet and for user)
            # wallet_user_tuple should be (wallet, user)
            wallet, user = wallet_user_tuple
            self.result_mock.scalar_one_or_none.side_effect = [wallet, user]

    helper = AdminMockHelper(router_app_context)
    
    # Custom middleware to inject our controlled mock_session
    class CustomSessionMiddleware:
        async def __call__(self, handler, event, data):
            data["session"] = helper.mock_session
            data["app_context"] = helper.ctx
            return await handler(event, data)
            
    router_app_context.dispatcher.message.middleware(CustomSessionMiddleware())
    return helper


@pytest.mark.asyncio
async def test_cmd_stats(mock_telegram, router_app_context, setup_admin_mocks):
    """Test /stats: should show aggregated statistics."""
    setup_admin_mocks.set_stats_data([("op1", 5), ("op2", 3)])
    
    dp = router_app_context.dispatcher
    dp.include_router(admin_router)

    update = create_message_update(user_id=123, text="/stats", username="itolstov")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "Статистика бота" in req["data"]["text"]
    assert "op1: 5" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_exit_restart_flow(mock_telegram, router_app_context, setup_admin_mocks):
    """Test /exit: first call warns, second call exits."""
    dp = router_app_context.dispatcher
    dp.include_router(admin_router)
    user_id = 123

    # 1. First call
    update1 = create_message_update(user_id, "/exit", username="itolstov", update_id=1)
    await dp.feed_update(bot=router_app_context.bot, update=update1, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert ":'[" in req["data"]["text"]
    
    # Verify state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    assert await dp.storage.get_state(key=storage_key) == ExitState.need_exit

    # 2. Second call - should exit (but skipped in test mode)
    mock_telegram.clear()
    update2 = create_message_update(user_id, "/exit", username="itolstov", update_id=2, message_id=2)
    await dp.feed_update(bot=router_app_context.bot, update=update2, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "Chao :[[[" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_horizon_cycle(mock_telegram, router_app_context, setup_admin_mocks):
    """Test /horizon: cycles through URLs."""
    from other.config_reader import horizont_urls
    
    dp = router_app_context.dispatcher
    dp.include_router(admin_router)

    # Setup test URLs
    original_urls = list(horizont_urls)
    horizont_urls.clear()
    horizont_urls.extend(["url1", "url2"])
    
    try:
        config.horizon_url = "url1"
        update = create_message_update(user_id=123, text="/horizon", username="itolstov")
        await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

        assert config.horizon_url == "url2"
        req = get_telegram_request(mock_telegram, "sendMessage")
        assert "Horizon url: url2" in req["data"]["text"]
    finally:
        # Restore original URLs
        horizont_urls.clear()
        horizont_urls.extend(original_urls)


@pytest.mark.asyncio
async def test_cmd_log_err_clear(mock_telegram, router_app_context, setup_admin_mocks):
    """Test log commands and clearing."""
    dp = router_app_context.dispatcher
    dp.include_router(admin_router)
    user_id = 123

    log_files = ['mmwb.log', 'mmwb_check_transaction.log', 'MyMTLWallet_bot.err', 'MMWB.err', 'MMWB.log']
    for f in log_files:
        with open(f, 'w') as fh:
            fh.write('log')

    try:
        # /log
        await dp.feed_update(bot=router_app_context.bot, update=create_message_update(user_id, "/log", username="itolstov"), app_context=router_app_context)
        assert any(r['method'] == 'sendDocument' for r in mock_telegram)

        # /clear - file deletion skipped in test mode
        mock_telegram.clear()
        await dp.feed_update(bot=router_app_context.bot, update=create_message_update(user_id, "/clear", username="itolstov"), app_context=router_app_context)
    finally:
        for f in log_files:
            if os.path.exists(f):
                os.remove(f)

@pytest.mark.asyncio
async def test_cmd_fee(mock_telegram, mock_horizon, router_app_context, setup_admin_mocks):
    """Test /fee command."""
    dp = router_app_context.dispatcher
    dp.include_router(admin_router)

    # mock_horizon already returns fee_stats with default values
    # Default: {"fee_charged": {"min": "100", "max": "10000", ...}}
    await dp.feed_update(bot=router_app_context.bot, update=create_message_update(123, "/fee"), app_context=router_app_context)
    req = get_telegram_request(mock_telegram, "sendMessage")
    # Check that fee info is in response (mock_horizon returns "100-10000")
    assert "100" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_user_wallets(mock_telegram, router_app_context, setup_admin_mocks):
    """Test /user_wallets search."""
    dp = router_app_context.dispatcher
    dp.include_router(admin_router)

    user = MagicMock(user_id=111)
    wallet = MagicMock(public_key="GABC", default_wallet=1, free_wallet=1, need_delete=0, use_pin=0)
    setup_admin_mocks.set_user_wallets(user, [wallet])

    await dp.feed_update(bot=router_app_context.bot, update=create_message_update(123, "/user_wallets @test"), app_context=router_app_context)
    
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "GABC" in req["data"]["text"]
    assert "main" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_address_info(mock_telegram, router_app_context, setup_admin_mocks):
    """Test /address_info lookup."""
    dp = router_app_context.dispatcher
    dp.include_router(admin_router)

    wallet = MagicMock(user_id=111, use_pin=0, free_wallet=0, need_delete=0)
    user = MagicMock(user_name="testuser", user_id=111)
    setup_admin_mocks.set_address_info((wallet, user))

    await dp.feed_update(bot=router_app_context.bot, update=create_message_update(123, "/address_info GABC"), app_context=router_app_context)
    
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "ID: 111" in req["data"]["text"]
    assert "testuser" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_delete_address(mock_telegram, router_app_context, setup_admin_mocks):
    """Test /delete_address marking."""
    dp = router_app_context.dispatcher
    dp.include_router(admin_router)

    wallet = MagicMock(need_delete=0)
    setup_admin_mocks.result_mock.scalar_one_or_none.return_value = wallet

    await dp.feed_update(bot=router_app_context.bot, update=create_message_update(123, "/delete_address GABC"), app_context=router_app_context)
    
    assert wallet.need_delete == 1
    assert setup_admin_mocks.mock_session.commit.called


@pytest.mark.asyncio
async def test_cmd_help(mock_telegram, router_app_context):
    """Test /help command."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(admin_router)

    await dp.feed_update(bot=router_app_context.bot, update=create_message_update(123, "/help"), app_context=router_app_context)
    
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "/stats" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_test(mock_telegram, router_app_context):
    """Test /test command functionality."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(admin_router)

    chat_mock = MagicMock()
    chat_mock.json.return_value = '{"id": 215155653}'
    router_app_context.bot.get_chat = AsyncMock(return_value=chat_mock)
    
    await dp.feed_update(bot=router_app_context.bot, update=create_message_update(123, "/test", username="itolstov"), app_context=router_app_context)
    assert any(r['method'] == 'sendMessage' for r in mock_telegram)
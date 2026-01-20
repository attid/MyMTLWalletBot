import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.storage.base import StorageKey

from routers.notification_settings import (
    router as notification_router,
)
from keyboards.common_keyboards import HideNotificationCallbackData
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if notification_router.parent_router:
        notification_router._parent_router = None

@pytest.fixture
def setup_notification_mocks(router_app_context):
    """
    Common mock setup for notification settings router tests.
    """
    class NotificationMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Wallet Repo
            self.wallet = MagicMock()
            self.wallet.id = 1
            self.wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            self.wallet_repo = MagicMock()
            self.wallet_repo.get_by_id = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = self.wallet_repo

            # Operation Repo
            self.operation = MagicMock()
            self.operation.id = 10
            self.operation.code1 = "EURMTL"
            self.operation.amount1 = "5.0"
            self.operation.operation = "payment"
            self.op_repo = MagicMock()
            self.op_repo.get_by_id = AsyncMock(return_value=self.operation)
            self.ctx.repository_factory.get_operation_repository.return_value = self.op_repo

            # Notification Repo
            self.notif_repo = MagicMock()
            self.notif_repo.get_by_user_id = AsyncMock(return_value=[])
            self.notif_repo.find_duplicate = AsyncMock(return_value=None)
            self.notif_repo.create = AsyncMock()
            self.notif_repo.delete_all_by_user = AsyncMock()
            self.ctx.repository_factory.get_notification_repository.return_value = self.notif_repo

    return NotificationMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')]
    return msgs[-1] if msgs else None


@pytest.mark.asyncio
async def test_hide_notification_start_flow(mock_telegram, router_app_context, setup_notification_mocks):
    """Test clicking 'Hide notification' button: should open settings menu."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(notification_router)

    user_id = 123
    cb_data = HideNotificationCallbackData(wallet_id=1, operation_id="10").pack()
    
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, cb_data))

    req = get_latest_msg(mock_telegram)
    assert "notification_settings_menu" in req["data"]["text"]
    assert "toggle_token_notify" in req["data"]["reply_markup"]
    
    # Verify state data
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    data = await dp.storage.get_data(state_key)
    assert data['asset_code'] == "EURMTL"
    assert data['operation_id'] == 10


@pytest.mark.asyncio
async def test_toggle_token_notify(mock_telegram, router_app_context, setup_notification_mocks):
    """Test toggling specific token notification."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(notification_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    
    # Initial state: token set
    await dp.storage.update_data(state_key, {'asset_code': 'EURMTL', 'operation_id': 10})

    # 1. Toggle OFF
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "toggle_token_notify"))
    data = await dp.storage.get_data(state_key)
    assert data['asset_code'] is None
    
    # 2. Toggle ON
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "toggle_token_notify", update_id=2))
    data = await dp.storage.get_data(state_key)
    assert data['asset_code'] == "EURMTL"


@pytest.mark.asyncio
async def test_change_amount_cycle(mock_telegram, router_app_context, setup_notification_mocks):
    """Test cycling through amounts [0, 1, 10, ...]."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(notification_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.update_data(state_key, {'min_amount': 1})

    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "change_amount"))
    
    data = await dp.storage.get_data(state_key)
    assert data['min_amount'] == 10


@pytest.mark.asyncio
async def test_save_filter_success(mock_telegram, router_app_context, setup_notification_mocks):
    """Test saving notification filter."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(notification_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.update_data(state_key, {
        'public_key': 'GKEY', 'asset_code': 'EURMTL', 
        'min_amount': 100, 'operation_type': 'payment'
    })

    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "save_filter"))
    
    setup_notification_mocks.notif_repo.create.assert_called_once()
    req = get_latest_msg(mock_telegram)
    assert "filter_saved" in req["data"]["text"]
    # State should be cleared
    assert await dp.storage.get_state(state_key) is None


@pytest.mark.asyncio
async def test_delete_all_filters(mock_telegram, router_app_context, setup_notification_mocks):
    """Test deleting all user filters."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(notification_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "delete_all_filters"))
    
    setup_notification_mocks.notif_repo.delete_all_by_user.assert_called_once_with(123)
    req = get_latest_msg(mock_telegram)
    assert "all_filters_deleted" in req["data"]["text"]
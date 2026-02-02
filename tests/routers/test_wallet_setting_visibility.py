
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest

from routers.wallet_setting import router as wallet_setting_router, AssetVisibilityCallbackData
from infrastructure.services.app_context import AppContext

from tests.conftest import create_callback_update

@pytest.fixture
def mock_app_context():
    app_context = MagicMock(spec=AppContext)
    app_context.repository_factory = MagicMock()
    app_context.use_case_factory = MagicMock()
    app_context.stellar_service = AsyncMock()
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.side_effect = lambda user_id, key, params=(): str(key)
    return app_context

@pytest.fixture
def mock_wallet_repo():
    repo = AsyncMock()
    wallet = MagicMock()
    wallet.public_key = "G_TEST_PUBLIC_KEY"
    wallet.is_free = False
    wallet.assets_visibility = "{}" # Default empty
    repo.get_default_wallet.return_value = wallet
    return repo, wallet

# moved to top

class CaptureSessionMiddleware(BaseMiddleware):
    def __init__(self, app_context, session):
        self.app_context = app_context
        self.session = session
        # Mock session methods if not already done
        if not hasattr(self.session, "execute"):
             self.session.execute = AsyncMock()
        if not hasattr(self.session, "commit"):
             self.session.commit = AsyncMock()

    async def __call__(self, handler, event, data):
        data["session"] = self.session
        data["app_context"] = self.app_context
        return await handler(event, data)

@pytest.mark.asyncio
async def test_asset_visibility_toggle(mock_app_context, mock_wallet_repo):
    """
    Test toggling asset visibility.
    """
    repo, wallet = mock_wallet_repo
    mock_app_context.repository_factory.get_wallet_repository.return_value = repo

    session = AsyncMock()
    
    # Mock GetWalletBalance use case
    balance_uc = MagicMock()
    balance = MagicMock()
    balance.asset_code = "EURMTL"
    balance_uc.execute = AsyncMock(return_value=[balance])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = balance_uc

    dp = Dispatcher(storage=MemoryStorage())
    # Manually detach router to prevent RuntimeError in tests re-using global router
    wallet_setting_router._parent_router = None
    dp.include_router(wallet_setting_router)
    dp.callback_query.middleware(CaptureSessionMiddleware(mock_app_context, session))
    
    bot = AsyncMock()
    bot.id = 123
    
    # User clicks "Hidden" (status=2) for EURMTL
    cb_data = AssetVisibilityCallbackData(action="set", code="EURMTL", status=2, page=1).pack()
    
    update = create_callback_update(user_id=12345, callback_data=cb_data)
    
    # Patch Message.edit_text to verify call
    with patch.object(Message, "edit_text", new_callable=AsyncMock) as mock_edit:
        await dp.feed_update(bot, update)
        mock_edit.assert_called()
    
    # Verify commit was called
    session.commit.assert_called()
    
    # Verify wallet visibility updated
    assert wallet.assets_visibility != "{}"


@pytest.mark.asyncio
async def test_asset_visibility_ui_handled_gracefully(mock_app_context, mock_wallet_repo):
    """
    Test handling of 'Message is not modified' - should NOT show alert.
    """
    repo, wallet = mock_wallet_repo
    mock_app_context.repository_factory.get_wallet_repository.return_value = repo

    session = AsyncMock()
    
    # Mock GetWalletBalance use case
    balance_uc = MagicMock()
    balance = MagicMock()
    balance.asset_code = "EURMTL"
    balance_uc.execute = AsyncMock(return_value=[balance])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = balance_uc

    dp = Dispatcher(storage=MemoryStorage())
    # Manually detach router to prevent RuntimeError in tests re-using global router
    wallet_setting_router._parent_router = None
    dp.include_router(wallet_setting_router)
    dp.callback_query.middleware(CaptureSessionMiddleware(mock_app_context, session))
    
    bot = AsyncMock()
    bot.id = 123
    
    cb_data = AssetVisibilityCallbackData(action="set", code="EURMTL", status=2, page=1).pack()
    update = create_callback_update(user_id=12345, callback_data=cb_data)
    
    # Patch Message.edit_text to raise TelegramBadRequest("message is not modified")
    # Note: TelegramBadRequest takes method, message_vals. mocking str(e) is easier if we just use exception with msg
    exc = TelegramBadRequest(method="editMessageText", message="message is not modified")
    
    with patch.object(Message, "edit_text", side_effect=exc):
        with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as mock_answer:
            await dp.feed_update(bot, update)
            
            # Verify Answer called WITHOUT "UI update failed"
            calls = mock_answer.call_args_list
            for c in calls:
                if c.args:
                    assert "UI update failed" not in c.args[0]
                # Also check show_alert is not True (or check explicit call)
                # It calls answer(text) without show_alert=True for success case
                if 'show_alert' in c.kwargs:
                     assert c.kwargs['show_alert'] is False or c.kwargs['show_alert'] is None

    session.commit.assert_called()


@pytest.mark.asyncio
async def test_asset_visibility_ui_fail_real_error(mock_app_context, mock_wallet_repo):
    """
    Test handling of other errors - MUST show alert.
    """
    repo, wallet = mock_wallet_repo
    mock_app_context.repository_factory.get_wallet_repository.return_value = repo

    session = AsyncMock()
    
    # Mock GetWalletBalance use case
    balance_uc = MagicMock()
    balance = MagicMock()
    balance.asset_code = "EURMTL"
    balance_uc.execute = AsyncMock(return_value=[balance])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = balance_uc

    dp = Dispatcher(storage=MemoryStorage())
    # Manually detach router to prevent RuntimeError in tests re-using global router
    wallet_setting_router._parent_router = None
    dp.include_router(wallet_setting_router)
    dp.callback_query.middleware(CaptureSessionMiddleware(mock_app_context, session))
    
    bot = AsyncMock()
    bot.id = 123
    
    cb_data = AssetVisibilityCallbackData(action="set", code="EURMTL", status=2, page=1).pack()
    update = create_callback_update(user_id=12345, callback_data=cb_data)
    
    # Patch Message.edit_text to raise Generic Exception
    with patch.object(Message, "edit_text", side_effect=Exception("Generic error")):
        with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as mock_answer:
            await dp.feed_update(bot, update)
            
            # Verify Answer called WITH "UI update failed"
            calls = mock_answer.call_args_list
            found = False
            for c in calls:
                if c.args and "UI update failed" in c.args[0]:
                    found = True
                    break
            assert found, "Should show UI update failed for generic errors"

    session.commit.assert_called()

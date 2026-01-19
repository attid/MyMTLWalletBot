import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.common_setting import cmd_language, callbacks_lang, cmd_support, LangCallbackData
from routers.notification_settings import hide_notification_callback, save_filter_callback
from keyboards.common_keyboards import HideNotificationCallbackData

# --- tests for routers/common_setting.py ---

@pytest.mark.asyncio
async def test_cmd_language(mock_session, mock_callback, mock_app_context):
    # Setup localization
    mock_app_context.localization_service.lang_dict = {'en': {'1_lang': 'English'}, 'ru': {'1_lang': 'Russian'}}
    
    # Run handler
    await cmd_language(mock_session, 123, mock_app_context.localization_service, app_context=mock_app_context)
    
    # Verify
    mock_app_context.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_callbacks_lang(mock_session, mock_callback, mock_state, mock_app_context):
    callback_data = LangCallbackData(action="ru")
    
    # Setup mocks for cmd_show_balance dependencies
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GKey"
    mock_wallet.is_free = False
    
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_wallet_repo.get_info = AsyncMock(return_value="WalletInfo")
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    mock_secret_service = MagicMock()
    mock_secret_service.is_ton_wallet = AsyncMock(return_value=False)
    mock_app_context.use_case_factory.create_wallet_secret_service.return_value = mock_secret_service
    
    mock_balance_use_case = MagicMock()
    mock_balance_use_case.execute = AsyncMock(return_value=[])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_use_case
    
    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=MagicMock())
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    # Mock change_user_lang (legacy DB util)
    with patch("routers.common_setting.change_user_lang", new_callable=AsyncMock) as mock_change:
        
        await callbacks_lang(mock_callback, callback_data, mock_state, mock_session, mock_app_context.localization_service, mock_app_context)
        
        mock_change.assert_called_once_with(mock_session, 123, "ru")
        
        # Check that user_lang was updated
        # mock_state.update_data is called multiple times (once for lang, once for balance)
        # We need to verify that one of them was user_lang='ru'
        calls = [call.kwargs for call in mock_state.update_data.call_args_list]
        assert any(c.get('user_lang') == 'ru' for c in calls)
        
        # Verify cmd_show_balance execution via side-effects (send_message called)
        mock_app_context.bot.send_message.assert_called()


@pytest.mark.asyncio
async def test_cmd_support(mock_session, mock_callback, mock_state, mock_app_context):
    await cmd_support(mock_callback, mock_state, mock_session, app_context=mock_app_context)
    
    # send_message calls bot.send_message
    mock_app_context.bot.send_message.assert_called_once()


# --- tests for routers/notification_settings.py ---

@pytest.mark.asyncio
async def test_hide_notification_callback(mock_session, mock_callback, mock_state, mock_app_context):
    callback_data = HideNotificationCallbackData(wallet_id=1, operation_id="10")
    mock_callback.data = callback_data.pack()
    
    # Setup mocks
    mock_wallet = MagicMock()
    mock_wallet.user_id = 123
    mock_wallet.public_key = "GKey"
    
    mock_op = MagicMock()
    mock_op.code1 = "XLM"
    mock_op.amount1 = "10.0"
    mock_op.operation = "payment"

    # Configure repository factory
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_by_id = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    mock_op_repo = MagicMock()
    mock_op_repo.get_by_id = AsyncMock(return_value=mock_op)
    mock_app_context.repository_factory.get_operation_repository.return_value = mock_op_repo
    
    # Mock send_notification_settings_menu to avoid complex UI construction if desired, 
    # OR let it run. Let's let it run but ensure it calls send_message.
    # It calls send_message -> bot.send_message.
    
    await hide_notification_callback(mock_callback, mock_state, mock_session, app_context=mock_app_context)
    
    mock_state.update_data.assert_called()
    mock_app_context.bot.send_message.assert_called()


@pytest.mark.asyncio
async def test_save_filter_callback(mock_session, mock_callback, mock_state, mock_app_context):
    mock_state.get_data.return_value = {
        'asset_code': 'XLM',
        'min_amount': 10,
        'operation_type': 'payment',
        'public_key': 'GKey',
        'for_all_wallets': False
    }
    
    mock_repo = MagicMock()
    mock_repo.find_duplicate = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock()
    mock_app_context.repository_factory.get_notification_repository.return_value = mock_repo

    await save_filter_callback(mock_callback, mock_state, mock_session, app_context=mock_app_context)
    
    mock_repo.create.assert_called_once()
    mock_state.clear.assert_called_once()
    mock_app_context.bot.send_message.assert_called()
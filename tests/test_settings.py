
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.common_setting import cmd_language, callbacks_lang, cmd_support, LangCallbackData
from routers.notification_settings import hide_notification_callback, save_filter_callback
from keyboards.common_keyboards import HideNotificationCallbackData
from db.models import MyMtlWalletBot

@pytest.fixture
def mock_session():
    session = MagicMock()
    return session

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    return state

@pytest.fixture
def mock_callback():
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.from_user.username = "user"
    callback.message = AsyncMock()
    callback.message.chat.id = 123
    return callback

@pytest.fixture
def mock_message():
    message = AsyncMock()
    message.from_user.id = 123
    message.chat.id = 123
    message.text = "test_text"
    return message

# --- tests for routers/common_setting.py ---

@pytest.mark.asyncio
async def test_cmd_language(mock_session, mock_callback):
    with patch("routers.common_setting.send_message", new_callable=AsyncMock) as mock_send, \
         patch("keyboards.common_keyboards.my_gettext", return_value="text"), \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        # mock_gd.lang_dict = {'en': {'1_lang': 'English'}, 'ru': {'1_lang': 'Russian'}} 
        
        l10n = MagicMock()
        l10n.lang_dict = {'en': {'1_lang': 'English'}, 'ru': {'1_lang': 'Russian'}}

        await cmd_language(mock_session, 123, l10n)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_callbacks_lang(mock_session, mock_callback, mock_state):
    callback_data = LangCallbackData(action="ru")
    
    with patch("routers.common_setting.change_user_lang") as mock_change, \
         patch("routers.common_setting.cmd_show_balance", new_callable=AsyncMock) as mock_balance, \
         patch("other.lang_tools.get_user_id", return_value=123):
        

        
        l10n = MagicMock()
        l10n.lang_dict = {'en': {}, 'ru': {}}
        
        app_context = MagicMock()

        await callbacks_lang(mock_callback, callback_data, mock_state, mock_session, l10n, app_context)
        
        mock_change.assert_called_once_with(mock_session, 123, "ru")
        mock_state.update_data.assert_called_with(user_lang="ru")
        mock_balance.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_support(mock_session, mock_callback, mock_state):
    with patch("routers.common_setting.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.get_user_id", return_value=123):
         

        
        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'
        await cmd_support(mock_callback, mock_state, mock_session, app_context)
        mock_send.assert_called_once()

# --- tests for routers/notification_settings.py ---

@pytest.mark.asyncio
async def test_hide_notification_callback(mock_session, mock_callback, mock_state):
    # Fix: Correctly pack data as string and assign to callback.data
    callback_data = HideNotificationCallbackData(wallet_id=1, operation_id="10")
    mock_callback.data = callback_data.pack()
    
    # Fix: unpacking inside handler expects string, mock_callback.data is now string.
    
    # Create mock objects
    mock_wallet = MagicMock()
    mock_wallet.user_id = 123
    mock_wallet.public_key = "GKey"
    
    mock_op = MagicMock()
    mock_op.code1 = "XLM"
    mock_op.amount1 = "10.0"
    mock_op.operation = "payment"

    with patch("routers.notification_settings.SqlAlchemyWalletRepository") as MockWalletRepo, \
         patch("routers.notification_settings.SqlAlchemyOperationRepository") as MockOpRepo, \
         patch("routers.notification_settings.send_notification_settings_menu", new_callable=AsyncMock) as mock_menu, \
         patch("other.lang_tools.get_user_id", return_value=123):
         

        
        # Setup repo returns
        mock_wallet_repo = MockWalletRepo.return_value
        mock_wallet_repo.get_by_id = AsyncMock(return_value=mock_wallet) # Use get_by_id as per implementation
        
        mock_op_repo = MockOpRepo.return_value
        mock_op_repo.get_by_id = AsyncMock(return_value=mock_op) # Use get_by_id
        
        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await hide_notification_callback(mock_callback, mock_state, mock_session, app_context=app_context)
        
        mock_state.update_data.assert_called()
        mock_menu.assert_called_once()

@pytest.mark.asyncio
async def test_save_filter_callback(mock_session, mock_callback, mock_state):
    mock_state.get_data.return_value = {
        'asset_code': 'XLM',
        'min_amount': 10,
        'operation_type': 'payment',
        'public_key': 'GKey',
        'for_all_wallets': False
    }
    
    # Mocking that no existing filter exists
    
    with patch("routers.notification_settings.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.notification_settings.SqlAlchemyNotificationRepository") as MockRepo, \
         patch("other.lang_tools.get_user_id", return_value=123):
        

        
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.find_duplicate = AsyncMock(return_value=None)
        mock_repo_instance.create = AsyncMock()

        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await save_filter_callback(mock_callback, mock_state, mock_session, app_context=app_context)
        
        mock_repo_instance.create.assert_called_once()
        mock_state.clear.assert_called_once()
        mock_send.assert_called_once()

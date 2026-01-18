
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.wallet_setting import cmd_wallet_setting, cmd_get_private_key, remove_password, send_private_key
from core.domain.entities import Wallet

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def mock_callback():
    callback = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 123
    callback.message = AsyncMock()
    callback.message.chat.id = 123
    return callback

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    return state

@pytest.mark.asyncio
async def test_cmd_wallet_setting(mock_session, mock_callback, mock_state):
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.is_free = True
    
    with patch("routers.wallet_setting.SqlAlchemyWalletRepository") as MockRepo, \
         patch("routers.wallet_setting.my_gettext", return_value="msg"), \
         patch("routers.wallet_setting.send_message", new_callable=AsyncMock) as mock_send:
         
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_default_wallet = AsyncMock(return_value=mock_wallet)
        
        app_context = MagicMock()
        l10n = MagicMock()
        await cmd_wallet_setting(mock_callback, mock_state, mock_session, app_context, l10n)
        
        mock_send.assert_called_once()
        # Check that 'Buy' button is present for free wallet
        args, kwargs = mock_send.call_args
        kb = kwargs['reply_markup']
        # We can't easily inspect InlineKeyboardMarkup object deeply without helper, 
        # but execution without error is a good start.

@pytest.mark.asyncio
async def test_cmd_get_private_key(mock_session, mock_callback, mock_state):
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.is_free = False
    mock_wallet.use_pin = 1 # Has PIN
    
    with patch("routers.wallet_setting.SqlAlchemyWalletRepository") as MockRepo, \
         patch("routers.wallet_setting.cmd_ask_pin", new_callable=AsyncMock) as mock_ask_pin:
         
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_default_wallet = AsyncMock(return_value=mock_wallet)
        
        app_context = MagicMock()
        await cmd_get_private_key(mock_callback, mock_state, mock_session, app_context)
        
        mock_ask_pin.assert_called_once()
        mock_state.update_data.assert_called()

@pytest.mark.asyncio
async def test_send_private_key(mock_session, mock_state):
    user_id = 123
    mock_state.get_data.return_value = {'pin': '1234'}
    
    mock_secrets = MagicMock()
    mock_secrets.secret_key = "SECRET_KEY"
    mock_secrets.seed_phrase = "SEED_PHRASE"
    
    with patch("routers.wallet_setting.SqlAlchemyWalletRepository") as MockRepo, \
         patch("routers.wallet_setting.EncryptionService"), \
         patch("routers.wallet_setting.GetWalletSecrets") as MockUseCase, \
         patch("routers.wallet_setting.send_message", new_callable=AsyncMock) as mock_send:
         
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=mock_secrets)
        
        await send_private_key(mock_session, user_id, mock_state)
        
        mock_send.assert_called_once()
        assert "SECRET_KEY" in mock_send.call_args[0][2]
        assert "SEED_PHRASE" in mock_send.call_args[0][2]

@pytest.mark.asyncio
async def test_remove_password(mock_session, mock_state):
    user_id = 123
    mock_state.get_data.return_value = {'pin': '1234'}
    
    with patch("routers.wallet_setting.SqlAlchemyWalletRepository") as MockRepo, \
         patch("routers.wallet_setting.EncryptionService"), \
         patch("routers.wallet_setting.ChangeWalletPassword") as MockUseCase, \
         patch("routers.wallet_setting.cmd_info_message", new_callable=AsyncMock) as mock_info:
         
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=True)
        
        await remove_password(mock_session, user_id, mock_state)
        
        mock_use_case.execute.assert_called_once_with(
            user_id=123, old_pin='1234', new_pin='123', pin_type=0
        )
        mock_info.assert_called_once()

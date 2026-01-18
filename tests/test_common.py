
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types, Bot
from aiogram.fsm.context import FSMContext
from routers.common_start import cmd_start, cb_set_limit
from routers.common_end import cmd_last_route
from routers.start_msg import cmd_show_balance, cmd_info_message
from routers.inout import cmd_inout, cmd_usdt_in, cmd_send_usdt_sum, StateInOut
import jsonpickle

@pytest.fixture
def mock_session():
    return MagicMock()

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

@pytest.fixture
def mock_bot():
    return AsyncMock(spec=Bot)

# --- tests for routers/common_start.py ---

@pytest.mark.asyncio
async def test_cmd_start(mock_session, mock_message, mock_state, mock_bot):
    with patch("routers.common_start.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.common_start.clear_state", new_callable=AsyncMock) as mock_clear, \
         patch("routers.common_start.check_user_lang", return_value="en"), \
         patch("routers.common_start.cmd_show_balance", new_callable=AsyncMock) as mock_balance, \
         patch("routers.common_start.check_update_username", new_callable=AsyncMock) as mock_check_username, \
         patch("routers.common_start.check_update_username", new_callable=AsyncMock) as mock_check_username:
         
        app_context = MagicMock()
        l10n = MagicMock()
        await cmd_start(mock_message, mock_state, mock_session, mock_bot, app_context, l10n)
        
        mock_clear.assert_called_once()
        mock_balance.assert_called_once()
        mock_check_username.assert_called_once()

@pytest.mark.asyncio
async def test_cb_set_limit(mock_session, mock_callback, mock_state):
    mock_user = MagicMock()
    mock_user.can_5000 = 0
    mock_user.id = 123
    mock_user.username = "user"
    mock_user.language = "en"
    mock_user.default_address = None
    
    with patch("routers.common_start.SqlAlchemyUserRepository") as MockRepo, \
         patch("routers.common_start.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.common_start.my_gettext", return_value="text"), \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_user)
        mock_repo_instance.update = AsyncMock(return_value=mock_user)
        mock_callback.data = "OffLimits"
        
        app_context = MagicMock()
        await cb_set_limit(mock_callback, mock_state, mock_session, app_context)
        
        assert mock_user.can_5000 == 1
        mock_repo_instance.update.assert_called_once()
        mock_session.commit.assert_called_once()

# --- tests for routers/common_end.py ---

@pytest.mark.asyncio
async def test_cmd_last_route(mock_session, mock_message, mock_state):
    mock_message.chat.type = "private"
    mock_message.text = "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB" # Valid Stellar key
    
    with patch("routers.common_end.is_valid_stellar_address", return_value=True), \
         patch("routers.common_end.find_stellar_addresses", return_value=["GAPQ3..."]), \
         patch("routers.common_end.stellar_check_account", new_callable=AsyncMock) as mock_check_acc, \
         patch("routers.common_end.cmd_send_choose_token", new_callable=AsyncMock) as mock_choose:
        
        mock_check_acc.return_value = MagicMock(account_id="GAPQ3...")
        
        app_context = MagicMock()
        await cmd_last_route(mock_message, mock_state, mock_session, app_context)
        
        mock_state.update_data.assert_called()
        mock_choose.assert_called_once()

# --- tests for routers/start_msg.py ---

@pytest.mark.asyncio
async def test_cmd_show_balance(mock_session, mock_state):
    # Mock SqlAlchemyUserRepository
    mock_user = MagicMock()
    mock_user.id = 123
    
    with patch("routers.start_msg.SqlAlchemyUserRepository") as MockRepo, \
         patch("routers.start_msg.clear_state", new_callable=AsyncMock), \
         patch("routers.start_msg.get_start_text", return_value="Start Text", new_callable=AsyncMock), \
         patch("routers.start_msg.get_kb_default", return_value=types.InlineKeyboardMarkup(inline_keyboard=[]), new_callable=AsyncMock), \
         patch("routers.start_msg.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_user)
        
        
        await cmd_show_balance(mock_session, 123, mock_state)
        mock_send.assert_called_once()

# --- tests for routers/inout.py ---

@pytest.mark.asyncio
async def test_cmd_inout(mock_session, mock_callback):
    with patch("routers.inout.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.inout.my_gettext", return_value="text"), \
         patch("routers.inout.my_gettext", return_value="text"), \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        app_context = MagicMock()
        await cmd_inout(mock_callback, mock_session, app_context)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_usdt_in(mock_session, mock_callback, mock_state):
    asset_balance = MagicMock()
    asset_balance.asset_code = "USDM"
    asset_balance.balance = "100.0"
    
    # Needs config for StellarService
    with patch("routers.inout.SqlAlchemyWalletRepository"), \
         patch("routers.inout.SqlAlchemyUserRepository") as MockUserRepo, \
         patch("routers.inout.StellarService"), \
         patch("routers.inout.GetWalletBalance") as MockGetBalance, \
         patch("routers.inout.create_trc_private_key"), \
         patch("routers.inout.tron_get_public", return_value="TRON_ADDR"), \
         patch("routers.inout.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.inout.get_user_id", return_value=123), \
         patch("routers.inout.my_gettext", return_value="text"), \
         patch("routers.inout.config"), \
         patch("routers.inout.config"), \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_user_repo = MockUserRepo.return_value
        mock_user_repo.get_usdt_key = AsyncMock(return_value=("priv_key", 0))

        mock_balance_use_case = MockGetBalance.return_value
        mock_balance_use_case.execute = AsyncMock(return_value=[asset_balance])
        
        mock_balance_use_case.execute = AsyncMock(return_value=[asset_balance])
        
        # Ensure my_gettext returns a string, avoiding MagicMock in Pydantic models
        with patch("keyboards.common_keyboards.my_gettext", return_value="string_text"), \
             patch("routers.inout.my_gettext", return_value="string_text"):
            app_context = MagicMock()
            app_context.localization_service.get_text.return_value = 'text'
            await cmd_usdt_in(mock_callback, mock_state, mock_session, app_context)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_usdt_sum(mock_session, mock_message, mock_state):
    mock_message.text = "20"
    mock_message.chat.id = 123
    asset_balance = MagicMock()
    asset_balance.asset_code = "USDM"
    asset_balance.balance = "100.0"
    
    with patch("routers.inout.my_float", return_value=20.0), \
         patch("routers.inout.SqlAlchemyWalletRepository"), \
         patch("routers.inout.StellarService"), \
         patch("routers.inout.GetWalletBalance") as MockGetBalance, \
         patch("routers.inout.cmd_send_usdt", new_callable=AsyncMock) as mock_send_usdt, \
         patch("routers.inout.my_gettext", return_value="text"), \
         patch("routers.inout.config"), \
         patch("routers.inout.config"), \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_balance_use_case = MockGetBalance.return_value
        mock_balance_use_case.execute = AsyncMock(return_value=[asset_balance])
        
        app_context = MagicMock()
        await cmd_send_usdt_sum(mock_message, mock_state, mock_session, app_context)
        
        mock_state.update_data.assert_called_with(send_sum=20.0)
        mock_state.set_state.assert_called_with(None)
        mock_send_usdt.assert_called_once()

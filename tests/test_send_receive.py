
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.send import cmd_send_start, cmd_send_token, cmd_send_for, StateSendToken, cmd_send_choose_token
from routers.receive import cmd_receive
from routers.cheque import cmd_create_cheque, StateCheque, cmd_cheque_get_sum
from stellar_sdk import Asset

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

# --- tests for routers/send.py ---

@pytest.mark.asyncio
async def test_cmd_send_start(mock_session, mock_state):
    user_id = 123
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_send_start(user_id, mock_state, mock_session)
        
        mock_send.assert_called_once()
        mock_state.set_state.assert_called_with(StateSendToken.sending_for)

@pytest.mark.asyncio
async def test_cmd_send_token_by_username(mock_session, mock_message, mock_state):
    send_for = "@recipient"
    # Use a valid Stellar public key (randomly generated or from docs)
    # Example: GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA
    valid_issuer = "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"
    send_asset = Asset("USD", valid_issuer)
    send_sum = 10.0
    
    mock_user_in_db = MagicMock()
    mock_user_in_db.user_name = "recipient"
    
    with patch("routers.send.db_get_user_account_by_username", return_value=("GADDR", 456)), \
         patch("routers.send.db_get_user", return_value=mock_user_in_db), \
         patch("routers.send.check_username", return_value="recipient", new_callable=AsyncMock), \
         patch("routers.send.db_update_username") as mock_update_username, \
         patch("routers.send.stellar_check_account", new_callable=AsyncMock), \
         patch("routers.send.cmd_send_04", new_callable=AsyncMock) as mock_send_04, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}

        await cmd_send_token(mock_message, mock_state, mock_session, send_for, send_asset, send_sum)
        
        mock_send_04.assert_called_once()
        mock_state.update_data.assert_called()

@pytest.mark.asyncio
async def test_cmd_send_for_address(mock_session, mock_message, mock_state):
    mock_message.text = "GADDRESS"
    mock_state.get_data.return_value = {}
    
    mock_account = MagicMock()
    mock_account.account_id = "GADDRESS"
    mock_account.memo = None

    with patch("routers.send.stellar_check_account", new_callable=AsyncMock, return_value=mock_account), \
         patch("routers.send.cmd_send_choose_token", new_callable=AsyncMock) as mock_next, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_send_for(mock_message, mock_state, mock_session)
        
        mock_next.assert_called_once()
        mock_state.update_data.assert_called_with(send_address="GADDRESS")

@pytest.mark.asyncio
async def test_cmd_send_choose_token(mock_session, mock_message, mock_state):
    mock_state.get_data.return_value = {"send_address": "GADDR"}
    
    balance = MagicMock()
    balance.asset_code = "XLM"
    balance.balance = "100.0"
    
    with patch("routers.send.stellar_get_balances", return_value=[balance], new_callable=AsyncMock), \
         patch("routers.send.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_send_choose_token(mock_message, mock_state, mock_session)
        
        mock_send.assert_called_once()
        # Verify assets stored in state
        args, kwargs = mock_state.update_data.call_args
        assert "assets" in kwargs

# --- tests for routers/receive.py ---

@pytest.mark.asyncio
async def test_cmd_receive(mock_session, mock_callback, mock_state):
    user_account = MagicMock()
    user_account.account.account_id = "GADDR"
    
    with patch("routers.receive.stellar_get_user_account", new_callable=AsyncMock, return_value=user_account), \
         patch("routers.receive.create_beautiful_code") as mock_create_qr, \
         patch("routers.receive.cmd_info_message", new_callable=AsyncMock) as mock_info, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_receive(mock_callback, mock_state, mock_session)
        
        mock_create_qr.assert_called_once_with(f'qr/GADDR.png', "GADDR")
        mock_info.assert_called_once()

# --- tests for routers/cheque.py ---

@pytest.mark.asyncio
async def test_cmd_create_cheque(mock_session, mock_message, mock_state):
    with patch("routers.cheque.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_create_cheque(mock_message, mock_state, mock_session)
        
        mock_send.assert_called_once()
        mock_state.set_state.assert_called_with(StateCheque.sending_sum)

@pytest.mark.asyncio
async def test_cmd_cheque_get_sum(mock_session, mock_message, mock_state):
    mock_message.text = "10.0"
    
    with patch("routers.cheque.cmd_cheque_show", new_callable=AsyncMock) as mock_show:
        await cmd_cheque_get_sum(mock_message, mock_state, mock_session)
        
        mock_state.update_data.assert_called_with(send_sum=10.0)
        mock_show.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_cheque_get_sum_invalid(mock_session, mock_message, mock_state):
    mock_message.text = "invalid"
    await cmd_cheque_get_sum(mock_message, mock_state, mock_session)
    mock_state.update_data.assert_not_called()
    assert mock_message.delete.called

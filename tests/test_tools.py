
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.mtltools import cmd_tools, cmd_tools_donate, cmd_tools_bim, cmd_tools_delegate
from routers.sign import cmd_yes_send, cmd_ask_pin, PinState, PinCallbackData, cq_pin, cmd_password_from_pin
from routers.ton import cmd_send_ton_start, cmd_send_ton_address
from routers.monitoring import handle_monitoring_message
from routers.uri import process_remote_uri
import jsonpickle

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    state.get_state.return_value = "some_state"
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

# --- tests for routers/mtltools.py ---

@pytest.mark.asyncio
async def test_cmd_tools(mock_session, mock_callback, mock_state):
    with patch("routers.mtltools.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await cmd_tools(mock_callback, mock_state, mock_session, app_context=app_context)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_tools_donate__no_donates(mock_session, mock_callback, mock_state):
    with patch("routers.mtltools.stellar_get_data", return_value={}, new_callable=AsyncMock), \
         patch("routers.mtltools.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await cmd_tools_donate(mock_callback, mock_state, mock_session, app_context=app_context)
        mock_send.assert_called_once()

# --- tests for routers/sign.py ---

@pytest.mark.asyncio
async def test_cmd_yes_send(mock_session, mock_callback, mock_state):
    with patch("routers.sign.cmd_ask_pin", new_callable=AsyncMock) as mock_ask:
        app_context = MagicMock()
        await cmd_yes_send(mock_callback, mock_state, mock_session, app_context)
        mock_state.set_state.assert_called_with(PinState.sign_and_send)
        mock_ask.assert_called_once()

@pytest.mark.asyncio
async def test_cq_pin_digits(mock_session, mock_callback, mock_state):
    mock_state.get_data.return_value = {'pin': '12'}
    callback_data = PinCallbackData(action="3")
    
    with patch("routers.sign.cmd_ask_pin", new_callable=AsyncMock) as mock_ask:
        app_context = MagicMock()
        await cq_pin(mock_callback, callback_data, mock_state, mock_session, app_context)
        
        mock_state.update_data.assert_called_with(pin='123')
        mock_ask.assert_called_once()

# --- tests for routers/ton.py ---

@pytest.mark.asyncio
async def test_cmd_send_ton_start(mock_session, mock_callback, mock_state):
    with patch("routers.ton.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.ton.clear_state", new_callable=AsyncMock) as mock_clear, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}

        await cmd_send_ton_start(mock_callback, mock_state, mock_session)
        
        mock_clear.assert_called_once()
        mock_send.assert_called_once()

# --- tests for routers/monitoring.py ---

@pytest.mark.asyncio
async def test_handle_monitoring_message(mock_message):
    mock_message.text = "#mmwb #skynet command=ping"
    await handle_monitoring_message(mock_message)
    mock_message.answer.assert_called_with('#skynet #mmwb command=pong')

# --- tests for routers/uri.py ---

@pytest.mark.asyncio
async def test_process_remote_uri(mock_session, mock_state):
    from core.use_cases.stellar.process_uri import ProcessStellarUriResult
    
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.data = {'uri': 'web+stellar:tx?xdr=XDR'}
    
    # Create mock result object
    mock_result = ProcessStellarUriResult(
        success=True,
        xdr='XDR',
        callback_url='url',
        return_url=None,
        error_message=None
    )
    
    with patch("routers.uri.http_session_manager.get_web_request", return_value=mock_resp, new_callable=AsyncMock), \
         patch("routers.uri.ProcessStellarUri") as mock_process_uri_class, \
         patch("routers.uri.cmd_check_xdr", new_callable=AsyncMock) as mock_check, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("infrastructure.utils.common_utils.get_user_id", return_value=123):
         
        # Setup ProcessStellarUri mock
        mock_process_uri_instance = AsyncMock()
        mock_process_uri_instance.execute.return_value = mock_result
        mock_process_uri_class.return_value = mock_process_uri_instance
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await process_remote_uri(mock_session, 123, "uri_id", mock_state)
        
        mock_state.update_data.assert_called()
        mock_check.assert_called_once()

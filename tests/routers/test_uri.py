
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.uri import cmd_start_remote, process_stellar_uri, process_wc_uri

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state

@pytest.fixture
def mock_message():
    message = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.chat = MagicMock()
    message.chat.id = 123
    message.text = "text"
    return message

@pytest.mark.asyncio
async def test_cmd_start_remote(mock_session, mock_message, mock_state):
    mock_message.text = "/start uri_12345"
    
    # Mocking http_session_manager response
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.data = {'uri': 'web+stellar:tx?xdr=AAAA'}
    
    with patch("routers.uri.http_session_manager.get_web_request", new_callable=AsyncMock) as mock_get, \
         patch("routers.uri.SqlAlchemyWalletRepository") as MockWalletRepo, \
         patch("routers.uri.StellarService") as MockStellarService, \
         patch("routers.uri.ProcessStellarUri") as MockProcessUri, \
         patch("routers.uri.cmd_check_xdr", new_callable=AsyncMock) as mock_check_xdr, \
         patch("routers.uri.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.uri.my_gettext", return_value="text"), \
         patch("routers.uri.clear_state", new_callable=AsyncMock):

        mock_get.return_value = mock_response
        
        mock_use_case = MockProcessUri.return_value
        mock_result = MagicMock()
        mock_result.xdr = "XDR_CONTENT"
        mock_result.callback_url = "cb_url"
        mock_result.return_url = "ret_url"
        mock_use_case.execute = AsyncMock(return_value=mock_result)
        
        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await cmd_start_remote(mock_message, mock_state, mock_session, app_context=app_context)

        mock_use_case.execute.assert_called_once()
        mock_check_xdr.assert_called_once()
        mock_state.update_data.assert_called()

@pytest.mark.asyncio
async def test_process_stellar_uri(mock_session, mock_message, mock_state):
    mock_message.text = "web+stellar:tx?xdr=AAAA"
    
    with patch("routers.uri.SqlAlchemyWalletRepository") as MockWalletRepo, \
         patch("routers.uri.StellarService") as MockStellarService, \
         patch("routers.uri.ProcessStellarUri") as MockProcessUri, \
         patch("routers.uri.cmd_check_xdr", new_callable=AsyncMock) as mock_check_xdr, \
         patch("routers.uri.clear_state", new_callable=AsyncMock):

        mock_use_case = MockProcessUri.return_value
        mock_result = MagicMock()
        mock_result.xdr = "XDR_CONTENT"
        mock_result.callback_url = None
        mock_result.return_url = None
        mock_use_case.execute = AsyncMock(return_value=mock_result)
        
        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await process_stellar_uri(mock_message, mock_state, mock_session, app_context=app_context)

        mock_use_case.execute.assert_called_once()
        mock_check_xdr.assert_called_once()
        mock_state.update_data.assert_called()

@pytest.mark.asyncio
async def test_process_wc_uri(mock_session, mock_message, mock_state):
    mock_message.text = "wc:12345"
    
    mock_account = MagicMock()
    mock_account.account.account_id = "GKEY"

    with patch("routers.uri.stellar_get_user_account", new_callable=AsyncMock) as mock_get_account, \
         patch("routers.uri.publish_pairing_request", new_callable=AsyncMock) as mock_publish, \
         patch("routers.uri.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.uri.my_gettext", return_value="text"), \
         patch("routers.uri.clear_state", new_callable=AsyncMock), \
         patch("routers.uri.clear_last_message_id", new_callable=AsyncMock):
         
        mock_get_account.return_value = mock_account
        
        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await process_wc_uri(mock_message, mock_state, mock_session, app_context=app_context)

        mock_publish.assert_called_once()
        mock_send.assert_called_once()

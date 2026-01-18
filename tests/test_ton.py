
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.ton import (
    cmd_send_ton_start,
    cmd_send_ton_address,
    cmd_send_ton_sum,
    cmd_send_ton_confirm,
    StateSendTon
)

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state

@pytest.fixture
def mock_callback():
    callback = AsyncMock(spec=types.CallbackQuery)
    # Fix: Make sure methods starting with 'answer' are AsyncMock if not covered by spec correctly or if spec is not enough
    callback.answer = AsyncMock() 
    callback.from_user = MagicMock()
    callback.from_user.id = 123
    callback.message = AsyncMock()
    callback.message.chat.id = 123
    return callback

@pytest.fixture
def mock_message():
    message = AsyncMock(spec=types.Message)
    message.delete = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.chat = MagicMock()
    message.chat.id = 123
    message.text = "text"
    return message

@pytest.mark.asyncio
async def test_cmd_send_ton_start(mock_session, mock_callback, mock_state):
    with patch("routers.ton.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.ton.clear_state", new_callable=AsyncMock):

        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await cmd_send_ton_start(mock_callback, mock_state, mock_session, app_context=app_context)

        mock_send.assert_called_once()
        mock_state.set_state.assert_called_with(StateSendTon.sending_for)
        mock_callback.answer.assert_called_once()  # Call expected

@pytest.mark.asyncio
async def test_cmd_send_ton_address(mock_session, mock_message, mock_state):
    mock_message.text = "EQD__________________________________________xxx" # 48 chars
    
    with patch("routers.ton.send_message", new_callable=AsyncMock) as mock_send:

        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await cmd_send_ton_address(mock_message, mock_state, mock_session, app_context=app_context)

        mock_state.update_data.assert_called_with(recipient_address=mock_message.text)
        mock_state.set_state.assert_called_with(StateSendTon.sending_sum)
        mock_message.delete.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_ton_sum(mock_session, mock_message, mock_state):
    mock_message.text = "10.5"
    mock_state.get_data.return_value = {'recipient_address': 'addr'}

    with patch("routers.ton.send_message", new_callable=AsyncMock) as mock_send:

        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await cmd_send_ton_sum(mock_message, mock_state, mock_session, app_context=app_context)

        mock_state.update_data.assert_called_with(amount=10.5)
        mock_state.set_state.assert_called_with(StateSendTon.sending_confirmation)
        mock_message.delete.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_ton_confirm(mock_session, mock_callback, mock_state):
    mock_state.get_data.return_value = {'recipient_address': 'addr', 'amount': 10.5}

    # Patching where it is DEFINED because it is imported inside the function
    with patch("infrastructure.services.wallet_secret_service.SqlAlchemyWalletSecretService") as MockSecretService, \
         patch("routers.ton.TonService") as MockTonService, \
         patch("routers.ton.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.ton.clear_state", new_callable=AsyncMock):

        mock_secret_service = MockSecretService.return_value
        mock_secret_service.is_ton_wallet = AsyncMock(return_value=True)
        mock_secret_service.get_ton_mnemonic = AsyncMock(return_value="mnemonic")
        
        mock_ton_service = MockTonService.return_value
        mock_ton_service.send_ton = AsyncMock(return_value=True) # Success
        
        app_context = MagicMock()
        app_context.localization_service.get_text.return_value = 'text'

        await cmd_send_ton_confirm(mock_callback, mock_state, mock_session, app_context=app_context)

        mock_ton_service.send_ton.assert_called_with('addr', 10.5)
        # Should send: sending msg, success msg
        assert mock_send.call_count >= 2


import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.send import cmd_send_start, cmd_send_token, cmd_send_for, StateSendToken, cmd_send_choose_token, cmd_send_get_sum, cmd_create_account, handle_docs_photo
from routers.receive import cmd_receive
from routers.cheque import cmd_create_cheque, StateCheque, cmd_cheque_get_sum, cmd_cheque_count, cmd_cancel_cheque, cmd_start_cheque, cmd_cheque_execute
from stellar_sdk import Asset

# --- tests for routers/send.py ---

@pytest.mark.asyncio
async def test_cmd_send_start(mock_session, mock_callback, mock_state):
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_send_start(mock_callback, mock_state, mock_session)
        mock_send.assert_called_once()
        # mock_callback.answer.assert_called_once() # Answer not called in cmd_send_start

@pytest.mark.asyncio
async def test_cmd_send_token(mock_session, mock_message, mock_state):
    # Pass required arguments for logic function
    send_asset = MagicMock(spec=Asset)
    send_asset.code = "XLM"
    send_asset.issuer = None
    
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.send.stellar_check_account", new_callable=AsyncMock), \
         patch("routers.send.cmd_send_04", new_callable=AsyncMock) as mock_send_04:
         
        await cmd_send_token(mock_message, mock_state, mock_session, 
                             send_for="GAR...", send_asset=send_asset, send_sum=10.0, send_memo="memo")
        
        mock_state.update_data.assert_called()
        mock_send_04.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_for(mock_session, mock_message, mock_state):
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_send_for(mock_message, mock_state, mock_session)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_choose_token(mock_session, mock_callback, mock_state):
    mock_bal = MagicMock()
    mock_bal.asset_code = "XLM"
    mock_bal.balance = "100.0"
    
    # Mock state data including send_address
    mock_state.get_data.return_value = {"send_address": "GADDR..."}
    
    with patch("routers.send.stellar_get_balances", new_callable=AsyncMock, return_value=[mock_bal]), \
         patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        
        await cmd_send_choose_token(mock_callback, mock_state, mock_session)
        mock_send.assert_called_once()

# --- tests for routers/receive.py ---

@pytest.mark.asyncio
async def test_cmd_receive(mock_session, mock_callback, mock_state):
    with patch("routers.receive.stellar_get_user_account", new_callable=AsyncMock) as mock_get_acc, \
         patch("routers.receive.create_beautiful_code") as mock_create_qr, \
         patch("routers.receive.cmd_info_message", new_callable=AsyncMock) as mock_info:
         
        mock_acc = MagicMock()
        mock_acc.account.account_id = "GADDR"
        mock_get_acc.return_value = mock_acc
        
        await cmd_receive(mock_callback, mock_state, mock_session)
        
        mock_create_qr.assert_called_once()
        args, _ = mock_create_qr.call_args
        assert args[1] == "GADDR"

# --- tests for routers/cheque.py ---

@pytest.mark.asyncio
async def test_cmd_create_cheque(mock_session, mock_callback, mock_state):
    with patch("routers.cheque.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_create_cheque(mock_callback, mock_state, mock_session)
        mock_state.set_state.assert_called_with(StateCheque.sending_sum)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_cheque_get_sum(mock_session, mock_message, mock_state):
    mock_message.text = "10.0"
    mock_state.get_data.return_value = {"send_sum": 0.0}
    with patch("routers.cheque.cmd_cheque_show", new_callable=AsyncMock) as mock_show:
        await cmd_cheque_get_sum(mock_message, mock_state, mock_session)
        mock_state.update_data.assert_called_with(send_sum=10.0)
        mock_show.assert_called_once()

# --- NEW TESTS FOR SEND ROUTER ---

@pytest.mark.asyncio
async def test_cmd_send_get_sum_valid(mock_session, mock_message, mock_state):
    mock_message.text = "10.5"
    mock_state.get_data.return_value = {"send_asset_code": "XLM", "send_asset_issuer": "GKB..."}
    
    with patch("routers.send.cmd_send_04", new_callable=AsyncMock) as mock_send_04, \
         patch("routers.send.db_get_user") as mock_db_get_user:
        
        mock_user = MagicMock()
        mock_user.can_5000 = 1
        mock_db_get_user.return_value = mock_user

        await cmd_send_get_sum(mock_message, mock_state, mock_session)
        mock_state.update_data.assert_called_with(send_sum=10.5)
        mock_send_04.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_send_get_sum_limit_exceeded(mock_session, mock_message, mock_state):
    mock_message.text = "6000"
    mock_state.get_data.return_value = {"msg": "previous_msg"}
    
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.send.db_get_user") as mock_db_get_user:
        
        mock_user = MagicMock()
        mock_user.can_5000 = 0 
        mock_db_get_user.return_value = mock_user

        await cmd_send_get_sum(mock_message, mock_state, mock_session)
        
        mock_send.assert_called_once()
        mock_state.update_data.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_get_memo(mock_session, mock_callback, mock_state):
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.send.get_kb_return"):

        from routers.send import cmd_get_memo
        await cmd_get_memo(mock_callback, mock_state, mock_session)
        
        mock_state.set_state.assert_called_with(StateSendToken.sending_memo)
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_send_memo(mock_session, mock_message, mock_state):
    mock_message.text = "A" * 30
    
    with patch("routers.send.cmd_send_04", new_callable=AsyncMock) as mock_send_04, \
         patch("routers.send.cut_text_to_28_bytes", return_value="A"*28) as mock_cut:
        
        from routers.send import cmd_send_memo
        await cmd_send_memo(mock_message, mock_state, mock_session)
        
        mock_cut.assert_called_with("A"*30)
        mock_state.update_data.assert_called_with(memo="A"*28)
        mock_send_04.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_create_account(mock_session, mock_state):
    user_id = 123
    mock_state.get_data.return_value = {"activate_sum": 10, "send_address": "GNEW"}
    
    mock_balance = MagicMock()
    mock_balance.asset_code = "USD"
    mock_balance.asset_issuer = "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = "GSEND"

    with patch("routers.send.stellar_get_balances", new_callable=AsyncMock, return_value=[mock_balance]), \
         patch("routers.send.stellar_get_user_account", new_callable=AsyncMock, return_value=mock_user_account), \
         patch("routers.send.stellar_pay", new_callable=AsyncMock, return_value="XDR_STRING") as mock_pay, \
         patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:

        await cmd_create_account(user_id, mock_state, mock_session)
        
        mock_pay.assert_called_once()
        _, kwargs = mock_pay.call_args
        assert kwargs.get('create') is True
        assert mock_pay.call_args[0][3] == 10
        
        mock_state.update_data.assert_called()
        mock_send.assert_called()


@pytest.mark.asyncio
async def test_handle_docs_photo_valid_address(mock_session, mock_message, mock_state):
    mock_message.photo = [MagicMock()]
    mock_bot = AsyncMock()
    
    with patch("routers.send.global_data") as mock_gd_module, \
         patch("routers.send.decode_qr_code", return_value="GVALIDADDRESS"), \
         patch("routers.send.is_valid_stellar_address", return_value=True), \
         patch("routers.send.cmd_send_for", new_callable=AsyncMock) as mock_send_for:
        
        mock_gd_module.bot = mock_bot
        
        await handle_docs_photo(mock_message, mock_state, mock_session)
        
        mock_state.update_data.assert_called_with(qr="GVALIDADDRESS", last_message_id=0)
        mock_send_for.assert_called_once()


# --- NEW TESTS FOR CHEQUE ROUTER ---

@pytest.mark.asyncio
async def test_cmd_cheque_count(mock_session, mock_message, mock_state):
    with patch("routers.cheque.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_cheque_count(mock_message, mock_state, mock_session)
        mock_state.set_state.assert_called_with(StateCheque.sending_count)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_cheque_execute(mock_session, mock_callback, mock_state):
    mock_state.get_data.return_value = {"send_sum": 10.0, "send_count": 2}
    
    with patch("routers.cheque.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.cheque.get_kb_yesno_send_xdr") as mock_kb:
         
         await cmd_cheque_execute(mock_callback, mock_state, mock_session)
         mock_state.update_data.assert_called()
         mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cancel_cheque(mock_session, mock_callback, mock_state):
    mock_state.get_data.return_value = {
        "cheque_uuid": "UUID", 
        "cheque_sum": 10, 
        "cheque_count": 5, 
        "cheque_asset_code": "XLM",
        "cheque_asset_issuer": "native"
    }
    
    mock_cheque = MagicMock(uuid="UUID", state='active')
    mock_cheque.cheque_count = 5 
    mock_cheque.cheque_status = 'active'
    mock_cheque.cheque_amount = 5.0
    
    with patch("routers.cheque.db_get_cheque", return_value=mock_cheque), \
         patch("routers.cheque.db_get_cheque_receive_count", return_value=0), \
         patch("routers.cheque.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.cheque.stellar_pay", new_callable=AsyncMock, return_value="XDR_REFUND") as mock_pay, \
         patch("routers.cheque.stellar_sign", return_value="XDR_SIGNED"), \
         patch("routers.cheque.stellar_get_master") as mock_master, \
         patch("routers.cheque.async_stellar_send", new_callable=AsyncMock), \
         patch("routers.cheque.cmd_info_message", new_callable=AsyncMock), \
         patch("routers.cheque.db_reset_balance"), \
         patch("routers.cheque.db_get_default_wallet") as mock_wallet:
         
         mock_wallet.return_value.public_key = "GOWNER"
         
         from routers.cheque import cmd_cancel_cheque
         await cmd_cancel_cheque(mock_session, mock_callback.from_user.id, "UUID", mock_state)
         
         mock_pay.assert_called_once()
         mock_state.update_data.assert_called()


@pytest.mark.asyncio
async def test_cmd_start_cheque_activation(mock_session, mock_message, mock_state):
    mock_message.text = "/start cheque_UUID_PWD"
    
    mock_cheque = MagicMock(uuid="UUID", state='active')
    mock_cheque.cheque_count = 5
    mock_cheque.cheque_status = 0
    mock_cheque.cheque_amount = 10
    mock_cheque.cheque_comment = "comment"

    with patch("routers.cheque.db_get_cheque", return_value=mock_cheque), \
         patch("routers.cheque.db_get_cheque_receive_count", return_value=0), \
         patch("routers.cheque.send_message", new_callable=AsyncMock) as mock_send:
         
         await cmd_start_cheque(mock_message, mock_state, mock_session)
         
         mock_state.update_data.assert_called()
         mock_send.assert_called()

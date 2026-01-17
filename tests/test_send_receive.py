
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
    
    with patch("core.use_cases.wallet.get_balance.GetWalletBalance") as MockGetBalance, \
         patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        
        mock_use_case = MockGetBalance.return_value
        mock_use_case.execute = AsyncMock(return_value=[mock_bal])
        
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



# --- NEW TESTS FOR SEND ROUTER ---

@pytest.mark.asyncio
async def test_cmd_send_get_sum_valid(mock_session, mock_message, mock_state):
    mock_message.text = "10.5"
    mock_state.get_data.return_value = {"send_asset_code": "XLM", "send_asset_issuer": "GKB..."}
    
    mock_user = MagicMock()
    mock_user.can_5000 = 1
    
    with patch("routers.send.cmd_send_04", new_callable=AsyncMock) as mock_send_04, \
         patch("infrastructure.persistence.sqlalchemy_user_repository.SqlAlchemyUserRepository") as MockRepo:
        
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_user)

        await cmd_send_get_sum(mock_message, mock_state, mock_session)
        mock_state.update_data.assert_called_with(send_sum=10.5)
        mock_send_04.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_send_get_sum_limit_exceeded(mock_session, mock_message, mock_state):
    mock_message.text = "6000"
    mock_state.get_data.return_value = {"msg": "previous_msg"}
    
    mock_user = MagicMock()
    mock_user.can_5000 = 0
    
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send, \
         patch("infrastructure.persistence.sqlalchemy_user_repository.SqlAlchemyUserRepository") as MockRepo:
        
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_by_id = AsyncMock(return_value=mock_user)

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

    with patch("core.use_cases.payment.send_payment.SendPayment") as MockSendPayment, \
         patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:

        mock_use_case = MockSendPayment.return_value
        mock_use_case.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR_CREATE"))

        await cmd_create_account(user_id, mock_state, mock_session)
        
        mock_use_case.execute.assert_called_once()
        _, kwargs = mock_use_case.execute.call_args
        assert kwargs.get('create_account') is True
        assert kwargs.get('amount') == 10.0
        
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




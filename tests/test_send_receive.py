
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
async def test_cmd_send_start(mock_session, mock_callback, mock_state, mock_app_context):
    """Test send start handler: should display send menu."""
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_send_start(123, mock_state, mock_session, app_context=mock_app_context)
        mock_send.assert_called_once()
        # Verify app_context is passed to send_message
        _, kwargs = mock_send.call_args
        assert kwargs.get('app_context') is mock_app_context, "app_context must be passed to send_message"

@pytest.mark.asyncio
async def test_cmd_send_token(mock_session, mock_message, mock_state, mock_app_context):
    """Test send token handler: should process token selection and proceed to next step."""
    send_asset = MagicMock(spec=Asset)
    send_asset.code = "XLM"
    send_asset.issuer = None
    
    with patch("routers.send.stellar_check_account", new_callable=AsyncMock), \
         patch("routers.send.cmd_send_04", new_callable=AsyncMock) as mock_send_04:
         
        await cmd_send_token(mock_message, mock_state, mock_session, 
                             send_for="GAR...", send_asset=send_asset, send_sum=10.0, send_memo="memo", app_context=mock_app_context)
        
        mock_state.update_data.assert_called()
        mock_send_04.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_for(mock_session, mock_message, mock_state, mock_app_context):
    """Test send for handler: should display address input form."""
    # Configure repository factory
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=MagicMock(is_free=False))
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_send_for(mock_message, mock_state, mock_session, mock_app_context)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_choose_token(mock_session, mock_callback, mock_state, mock_app_context):
    """Test choose token handler: should display available balances for sending."""
    mock_bal = MagicMock()
    mock_bal.asset_code = "XLM"
    mock_bal.balance = "100.0"
    
    # Mock state data including send_address
    mock_state.get_data.return_value = {"send_address": "GADDR..."}
    
    # Configure use_case_factory to return mock GetWalletBalance use case
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=[mock_bal])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_use_case
    
    mock_message = MagicMock()
    mock_message.from_user.id = 123
    
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_send_choose_token(mock_message, mock_state, mock_session, app_context=mock_app_context)
        mock_send.assert_called_once()
        
        # Verify balance use case was called twice (user + recipient)
        assert mock_use_case.execute.call_count == 2

# --- tests for routers/receive.py ---

@pytest.mark.asyncio
async def test_cmd_receive(mock_session, mock_callback, mock_state, mock_app_context):
    """Test receive callback handler: should get user account and create QR code."""
    # Arrange: setup mock account data
    mock_acc = MagicMock()
    mock_acc.account.account_id = "GADDR1234567890TESTACCOUNT"
    
    # Configure bot.send_photo mock
    mock_send_photo = AsyncMock()
    mock_app_context.bot.send_photo = mock_send_photo
    
    # Configure dispatcher.storage mocks
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.set_data = AsyncMock()
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    
    with patch("routers.receive.stellar_get_user_account", new_callable=AsyncMock) as mock_get_acc, \
         patch("routers.start_msg.get_kb_return", return_value=MagicMock()):
        mock_get_acc.return_value = mock_acc
        
        # Act: call the handler
        await cmd_receive(mock_callback, mock_state, mock_session, app_context=mock_app_context)
        
        # Assert: verify photo was sent with correct file
        mock_send_photo.assert_called_once()
        args, kwargs = mock_send_photo.call_args
        photo = kwargs.get('photo')
        assert photo.path == f"qr/{mock_acc.account.account_id}.png"
        
        # Verify callback was answered
        mock_callback.answer.assert_called_once()




# --- NEW TESTS FOR SEND ROUTER ---

@pytest.mark.asyncio
async def test_cmd_send_get_sum_valid(mock_session, mock_message, mock_state, mock_app_context):
    """Test send get sum handler with valid amount."""
    mock_message.text = "10.5"
    mock_state.get_data.return_value = {"send_asset_code": "XLM", "send_asset_issuer": "GKB..."}
    
    mock_user = MagicMock()
    mock_user.can_5000 = 1
    
    # Configure repository
    mock_repo_instance = MagicMock()
    mock_repo_instance.get_by_id = AsyncMock(return_value=mock_user)
    mock_app_context.repository_factory.get_user_repository.return_value = mock_repo_instance
    
    with patch("routers.send.cmd_send_04", new_callable=AsyncMock) as mock_send_04:
        await cmd_send_get_sum(mock_message, mock_state, mock_session, mock_app_context)
        mock_state.update_data.assert_called_with(send_sum=10.5)
        mock_send_04.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_send_get_sum_limit_exceeded(mock_session, mock_message, mock_state, mock_app_context):
    """Test send get sum handler when amount exceeds limit."""
    mock_message.text = "6000"
    mock_state.get_data.return_value = {"msg": "previous_msg"}
    
    mock_user = MagicMock()
    mock_user.can_5000 = 0
    
    # Configure repository
    mock_repo_instance = MagicMock()
    mock_repo_instance.get_by_id = AsyncMock(return_value=mock_user)
    mock_app_context.repository_factory.get_user_repository.return_value = mock_repo_instance
    
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_send_get_sum(mock_message, mock_state, mock_session, mock_app_context)
        
        mock_send.assert_called_once()
        mock_state.update_data.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_get_memo(mock_session, mock_callback, mock_state, mock_app_context):
    """Test get memo handler: should set state to sending_memo."""
    from routers.send import cmd_get_memo
    
    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_get_memo(mock_callback, mock_state, mock_session, mock_app_context)
        
        mock_state.set_state.assert_called_with(StateSendToken.sending_memo)
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_send_memo(mock_session, mock_message, mock_state, mock_app_context):
    """Test send memo handler: should truncate memo to 28 bytes."""
    from routers.send import cmd_send_memo
    mock_message.text = "A" * 30
    
    with patch("routers.send.cmd_send_04", new_callable=AsyncMock) as mock_send_04, \
         patch("routers.send.cut_text_to_28_bytes", return_value="A"*28) as mock_cut:
        
        await cmd_send_memo(mock_message, mock_state, mock_session, mock_app_context)
        
        mock_cut.assert_called_with("A"*30)
        mock_state.update_data.assert_called_with(memo="A"*28)
        mock_send_04.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_create_account(mock_session, mock_state, mock_app_context):
    """Test create account handler: should create Stellar account with initial balance."""
    user_id = 123
    mock_state.get_data.return_value = {"activate_sum": 10, "send_address": "GNEW"}

    # Configure use_case_factory to return mock SendPayment use case
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR_CREATE"))
    mock_app_context.use_case_factory.create_send_payment.return_value = mock_use_case

    with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_create_account(user_id, mock_state, mock_session, app_context=mock_app_context)
        
        # Verify use case was called with create_account=True
        mock_use_case.execute.assert_called_once()
        _, kwargs = mock_use_case.execute.call_args
        assert kwargs.get('create_account') is True
        assert kwargs.get('amount') == 10.0
        
        mock_state.update_data.assert_called()
        mock_send.assert_called()


@pytest.mark.asyncio
async def test_handle_docs_photo_valid_address(mock_session, mock_message, mock_state, mock_app_context):
    """Test photo handler: creates real QR code, decodes it, validates address, and proceeds with send flow."""
    import os
    import tempfile
    import shutil
    from routers.receive import create_beautiful_code
    
    # Use real valid Stellar address from codebase examples
    valid_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    
    # Setup state mockup to actually store data so subsequent calls to get_data work correctly
    state_data = {}
    async def update_data(**kwargs):
        state_data.update(kwargs)
        return state_data
    async def get_data():
        return state_data
    
    mock_state.update_data.side_effect = update_data
    mock_state.get_data.side_effect = get_data
    
    # Create real QR code image in temp directory
    temp_dir = tempfile.mkdtemp()
    qr_filename = f"{mock_message.from_user.id}.jpg"
    qr_path = os.path.join(temp_dir, qr_filename)
    
    try:
        # Generate real QR code with valid Stellar address
        create_beautiful_code(qr_path, valid_address)
        
        # Configure mock_message
        mock_message.photo = [MagicMock()]
        # mock_message.from_user.id is already set in conftest, but ensure it matches
        user_id = mock_message.from_user.id
        
        # Mock bot.download to copy our QR file to the expected 'qr/' directory
        async def mock_download(photo, destination):
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy(qr_path, destination)
        
        mock_app_context.bot.download = AsyncMock(side_effect=mock_download)
        
        # Mock stellar_check_account (external Stellar Network API)
        with patch("routers.send.stellar_check_account", new_callable=AsyncMock) as mock_check:
            # Configure stellar_check_account to return valid account
            mock_account = MagicMock()
            mock_account.account_id = valid_address
            mock_account.memo = None
            mock_check.return_value = mock_account
            
            # Configure repository mock for wallet check
            mock_wallet_repo = MagicMock()
            mock_wallet_repo.get_default_wallet = AsyncMock(return_value=MagicMock(is_free=False))
            mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
            
            # Configure use case factory for GetWalletBalance
            mock_balance_uc = MagicMock()
            mock_balance_uc.execute = AsyncMock(return_value=[])
            mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
            
            # Mock send_message (Telegram API)
            with patch("routers.send.send_message", new_callable=AsyncMock) as mock_send:
                # Execute handler - all local functions (decode_qr_code, is_valid_stellar_address, cmd_send_for) work for real
                await handle_docs_photo(mock_message, mock_state, mock_session, app_context=mock_app_context)
                
                # Verify real QR decode happened and address was validated and stored
                assert state_data.get('qr') == valid_address
                assert state_data.get('send_address') == valid_address
                
                # Verify send_message was called (cmd_send_choose_token executed)
                assert mock_send.called
                
    finally:
        # Cleanup temp files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        # Cleanup qr directory
        if os.path.exists('qr'):
            for f in os.listdir('qr'):
                if f.startswith(str(user_id)):
                    try:
                        os.remove(os.path.join('qr', f))
                    except:
                        pass

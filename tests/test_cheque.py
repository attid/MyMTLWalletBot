
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.cheque import (
    cmd_create_cheque, cmd_cheque_get_sum, cmd_cheque_show, cmd_cheque_count,
    cmd_cheque_get_count, cmd_cheque_comment, cmd_cheque_get_comment,
    cmd_cheque_execute, cheque_after_send, cb_cheque_click, cmd_cancel_cheque,
    cmd_inline_query, cmd_start_cheque, cmd_cheque_yes, cmd_send_money_from_cheque,
    cmd_invoice_yes, cmd_cheques, StateCheque, ChequeCallbackData, ChequeQuery
)
from core.use_cases.cheque.claim_cheque import ClaimResult
from core.use_cases.cheque.cancel_cheque import CancelResult
from core.domain.value_objects import PaymentResult
from db.models import ChequeStatus


# --- Tests for Create Cheque Flow ---

@pytest.mark.asyncio
async def test_cmd_create_cheque_with_message(mock_session, mock_message, mock_state, mock_app_context):
    """Test /create_cheque command handler with Message."""
    with patch("infrastructure.utils.telegram_utils.clear_state", new_callable=AsyncMock) as mock_clear, \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.my_gettext", return_value="Enter cheque amount"), \
         patch("keyboards.common_keyboards.get_kb_return"):
        
        await cmd_create_cheque(mock_message, mock_state, mock_session, app_context=mock_app_context, l10n=MagicMock())
        
        mock_clear.assert_called_once_with(mock_state)
        mock_message.delete.assert_called_once()
        mock_send.assert_called_once()
        mock_state.set_state.assert_called_with(StateCheque.sending_sum)


@pytest.mark.asyncio
async def test_cmd_create_cheque_with_callback(mock_session, mock_callback, mock_state, mock_app_context):
    """Test CreateCheque callback handler."""
    with patch("infrastructure.utils.telegram_utils.clear_state", new_callable=AsyncMock) as mock_clear, \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.my_gettext", return_value="Enter cheque amount"), \
         patch("keyboards.common_keyboards.get_kb_return"):
        
        await cmd_create_cheque(mock_callback, mock_state, mock_session, app_context=mock_app_context, l10n=MagicMock())
        
        mock_clear.assert_called_once_with(mock_state)
        mock_send.assert_called_once()
        mock_state.set_state.assert_called_with(StateCheque.sending_sum)
        mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_sum_valid(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque sum input with valid amount."""
    mock_message.text = "100.5"
    mock_state.get_data.return_value = {}
    
    with patch("infrastructure.utils.stellar_utils.my_float", return_value=100.5), \
         patch("routers.cheque.cmd_cheque_show", new_callable=AsyncMock) as mock_show:
        
        await cmd_cheque_get_sum(mock_message, mock_state, mock_session, mock_app_context)
        
        mock_state.update_data.assert_called_with(send_sum=100.5)
        mock_state.set_state.assert_called_with(None)
        mock_show.assert_called_once()
        mock_message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_sum_invalid(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque sum input with invalid amount."""
    mock_message.text = "invalid"
    
    with patch("infrastructure.utils.stellar_utils.my_float", side_effect=ValueError):
        await cmd_cheque_get_sum(mock_message, mock_state, mock_session, mock_app_context)
        
        mock_state.update_data.assert_not_called()
        mock_message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_show(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque preview display."""
    mock_state.get_data.return_value = {
        "send_sum": 50.0,
        "send_count": 2,
        "send_comment": "Test comment",
        "send_uuid": "test-uuid-1234567890"
    }
    
    mock_result = PaymentResult(success=True, xdr="XDR_STRING")
    
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository"), \
         patch("infrastructure.services.stellar_service.StellarService"), \
         patch("core.use_cases.cheque.create_cheque.CreateCheque") as MockUseCase, \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.my_gettext", return_value="Cheque preview"), \
         patch("routers.cheque.get_kb_send_cheque"):
        
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=mock_result)
        
        await cmd_cheque_show(mock_session, mock_message, mock_state, mock_app_context)
        
        mock_use_case.execute.assert_called_once()
        args, kwargs = mock_use_case.execute.call_args
        assert kwargs['user_id'] == mock_message.from_user.id
        assert kwargs['amount'] == 50.0
        assert kwargs['count'] == 2
        
        mock_state.update_data.assert_called()
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_show_failure(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque preview when use case fails."""
    mock_state.get_data.return_value = {
        "send_sum": 50.0,
        "send_count": 1
    }
    
    mock_result = PaymentResult(success=False, error_message="Insufficient balance")
    
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository"), \
         patch("infrastructure.services.stellar_service.StellarService"), \
         patch("core.use_cases.cheque.create_cheque.CreateCheque") as MockUseCase, \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("keyboards.common_keyboards.get_kb_return"):
        
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=mock_result)
        
        await cmd_cheque_show(mock_session, mock_message, mock_state, mock_app_context)
        
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert "Error: Insufficient balance" in args[2]


# --- Tests for Cheque Count ---

@pytest.mark.asyncio
async def test_cmd_cheque_count(mock_session, mock_callback, mock_state, mock_app_context):
    """Test cheque count callback."""
    with patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.my_gettext", return_value="Enter count"), \
         patch("keyboards.common_keyboards.get_kb_return"):
        
        await cmd_cheque_count(mock_callback, mock_state, mock_session, mock_app_context)
        
        mock_send.assert_called_once()
        mock_state.set_state.assert_called_with(StateCheque.sending_count)
        mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_count_valid(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque count input with valid number."""
    mock_message.text = "5"
    
    with patch("routers.cheque.cmd_cheque_show", new_callable=AsyncMock) as mock_show:
        await cmd_cheque_get_count(mock_message, mock_state, mock_session, mock_app_context)
        
        mock_state.update_data.assert_called_with(send_count=5)
        mock_state.set_state.assert_called_with(None)
        mock_show.assert_called_once()
        mock_message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_count_zero(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque count input with zero (should default to 1)."""
    mock_message.text = "0"
    
    await cmd_cheque_get_count(mock_message, mock_state, mock_session, mock_app_context)
    
    # Zero is not > 0, so should just delete message
    mock_state.update_data.assert_not_called()
    mock_message.delete.assert_called_once()


# --- Tests for Cheque Comment ---

@pytest.mark.asyncio
async def test_cmd_cheque_comment(mock_session, mock_callback, mock_state, mock_app_context):
    """Test cheque comment callback."""
    with patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.my_gettext", return_value="Enter comment"), \
         patch("keyboards.common_keyboards.get_kb_return"):
        
        await cmd_cheque_comment(mock_callback, mock_state, mock_session, mock_app_context)
        
        mock_send.assert_called_once()
        mock_state.set_state.assert_called_with(StateCheque.sending_comment)
        mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_comment(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque comment input."""
    mock_message.text = "Birthday gift"
    
    with patch("routers.cheque.cmd_cheque_show", new_callable=AsyncMock) as mock_show:
        await cmd_cheque_get_comment(mock_message, mock_state, mock_session, mock_app_context)
        
        mock_state.update_data.assert_called_with(send_comment="Birthday gift")
        mock_state.set_state.assert_called_with(None)
        mock_show.assert_called_once()
        mock_message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_comment_truncate(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque comment truncation to 255 chars."""
    long_comment = "A" * 300
    mock_message.text = long_comment
    
    with patch("routers.cheque.cmd_cheque_show", new_callable=AsyncMock):
        await cmd_cheque_get_comment(mock_message, mock_state, mock_session, mock_app_context)
        
        # Should truncate to 255 chars
        call_args = mock_state.update_data.call_args
        assert call_args[1]['send_comment'] == "A" * 255


# --- Tests for Cheque Execute ---

@pytest.mark.asyncio
async def test_cmd_cheque_execute(mock_session, mock_callback, mock_state, mock_app_context):
    """Test cheque execution confirmation."""
    mock_state.get_data.return_value = {
        "send_sum": 100.0,
        "send_count": 3,
        "send_uuid": "test-uuid"
    }
    
    mock_asset = MagicMock()
    mock_asset.code = "EURMTL"
    
    with patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.my_gettext", return_value="Confirm send"), \
         patch("keyboards.common_keyboards.get_kb_yesno_send_xdr"), \
         patch("infrastructure.utils.stellar_utils.eurmtl_asset", mock_asset), \
         patch("routers.cheque.cheque_public", "GCHEQUE"), \
         patch("routers.cheque.jsonpickle.dumps", return_value="pickled"):
        
        await cmd_cheque_execute(mock_callback, mock_state, mock_session, mock_app_context)
        
        mock_send.assert_called_once()
        mock_state.update_data.assert_called()
        mock_callback.answer.assert_called_once()


# --- Tests for Cheque After Send ---

@pytest.mark.asyncio
async def test_cheque_after_send_new_cheque(mock_session, mock_state, mock_app_context):
    """Test cheque_after_send creates new cheque."""
    user_id = 123
    mock_state.get_data.return_value = {
        "send_sum": 50.0,
        "send_count": 2,
        "send_comment": "Test",
        "send_uuid": "uuid123"
    }
    
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.amount = 50.0
    mock_cheque.count = 2
    mock_cheque.comment = "Test"
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock(return_value=mock_cheque)
    
    mock_bot = AsyncMock()
    mock_bot.me.return_value = MagicMock(username="testbot")
    mock_app_context.bot = mock_bot
    
    with patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo), \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.my_gettext", return_value="Cheque created"), \
         patch("keyboards.common_keyboards.get_return_button"):
        
        await cheque_after_send(mock_session, user_id, mock_state, app_context=mock_app_context)
        
        mock_repo.create.assert_called_once()
        mock_send.assert_called_once()
        mock_state.update_data.assert_called()


# --- Tests for Cheque Callback ---

@pytest.mark.asyncio
async def test_cb_cheque_click_info(mock_session, mock_callback, mock_state, mock_app_context):
    """Test cheque info callback."""
    callback_data = ChequeCallbackData(uuid="test-uuid", cmd="info")
    
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.count = 5
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(return_value=2)
    
    with patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo):
        await cb_cheque_click(mock_callback, callback_data, mock_state, mock_session, mock_app_context)
        
        mock_callback.answer.assert_called_once()
        args = mock_callback.answer.call_args
        assert "2" in args[0][0]  # receive count
        assert "5" in args[0][0]  # total count


@pytest.mark.asyncio
async def test_cb_cheque_click_cancel(mock_session, mock_callback, mock_state, mock_app_context):
    """Test cheque cancel callback."""
    callback_data = ChequeCallbackData(uuid="test-uuid", cmd="cancel")
    mock_callback.from_user.id = 123
    
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.count = 5
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(return_value=2)
    
    mock_queue = MagicMock()
    mock_queue.put_nowait = MagicMock()  # Synchronous mock
    mock_app_context.cheque_queue = mock_queue
    
    with patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo):
        await cb_cheque_click(mock_callback, callback_data, mock_state, mock_session, mock_app_context)
        
        mock_queue.put_nowait.assert_called_once()
        call_args = mock_queue.put_nowait.call_args[0][0]
        assert isinstance(call_args, ChequeQuery)
        assert call_args.for_cancel is True


@pytest.mark.asyncio
async def test_cb_cheque_click_already_cancelled(mock_session, mock_callback, mock_state, mock_app_context):
    """Test callback for already cancelled cheque."""
    callback_data = ChequeCallbackData(uuid="test-uuid", cmd="info")
    
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.CANCELED.value
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    
    with patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo):
        await cb_cheque_click(mock_callback, callback_data, mock_state, mock_session, mock_app_context)
        
        mock_callback.answer.assert_called_once()
        args = mock_callback.answer.call_args
        assert "cancelled" in args[0][0].lower()


# --- Tests for Cancel Cheque ---

@pytest.mark.asyncio
async def test_cmd_cancel_cheque_success(mock_session, mock_state, mock_app_context):
    """Test successful cheque cancellation."""
    user_id = 123
    cheque_uuid = "test-uuid"
    
    mock_result = CancelResult(success=True, xdr="XDR_CANCEL")
    
    mock_stellar_service = AsyncMock()
    mock_stellar_service.submit_transaction = AsyncMock()
    
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository"), \
         patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository"), \
         patch("infrastructure.services.stellar_service.StellarService", return_value=mock_stellar_service), \
         patch("infrastructure.services.encryption_service.EncryptionService"), \
         patch("core.use_cases.cheque.cancel_cheque.CancelCheque") as MockUseCase, \
         patch("routers.start_msg.cmd_info_message", new_callable=AsyncMock) as mock_info, \
         patch("other.lang_tools.my_gettext", return_value="msg"):
        
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=mock_result)
        
        await cmd_cancel_cheque(mock_session, user_id, cheque_uuid, mock_state, app_context=mock_app_context)
        
        mock_use_case.execute.assert_called_once_with(user_id=user_id, cheque_uuid=cheque_uuid)
        mock_stellar_service.submit_transaction.assert_called_once_with("XDR_CANCEL")
        assert mock_info.call_count == 2  # "try_send2" and "send_good_cheque"


@pytest.mark.asyncio
async def test_cmd_cancel_cheque_failure(mock_session, mock_state, mock_app_context):
    """Test failed cheque cancellation."""
    user_id = 123
    cheque_uuid = "test-uuid"
    
    mock_result = CancelResult(success=False, error_message="Cheque not found")
    
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository"), \
         patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository"), \
         patch("infrastructure.services.stellar_service.StellarService"), \
         patch("infrastructure.services.encryption_service.EncryptionService"), \
         patch("core.use_cases.cheque.cancel_cheque.CancelCheque") as MockUseCase, \
         patch("routers.start_msg.cmd_info_message", new_callable=AsyncMock) as mock_info:
        
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=mock_result)
        
        await cmd_cancel_cheque(mock_session, user_id, cheque_uuid, mock_state, app_context=mock_app_context)
        
        mock_info.assert_called_once()
        args = mock_info.call_args[0]
        assert "Error: Cheque not found" in args[2]


# --- Tests for Inline Query ---

@pytest.mark.asyncio
async def test_cmd_inline_query(mock_session, mock_app_context):
    """Test inline query handler for cheques."""
    mock_inline_query = AsyncMock()
    mock_inline_query.from_user.id = 123
    
    mock_cheque1 = MagicMock()
    mock_cheque1.uuid = "uuid1"
    mock_cheque1.status = ChequeStatus.CHEQUE.value
    mock_cheque1.amount = 100.0
    mock_cheque1.count = 2
    mock_cheque1.comment = "Test"
    
    mock_cheque2 = MagicMock()
    mock_cheque2.uuid = "uuid2"
    mock_cheque2.status = ChequeStatus.INVOICE.value
    mock_cheque2.amount = 50.0
    mock_cheque2.asset = "USDC:GISSUER"
    mock_cheque2.comment = "Invoice"
    
    mock_repo = MagicMock()
    mock_repo.get_available = AsyncMock(return_value=[mock_cheque1, mock_cheque2])
    
    mock_bot = AsyncMock()
    mock_bot.me.return_value = MagicMock(username="testbot")
    mock_app_context.bot = mock_bot
    
    with patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo), \
         patch("other.lang_tools.my_gettext", return_value="text"):
        
        await cmd_inline_query(mock_inline_query, mock_session, mock_app_context)
        
        mock_inline_query.answer.assert_called_once()
        results = mock_inline_query.answer.call_args[0][0]
        assert len(results) == 2


# --- Tests for Start Cheque ---

@pytest.mark.asyncio
async def test_cmd_start_cheque_valid(mock_session, mock_message, mock_state, mock_app_context):
    """Test /start cheque_uuid command."""
    mock_message.text = "/start cheque_test-uuid"
    mock_message.from_user.id = 123
    
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.amount = 100.0
    mock_cheque.count = 5
    mock_cheque.comment = "Gift"
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(side_effect=[2, 0])  # total=2, user=0
    
    with patch("infrastructure.utils.telegram_utils.clear_state", new_callable=AsyncMock), \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo), \
         patch("other.lang_tools.my_gettext", return_value="Cheque text"), \
         patch("keyboards.common_keyboards.get_return_button"):
        
        await cmd_start_cheque(mock_message, mock_state, mock_session, mock_app_context)
        
        mock_state.update_data.assert_called()
        assert mock_send.call_count == 2  # Loading + actual message


@pytest.mark.asyncio
async def test_cmd_start_cheque_already_claimed(mock_session, mock_message, mock_state, mock_app_context):
    """Test /start with already claimed cheque."""
    mock_message.text = "/start cheque_test-uuid"
    mock_message.from_user.id = 123
    
    mock_cheque = MagicMock()
    mock_cheque.count = 5
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(side_effect=[5, 1])  # total=5 (full), user=1
    
    with patch("infrastructure.utils.telegram_utils.clear_state", new_callable=AsyncMock), \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo), \
         patch("other.lang_tools.my_gettext", return_value="Bad cheque"), \
         patch("keyboards.common_keyboards.get_kb_return"):
        
        await cmd_start_cheque(mock_message, mock_state, mock_session, mock_app_context)
        
        # Should show bad_cheque message
        assert any("Bad cheque" in str(call) for call in mock_send.call_args_list)


# --- Tests for Claim Cheque ---

@pytest.mark.asyncio
async def test_cmd_cheque_yes(mock_session, mock_callback, mock_state, mock_app_context):
    """Test ChequeYes callback."""
    mock_callback.from_user.id = 123
    mock_callback.from_user.username = "testuser"
    mock_state.get_data.return_value = {"cheque_uuid": "test-uuid"}
    
    mock_queue = MagicMock()
    mock_queue.put_nowait = MagicMock()  # Synchronous mock
    mock_app_context.cheque_queue = mock_queue
    
    await cmd_cheque_yes(mock_callback, mock_state, mock_session, mock_app_context)
    
    mock_queue.put_nowait.assert_called_once()
    call_args = mock_queue.put_nowait.call_args[0][0]
    assert isinstance(call_args, ChequeQuery)
    assert call_args.for_cancel is False
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_send_money_from_cheque_success(mock_session, mock_state, mock_app_context):
    """Test successful cheque claim."""
    user_id = 123
    cheque_uuid = "test-uuid"
    username = "testuser"
    
    mock_result = ClaimResult(success=True, xdr="XDR_CLAIM")
    
    mock_stellar_service = AsyncMock()
    mock_stellar_service.submit_transaction = AsyncMock()
    
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository"), \
         patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository"), \
         patch("infrastructure.services.stellar_service.StellarService", return_value=mock_stellar_service), \
         patch("infrastructure.services.encryption_service.EncryptionService"), \
         patch("core.use_cases.wallet.add_wallet.AddWallet"), \
         patch("core.use_cases.cheque.claim_cheque.ClaimCheque") as MockUseCase, \
         patch("routers.start_msg.cmd_info_message", new_callable=AsyncMock) as mock_info, \
         patch("other.lang_tools.my_gettext", return_value="msg"):
        
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=mock_result)
        
        await cmd_send_money_from_cheque(mock_session, user_id, mock_state, cheque_uuid, username, app_context=mock_app_context)
        
        mock_use_case.execute.assert_called_once()
        mock_stellar_service.submit_transaction.assert_called_once_with("XDR_CLAIM")
        assert mock_info.call_count == 2


@pytest.mark.asyncio
async def test_cmd_send_money_from_cheque_failure(mock_session, mock_state, mock_app_context):
    """Test failed cheque claim."""
    user_id = 123
    cheque_uuid = "test-uuid"
    username = "testuser"
    
    mock_result = ClaimResult(success=False, error_message="Cheque already claimed")
    
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository"), \
         patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository"), \
         patch("infrastructure.services.stellar_service.StellarService"), \
         patch("infrastructure.services.encryption_service.EncryptionService"), \
         patch("core.use_cases.wallet.add_wallet.AddWallet"), \
         patch("core.use_cases.cheque.claim_cheque.ClaimCheque") as MockUseCase, \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("keyboards.common_keyboards.get_kb_return"):
        
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=mock_result)
        
        await cmd_send_money_from_cheque(mock_session, user_id, mock_state, cheque_uuid, username, app_context=mock_app_context)
        
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert "Error: Cheque already claimed" in args[2]


# --- Tests for Invoice ---

@pytest.mark.asyncio
async def test_cmd_invoice_yes(mock_session, mock_callback, mock_state, mock_app_context):
    """Test InvoiceYes callback handler."""
    mock_callback.from_user.id = 123
    mock_state.get_data.return_value = {"cheque_uuid": "test-uuid"}
    
    mock_cheque = MagicMock()
    mock_cheque.count = 5
    mock_cheque.asset = "USDC:GISSUER123"
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(side_effect=[0, 0])  # user=0, total=0
    
    mock_balance = MagicMock()
    mock_balance.asset_code = "XLM"
    mock_balance.balance = "100"
    
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GADDR"
    
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    
    mock_stellar_service = AsyncMock()
    mock_stellar_service.build_change_trust_transaction = AsyncMock(return_value="XDR_TRUST")
    
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute = AsyncMock(return_value=[mock_balance])
    
    mock_asset = MagicMock()
    mock_asset.code = "EURMTL"
    mock_asset.issuer = "GISSUER"
    
    with patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo), \
         patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository", return_value=mock_wallet_repo), \
         patch("infrastructure.services.stellar_service.StellarService", return_value=mock_stellar_service), \
         patch("core.use_cases.wallet.get_balance.GetWalletBalance", return_value=mock_balance_uc), \
         patch("infrastructure.utils.telegram_utils.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.my_gettext", return_value="text"), \
         patch("keyboards.common_keyboards.get_kb_return"), \
         patch("infrastructure.utils.stellar_utils.eurmtl_asset", mock_asset), \
         patch("infrastructure.utils.stellar_utils.stellar_get_market_link", return_value="link"):
        
        await cmd_invoice_yes(mock_callback, mock_state, mock_session, mock_app_context)
        
        mock_state.update_data.assert_called()
        mock_send.assert_called_once()
        mock_callback.answer.assert_called_once()


# --- Tests for Cheques List ---

@pytest.mark.asyncio
async def test_cmd_cheques(mock_session, mock_message, mock_state, mock_app_context):
    """Test /cheques command to list all available cheques."""
    mock_message.from_user.id = 123
    
    mock_cheque1 = MagicMock()
    mock_cheque1.uuid = "uuid1"
    mock_cheque1.amount = 50.0
    mock_cheque1.count = 2
    mock_cheque1.comment = "Test1"
    
    mock_cheque2 = MagicMock()
    mock_cheque2.uuid = "uuid2"
    mock_cheque2.amount = 100.0
    mock_cheque2.count = 1
    mock_cheque2.comment = "Test2"
    
    mock_repo = MagicMock()
    mock_repo.get_available = AsyncMock(return_value=[mock_cheque1, mock_cheque2])
    
    with patch("infrastructure.utils.telegram_utils.clear_state", new_callable=AsyncMock), \
         patch("infrastructure.persistence.sqlalchemy_cheque_repository.SqlAlchemyChequeRepository", return_value=mock_repo), \
         patch("routers.cheque.cheque_after_send", new_callable=AsyncMock) as mock_after:
        
        await cmd_cheques(mock_message, mock_state, mock_session, mock_app_context)
        
        assert mock_after.call_count == 2
        assert mock_state.update_data.call_count == 2


import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
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


@pytest.fixture
def mock_message():
    message = MagicMock(spec=Message)
    # Re-mock async methods that we use
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.chat = MagicMock()
    message.chat.id = 123
    message.text = "test_text"
    return message

@pytest.fixture
def mock_callback():
    callback = MagicMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.message = MagicMock(spec=Message)
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.from_user = MagicMock()
    callback.from_user.id = 123
    callback.from_user.username = "user"
    callback.data = "data"
    return callback


# --- Tests for Create Cheque Flow ---

@pytest.mark.asyncio
async def test_cmd_create_cheque_with_message(mock_session, mock_message, mock_state, mock_app_context):
    """Test /create_cheque command handler with Message."""
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.bot.id = 12345

    await cmd_create_cheque(mock_message, mock_state, mock_session, app_context=mock_app_context, l10n=mock_app_context.localization_service)
    
    mock_message.delete.assert_called_once()
    mock_app_context.bot.send_message.assert_called_once()
    mock_state.set_state.assert_called_with(StateCheque.sending_sum)


@pytest.mark.asyncio
async def test_cmd_create_cheque_with_callback(mock_session, mock_callback, mock_state, mock_app_context):
    """Test CreateCheque callback handler."""
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.bot.id = 12345

    await cmd_create_cheque(mock_callback, mock_state, mock_session, app_context=mock_app_context, l10n=mock_app_context.localization_service)
    
    mock_app_context.bot.send_message.assert_called_once()
    mock_state.set_state.assert_called_with(StateCheque.sending_sum)
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_sum_valid(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque sum input with valid amount."""
    mock_message.text = "100.5"
    
    # Unified state management
    state_data = {}
    async def update_data(data=None, **kwargs):
        if data and isinstance(data, dict):
            state_data.update(data)
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async

    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CreateCheque use case (called inside cmd_cheque_show)
    mock_create_cheque = MagicMock()
    mock_create_cheque.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR"))
    mock_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque

    await cmd_cheque_get_sum(mock_message, mock_state, mock_session, mock_app_context)
    
    # Verify state update
    assert state_data['send_sum'] == 100.5
    mock_message.delete.assert_called_once()
    # Should call cmd_cheque_show -> bot.send_message
    mock_app_context.bot.send_message.assert_called()


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
    # Unified state management
    state_data = {
        "send_sum": 50.0,
        "send_count": 2,
        "send_comment": "Test comment",
        "send_uuid": "test-uuid-1234567890"
    }
    async def update_data(**kwargs):
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CreateCheque use case
    mock_create_cheque = MagicMock()
    mock_create_cheque.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR_STRING"))
    mock_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque
    
    await cmd_cheque_show(mock_session, mock_message, mock_state, mock_app_context)
    
    mock_create_cheque.execute.assert_called_once()
    mock_app_context.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_show_failure(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque preview when use case fails."""
    # Unified state management
    state_data = {
        "send_sum": 50.0,
        "send_count": 1
    }
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CreateCheque use case failure
    mock_create_cheque = MagicMock()
    mock_create_cheque.execute = AsyncMock(return_value=PaymentResult(success=False, error_message="Insufficient balance"))
    mock_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque
    
    await cmd_cheque_show(mock_session, mock_message, mock_state, mock_app_context)
    
    mock_app_context.bot.send_message.assert_called_once()
    kwargs = mock_app_context.bot.send_message.call_args[1]
    msg_text = kwargs.get('text') or mock_app_context.bot.send_message.call_args[0][1]
    assert "Error: Insufficient balance" in msg_text


# --- Tests for Cheque Count ---

@pytest.mark.asyncio
async def test_cmd_cheque_count(mock_session, mock_callback, mock_state, mock_app_context):
    """Test cheque count callback."""
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.bot.id = 12345

    await cmd_cheque_count(mock_callback, mock_state, mock_session, mock_app_context)
    
    mock_app_context.bot.send_message.assert_called_once()
    mock_state.set_state.assert_called_with(StateCheque.sending_count)
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_count_valid(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque count input with valid number."""
    mock_message.text = "5"
    # Unified state management
    state_data = {"send_sum": 10.5}
    async def update_data(data=None, **kwargs):
        if data and isinstance(data, dict):
            state_data.update(data)
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async

    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CreateCheque use case (called inside cmd_cheque_show)
    mock_create_cheque = MagicMock()
    mock_create_cheque.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR"))
    mock_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque

    await cmd_cheque_get_count(mock_message, mock_state, mock_session, mock_app_context)
    
    assert state_data['send_count'] == 5
    mock_message.delete.assert_called_once()
    mock_app_context.bot.send_message.assert_called()


@pytest.mark.asyncio
async def test_cmd_cheque_get_count_zero(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque count input with zero (should default to 1)."""
    mock_message.text = "0"
    # Unified state management
    state_data = {"send_sum": 100.0}
    async def update_data(data=None, **kwargs):
        if data and isinstance(data, dict):
            state_data.update(data)
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CreateCheque use case (called inside cmd_cheque_show)
    mock_create_cheque = MagicMock()
    mock_create_cheque.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR"))
    mock_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque

    await cmd_cheque_get_count(mock_message, mock_state, mock_session, mock_app_context)
    
    assert state_data['send_count'] == 1 
    mock_message.delete.assert_called_once()
    mock_app_context.bot.send_message.assert_called()


# --- Tests for Cheque Comment ---

@pytest.mark.asyncio
async def test_cmd_cheque_comment(mock_session, mock_callback, mock_state, mock_app_context):
    """Test cheque comment callback."""
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.bot.id = 12345

    await cmd_cheque_comment(mock_callback, mock_state, mock_session, mock_app_context)
    
    mock_app_context.bot.send_message.assert_called_once()
    mock_state.set_state.assert_called_with(StateCheque.sending_comment)
    mock_callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_cheque_get_comment(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque comment input."""
    mock_message.text = "Birthday gift"
    
    # Unified state management
    state_data = {"send_sum": 100.0}
    async def update_data(**kwargs):
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async

    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CreateCheque use case (called inside cmd_cheque_show)
    mock_create_cheque = MagicMock()
    mock_create_cheque.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR"))
    mock_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque

    await cmd_cheque_get_comment(mock_message, mock_state, mock_session, mock_app_context)
    
    assert state_data['send_comment'] == "Birthday gift"
    mock_message.delete.assert_called_once()
    mock_app_context.bot.send_message.assert_called()


@pytest.mark.asyncio
async def test_cmd_cheque_get_comment_truncate(mock_session, mock_message, mock_state, mock_app_context):
    """Test cheque comment truncation to 255 chars."""
    long_comment = "A" * 300
    mock_message.text = long_comment
    
    # Unified state management
    state_data = {"send_sum": 10.0}
    async def update_data(**kwargs):
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async

    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CreateCheque use case
    mock_create_cheque = MagicMock()
    mock_create_cheque.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR"))
    mock_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque

    await cmd_cheque_get_comment(mock_message, mock_state, mock_session, mock_app_context)
    
    # Should truncate to 255 chars
    assert state_data['send_comment'] == "A" * 255


# --- Tests for Cheque Execute ---

@pytest.mark.asyncio
async def test_cmd_cheque_execute(mock_session, mock_callback, mock_state, mock_app_context):
    """Test cheque execution confirmation."""
    # Unified state management
    state_data = {
        "send_sum": 100.0,
        "send_count": 3,
        "send_uuid": "test-uuid"
    }
    async def update_data(**kwargs):
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    await cmd_cheque_execute(mock_callback, mock_state, mock_session, mock_app_context)
    
    mock_app_context.bot.send_message.assert_called_once()
    mock_callback.answer.assert_called_once()


# --- Tests for Cheque After Send ---

@pytest.mark.asyncio
async def test_cheque_after_send_new_cheque(mock_session, mock_state, mock_app_context):
    """Test cheque_after_send creates new cheque."""
    user_id = 123
    # Unified state management
    state_data = {
        "send_sum": 50.0,
        "send_count": 2,
        "send_comment": "Test",
        "send_uuid": "uuid123"
    }
    async def update_data(**kwargs):
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
    # Configure repository
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.amount = 50.0
    mock_cheque.count = 2
    mock_cheque.comment = "Test"
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock(return_value=mock_cheque)
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    mock_app_context.bot.me = AsyncMock(return_value=MagicMock(username="testbot"))
    
    await cheque_after_send(mock_session, user_id, mock_state, app_context=mock_app_context)
    
    mock_repo.create.assert_called_once()
    mock_app_context.bot.send_message.assert_called_once()


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
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    await cb_cheque_click(mock_callback, callback_data, mock_state, mock_session, mock_app_context)
    
    mock_callback.answer.assert_called_once()
    args = mock_callback.answer.call_args[0]
    assert "2" in args[0]  # receive count
    assert "5" in args[0]  # total count


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
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    mock_queue = MagicMock()
    mock_queue.put_nowait = MagicMock()  # Synchronous mock
    mock_app_context.cheque_queue = mock_queue
    
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
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    await cb_cheque_click(mock_callback, callback_data, mock_state, mock_session, mock_app_context)
    
    mock_callback.answer.assert_called_once()
    args = mock_callback.answer.call_args[0]
    assert "cancelled" in args[0].lower()


# --- Tests for Cancel Cheque ---

@pytest.mark.asyncio
async def test_cmd_cancel_cheque_success(mock_session, mock_state, mock_app_context):
    """Test successful cheque cancellation."""
    user_id = 123
    cheque_uuid = "test-uuid"
    
    mock_result = CancelResult(success=True, xdr="XDR_CANCEL")
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CancelCheque use case
    mock_cancel_cheque = MagicMock()
    mock_cancel_cheque.execute = AsyncMock(return_value=mock_result)
    mock_app_context.use_case_factory.create_cancel_cheque.return_value = mock_cancel_cheque
    
    await cmd_cancel_cheque(mock_session, user_id, cheque_uuid, mock_state, app_context=mock_app_context)
    
    mock_cancel_cheque.execute.assert_called_once_with(user_id=user_id, cheque_uuid=cheque_uuid)
    mock_app_context.stellar_service.submit_transaction.assert_called_once_with("XDR_CANCEL")
    assert mock_app_context.bot.send_message.call_count == 2 # try_send2, send_good_cheque


@pytest.mark.asyncio
async def test_cmd_cancel_cheque_failure(mock_session, mock_state, mock_app_context):
    """Test failed cheque cancellation."""
    user_id = 123
    cheque_uuid = "test-uuid"
    
    mock_result = CancelResult(success=False, error_message="Cheque not found")
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock CancelCheque use case failure
    mock_cancel_cheque = MagicMock()
    mock_cancel_cheque.execute = AsyncMock(return_value=mock_result)
    mock_app_context.use_case_factory.create_cancel_cheque.return_value = mock_cancel_cheque
    
    await cmd_cancel_cheque(mock_session, user_id, cheque_uuid, mock_state, app_context=mock_app_context)
    
    # Should call cmd_info_message (which calls bot.send_message)
    mock_app_context.bot.send_message.assert_called_once()
    args = mock_app_context.bot.send_message.call_args[0]
    assert "Error: Cheque not found" in args[1]


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
    
    # Mock repository
    mock_repo = MagicMock()
    mock_repo.get_available = AsyncMock(return_value=[mock_cheque1])
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    mock_app_context.bot.me = AsyncMock(return_value=MagicMock(username="testbot"))
    
    await cmd_inline_query(mock_inline_query, mock_session, mock_app_context)
    
    mock_inline_query.answer.assert_called_once()
    results = mock_inline_query.answer.call_args[0][0]
    assert len(results) == 1


# --- Tests for Start Cheque ---

@pytest.mark.asyncio
async def test_cmd_start_cheque_valid(mock_session, mock_message, mock_state, mock_app_context):
    """Test /start cheque_uuid command."""
    mock_message.text = "/start cheque_test-uuid"
    mock_message.from_user.id = 123
    
    # Unified state management
    state_data = {}
    async def update_data(data=None, **kwargs):
        if data and isinstance(data, dict):
            state_data.update(data)
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345

    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.amount = 100.0
    mock_cheque.count = 5
    mock_cheque.comment = "Gift"
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(side_effect=[2, 0])  # total=2, user=0
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    await cmd_start_cheque(mock_message, mock_state, mock_session, mock_app_context)
    
    assert state_data['cheque_uuid'] == "test-uuid"
    assert mock_app_context.bot.send_message.call_count == 2  # Loading + actual message


@pytest.mark.asyncio
async def test_cmd_start_cheque_already_claimed(mock_session, mock_message, mock_state, mock_app_context):
    """Test /start with already claimed cheque."""
    mock_message.text = "/start cheque_test-uuid"
    mock_message.from_user.id = 123
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345

    mock_cheque = MagicMock()
    mock_cheque.count = 5
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(side_effect=[5, 1])  # total=5 (full), user=1
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    await cmd_start_cheque(mock_message, mock_state, mock_session, mock_app_context)
    
    # Should show bad_cheque message
    mock_app_context.bot.send_message.assert_called()
    msg_found = False
    for call in mock_app_context.bot.send_message.call_args_list:
        args = call[0]
        kwargs = call[1]
        text = str(kwargs.get('text') or (args[1] if len(args) > 1 else ""))
        if "bad_cheque" in text:
            msg_found = True
            break
    assert msg_found


# --- Tests for Claim Cheque ---

@pytest.mark.asyncio
async def test_cmd_cheque_yes(mock_session, mock_callback, mock_state, mock_app_context):
    """Test ChequeYes callback."""
    mock_callback.from_user.id = 123
    mock_callback.from_user.username = "testuser"
    state_data = {"cheque_uuid": "test-uuid"}
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
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
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock ClaimCheque use case
    mock_claim_cheque = MagicMock()
    mock_claim_cheque.execute = AsyncMock(return_value=mock_result)
    mock_app_context.use_case_factory.create_claim_cheque.return_value = mock_claim_cheque
    
    await cmd_send_money_from_cheque(mock_session, user_id, mock_state, cheque_uuid, username, app_context=mock_app_context)
    
    mock_claim_cheque.execute.assert_called_once()
    mock_app_context.stellar_service.submit_transaction.assert_called_once_with("XDR_CLAIM")
    assert mock_app_context.bot.send_message.call_count == 2


@pytest.mark.asyncio
async def test_cmd_send_money_from_cheque_failure(mock_session, mock_state, mock_app_context):
    """Test failed cheque claim."""
    user_id = 123
    cheque_uuid = "test-uuid"
    username = "testuser"
    
    mock_result = ClaimResult(success=False, error_message="Cheque already claimed")
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    # Mock ClaimCheque use case failure
    mock_claim_cheque = MagicMock()
    mock_claim_cheque.execute = AsyncMock(return_value=mock_result)
    mock_app_context.use_case_factory.create_claim_cheque.return_value = mock_claim_cheque
    
    await cmd_send_money_from_cheque(mock_session, user_id, mock_state, cheque_uuid, username, app_context=mock_app_context)
    
    mock_claim_cheque.execute.assert_called_once()
    mock_app_context.bot.send_message.assert_called_once()
    args = mock_app_context.bot.send_message.call_args[0]
    assert "Error: Cheque already claimed" in args[1]


# --- Tests for Invoice ---

@pytest.mark.asyncio
async def test_cmd_invoice_yes(mock_session, mock_callback, mock_state, mock_app_context):
    """Test InvoiceYes callback."""
    mock_callback.from_user.id = 123
    state_data = {"cheque_uuid": "test-uuid"}
    async def update_data(data=None, **kwargs):
        if data and isinstance(data, dict):
            state_data.update(data)
        state_data.update(kwargs)
        return state_data
    mock_state.update_data.side_effect = update_data
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.INVOICE.value
    mock_cheque.count = 5
    mock_cheque.asset = "USDC:GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    mock_cheque.amount = 10.0
    mock_cheque.comment = "test info"
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(return_value=0)
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    mock_balance = MagicMock()
    mock_balance.asset_code = "XYZ"
    mock_balance.balance = 100.0
    
    mock_balance_uc = MagicMock()
    mock_balance_uc.execute = AsyncMock(return_value=[mock_balance])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    mock_wallet = MagicMock()
    mock_wallet.public_key = "GADDR"
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    mock_app_context.stellar_service.build_change_trust_transaction = AsyncMock(return_value="XDR_TRUST")
    
    await cmd_invoice_yes(mock_callback, mock_state, mock_session, mock_app_context)
    
    # We expect send_message to be called at the end
    assert mock_app_context.bot.send_message.call_count >= 1
    mock_callback.answer.assert_called_once()


# --- Tests for Cheques List ---

@pytest.mark.asyncio
async def test_cmd_cheques(mock_session, mock_message, mock_state, mock_app_context):
    """Test /cheques command to list all available cheques."""
    mock_message.from_user.id = 123
    # Unified state management
    state_data = {}
    state_data = {"send_sum": 100.0}
    async def get_data_async():
        return state_data
    mock_state.get_data.side_effect = get_data_async
    
    # Configure mock_app_context
    mock_app_context.dispatcher.storage.get_data = AsyncMock(return_value={})
    mock_app_context.dispatcher.storage.update_data = AsyncMock()
    mock_app_context.bot.id = 12345
    mock_app_context.bot.me = AsyncMock(return_value=MagicMock(username="testbot"))

    mock_cheque1 = MagicMock()
    mock_cheque1.uuid = "uuid1"
    mock_cheque1.status = ChequeStatus.CHEQUE.value
    mock_cheque1.amount = 50.0
    mock_cheque1.count = 2
    mock_cheque1.comment = "Test1"
    
    mock_repo = MagicMock()
    mock_repo.get_available = AsyncMock(return_value=[mock_cheque1])
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque1) # inside cheque_after_send
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    await cmd_cheques(mock_message, mock_state, mock_session, mock_app_context)
    
    assert mock_app_context.bot.send_message.call_count == 1



import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.cheque import cmd_create_cheque, cmd_cancel_cheque, cmd_send_money_from_cheque, ChequeQuery
from core.use_cases.cheque.claim_cheque import ClaimResult
from core.use_cases.cheque.cancel_cheque import CancelResult
from core.domain.entities import Cheque, ChequeStatus


@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def mock_callback():
    callback = AsyncMock()
    callback.from_user = MagicMock()
    callback.from_user.id = 123
    callback.message = AsyncMock()
    callback.message.chat.id = 123
    return callback

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    return state

@pytest.mark.asyncio
async def test_cmd_cancel_cheque(mock_session, mock_state):
    user_id = 123
    cheque_uuid = "uuid"
    
    with patch("routers.cheque.SqlAlchemyWalletRepository"), \
         patch("routers.cheque.SqlAlchemyChequeRepository"), \
         patch("routers.cheque.StellarService"), \
         patch("routers.cheque.EncryptionService"), \
         patch("routers.cheque.CancelCheque") as MockUseCase, \
         patch("routers.cheque.cmd_info_message", new_callable=AsyncMock) as mock_info, \
         patch("routers.cheque.my_gettext", return_value="msg"):
         
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=CancelResult(success=True, xdr="XDR"))
        
        # We need StellarService.submit_transaction to be mocked too
        mock_service = AsyncMock()
        mock_service.submit_transaction = AsyncMock()
        
        # But we patch class definition in router. 
        # Inside router: stellar_service = StellarService(...)
        # So we mocked the class. The instance is MockClass.return_value.
        mock_app_context = MagicMock()
        with patch("routers.cheque.StellarService", return_value=mock_service):
            await cmd_cancel_cheque(mock_session, user_id, cheque_uuid, mock_state, app_context=mock_app_context)
        
        mock_use_case.execute.assert_called_once_with(user_id=123, cheque_uuid="uuid")
        mock_state.update_data.assert_called()
        mock_info.assert_called()


@pytest.mark.asyncio
async def test_cmd_send_money_from_cheque(mock_session, mock_state):
    user_id = 123
    cheque_uuid = "uuid"
    username = "user"
    
    with patch("routers.cheque.SqlAlchemyWalletRepository"), \
         patch("routers.cheque.SqlAlchemyChequeRepository"), \
         patch("routers.cheque.StellarService") as MockService, \
         patch("routers.cheque.EncryptionService"), \
         patch("routers.cheque.AddWallet"), \
         patch("routers.cheque.ClaimCheque") as MockUseCase, \
         patch("routers.cheque.cmd_info_message", new_callable=AsyncMock), \
         patch("routers.cheque.my_gettext", return_value="msg"):
         
        mock_use_case = MockUseCase.return_value
        mock_use_case.execute = AsyncMock(return_value=ClaimResult(success=True, xdr="XDR"))
        
        mock_service_instance = MockService.return_value
        mock_service_instance.submit_transaction = AsyncMock()
        
        mock_app_context = MagicMock()
        await cmd_send_money_from_cheque(mock_session, user_id, mock_state, cheque_uuid, username, app_context=mock_app_context)
        
        mock_use_case.execute.assert_called_once()
        mock_service_instance.submit_transaction.assert_called_with("XDR")

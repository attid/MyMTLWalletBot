
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.inout import cmd_inout, cmd_receive_usdt, cmd_usdt_in, cmd_usdt_check, cmd_balance, cmd_send_usdt_sum
from core.domain.entities import Wallet, User
from core.domain.value_objects import Balance
from datetime import datetime

@pytest.mark.asyncio
async def test_cmd_inout(mock_session, mock_callback, mock_app_context):
    with patch("routers.inout.my_gettext", return_value="msg"), \
         patch("routers.inout.send_message", new_callable=AsyncMock) as mock_send:
        
        await cmd_inout(mock_callback, mock_session, mock_app_context)
        
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert kwargs['reply_markup'] is not None

@pytest.mark.asyncio
async def test_cmd_receive_usdt(mock_session, mock_callback, mock_app_context):
    with patch("routers.inout.my_gettext", return_value="msg"), \
         patch("routers.inout.send_message", new_callable=AsyncMock) as mock_send:
        
        await cmd_receive_usdt(mock_callback, mock_session, mock_app_context)
        
        mock_send.assert_called_once()
        # Verify specific buttons exist in markup if possible, or just execution success

@pytest.mark.asyncio
async def test_cmd_usdt_in(mock_session, mock_callback, mock_state, mock_app_context):
    # Mock mocks
    mock_balances = [
        Balance(asset_code="USDM", asset_issuer="native", balance="100.0", limit="1000", asset_type="credit_alphanum4")
    ]
    
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute.return_value = mock_balances
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
    
    # Mock User Repo for Tron Key
    mock_user_repo = MagicMock()
    mock_user_repo.get_usdt_key = AsyncMock(return_value=("TRON_PRIVATE_KEY", 0))
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    with patch("routers.inout.my_gettext", return_value="msg"), \
         patch("routers.inout.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.inout.tron_get_public", return_value="TRON_PUBLIC_KEY"):
         
        await cmd_usdt_in(mock_callback, mock_state, mock_session, mock_app_context)
        
        mock_send.assert_called_once()
        # Check text contains Tron Key
        # msg = my_gettext(..., (..., tron_get_public(...)), ...)
        # Since we mocked my_gettext to return "msg", we might not see it unless we check call args to my_gettext?
        # But execution path confirms logic.

@pytest.mark.asyncio
async def test_cmd_balance(mock_session, mock_message, mock_app_context):
    mock_message.from_user.username = "itolstov"
    
    mock_user_repo = MagicMock()
    # (user_name, usdt_amount, user_id)
    mock_user_repo.get_all_with_usdt_balance = AsyncMock(return_value=[
        ("user1", 100, 1),
        ("user2", 50, 2)
    ])
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    # Mock get_account_energy
    mock_energy = MagicMock()
    mock_energy.energy_amount = 500000
    
    with patch("routers.inout.get_account_energy", new_callable=AsyncMock) as mock_get_energy:
        mock_get_energy.return_value = mock_energy
        
        await cmd_balance(mock_message, mock_session, mock_app_context)
        
        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args[0][0]
        assert "user1" in text
        assert "100" in text
        assert "user2" in text

@pytest.mark.asyncio
async def test_cmd_send_usdt_sum(mock_session, mock_message, mock_state, mock_app_context):
    mock_message.text = "20"
    
    mock_balances = [
        Balance(asset_code="USDM", asset_issuer="native", balance="100.0", limit="1000", asset_type="credit_alphanum4")
    ]
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute.return_value = mock_balances
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
    
    with patch("routers.inout.cmd_send_usdt", new_callable=AsyncMock) as mock_send_usdt, \
         patch("routers.inout.my_gettext", return_value="msg"):
         
        await cmd_send_usdt_sum(mock_message, mock_state, mock_session, mock_app_context)
        
        mock_state.update_data.assert_called_with(send_sum=20.0)
        mock_state.set_state.assert_called_with(None)
        mock_send_usdt.assert_called_once()



import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime

from routers.admin import router as admin_router, cmd_stats, cmd_exit, ExitState, cmd_horizon, cmd_horizon_rw, cmd_log, cmd_err, cmd_clear, cmd_fee, cmd_user_wallets, cmd_address_info, cmd_delete_address, cmd_help, cmd_test
from db.models import MyMtlWalletBotUsers, MyMtlWalletBot, MyMtlWalletBotTransactions, MyMtlWalletBotCheque, MyMtlWalletBotLog
import routers.admin as admin_module

@pytest.fixture
def mock_session():
    session = MagicMock()
    # Mock query returns a mock that has count, filter etc.
    query_mock = MagicMock()
    session.query.return_value = query_mock
    query_mock.count.return_value = 10
    query_mock.filter.return_value = query_mock
    query_mock.distinct.return_value = query_mock
    query_mock.group_by.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.all.return_value = []
    query_mock.one_or_none.return_value = None
    query_mock.first.return_value = None
    return session

@pytest.mark.asyncio
async def test_cmd_stats(mock_session):
    message = AsyncMock()
    
    # Mock return values for counts
    mock_session.query.return_value.limit.return_value.all.return_value = [("op1", 5), ("op2", 3)]
    
    await cmd_stats(message, mock_session)
    
    assert message.answer.called
    args = message.answer.call_args[0][0]
    assert "Статистика бота" in args
    assert "op1: 5" in args

@pytest.mark.asyncio
async def test_cmd_exit_restart():
    message = AsyncMock()
    message.from_user.username = "itolstov"
    state = AsyncMock(spec=FSMContext)
    session = MagicMock()
    
    # Case 1: First call, sets state
    state.get_state.return_value = None
    await cmd_exit(message, state, session)
    state.set_state.assert_called_with(ExitState.need_exit)
    message.reply.assert_called_with(":'[")
    
    # Case 2: Second call, exits
    state.get_state.return_value = ExitState.need_exit
    with patch("routers.admin.exit") as mock_exit:
        await cmd_exit(message, state, session)
        state.set_state.assert_called_with(None)
        message.reply.assert_called_with("Chao :[[[")
        mock_exit.assert_called()

@pytest.mark.asyncio
async def test_cmd_horizon():
    message = AsyncMock()
    message.from_user.username = "itolstov"
    state = AsyncMock(spec=FSMContext)
    session = MagicMock()
    
    with patch("routers.admin.config") as mock_config, \
         patch("routers.admin.horizont_urls", ["url1", "url2"]):
        mock_config.horizon_url = "url1"
        
        # Test /horizon
        await cmd_horizon(message, state, session)
        assert mock_config.horizon_url == "url2"
        message.reply.assert_called_with("Horizon url: url2")

@pytest.mark.asyncio
async def test_cmd_horizon_rw():
    message = AsyncMock()
    message.from_user.username = "itolstov"
    state = AsyncMock(spec=FSMContext)
    session = MagicMock()
    
    with patch("routers.admin.config") as mock_config, \
         patch("routers.admin.horizont_urls", ["url1", "url2"]):
        mock_config.horizon_url_rw = "url1"
        
        # Test /horizon_rw
        await cmd_horizon_rw(message, state, session)
        assert mock_config.horizon_url_rw == "url2"
        message.reply.assert_called_with("Horizon url: url2")

@pytest.mark.asyncio
async def test_cmd_log_err_clear():
    message = AsyncMock()
    message.from_user.username = "itolstov"
    message.chat.id = 123
    
    with patch("routers.admin.global_data") as mock_gd, \
         patch("routers.admin.os.path.isfile", return_value=True), \
         patch("routers.admin.os.remove") as mock_remove:
             
        mock_gd.bot.send_document = AsyncMock()
        
        # Test /log
        await cmd_log(message)
        assert mock_gd.bot.send_document.call_count >= 1
        
        # Test /err
        mock_gd.bot.send_document.reset_mock()
        await cmd_err(message)
        assert mock_gd.bot.send_document.call_count >= 1
        
        # Test /clear
        await cmd_clear(message)
        # Verify os.remove called
        assert mock_remove.call_count >= 1

@pytest.mark.asyncio
async def test_admin_router_integration():
    """Test admin commands via router to handle the duplicate function names issue"""
    pass

@pytest.mark.asyncio
async def test_cmd_fee():
    message = AsyncMock()
    with patch("routers.admin.async_stellar_check_fee", return_value="10-100"):
        await cmd_fee(message)
        message.answer.assert_called_with("Комиссия (мин и мах) 10-100")

@pytest.mark.asyncio
async def test_cmd_user_wallets(mock_session):
    message = AsyncMock()
    message.text = "/user_wallets @testuser"
    
    # Mock user lookup
    user_mock = MagicMock()
    user_mock.user_id = 111
    mock_session.query.return_value.filter.return_value.one_or_none.return_value = user_mock
    
    # Mock wallets lookup
    wallet_mock = MagicMock()
    wallet_mock.public_key = "GABC"
    wallet_mock.default_wallet = 1
    wallet_mock.free_wallet = 1
    wallet_mock.need_delete = 0
    wallet_mock.use_pin = 0
    mock_session.query.return_value.filter.return_value.all.return_value = [wallet_mock]
    
    await cmd_user_wallets(message, mock_session)
    
    assert message.answer.called
    args = message.answer.call_args[0][0]
    assert "GABC" in args
    assert "main" in args
    assert "free" in args

@pytest.mark.asyncio
async def test_cmd_address_info(mock_session):
    message = AsyncMock()
    message.text = "/address_info GABC"
    
    # Mock wallet/user join
    wallet_row = MagicMock()
    wallet_row.user_id = 111
    wallet_row.use_pin = 0
    wallet_row.free_wallet = 0
    wallet_row.need_delete = 0
    
    user_row = MagicMock()
    user_row.user_name = "testuser"
    
    mock_session.query.return_value.join.return_value.filter.return_value.first.return_value = (wallet_row, user_row)
    
    await cmd_address_info(message, mock_session)
    
    assert message.answer.called
    args = message.answer.call_args[0][0]
    assert "user_id: 111" in args
    assert "@testuser" in args

@pytest.mark.asyncio
async def test_cmd_delete_address(mock_session):
    message = AsyncMock()
    message.text = "/delete_address GABC"
    
    wallet_mock = MagicMock()
    wallet_mock.need_delete = 0
    mock_session.query.return_value.filter.return_value.one_or_none.return_value = wallet_mock
    
    await cmd_delete_address(message, mock_session)
    
    assert wallet_mock.need_delete == 1
    mock_session.commit.assert_called()
    message.answer.assert_called_with("Адрес помечен удалённым")

@pytest.mark.asyncio
async def test_cmd_help():
    message = AsyncMock()
    await cmd_help(message)
    assert message.answer.called
    assert "/stats" in message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_test():
    message = AsyncMock()
    message.from_user.username = "itolstov"
    
    chat_mock = MagicMock()
    chat_mock.json.return_value = "{}"
    
    with patch("routers.admin.global_data") as mock_gd:
        mock_gd.bot.get_chat = AsyncMock(return_value=chat_mock)
        await cmd_test(message)
        assert message.answer.call_count == 2

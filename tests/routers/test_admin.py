
import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import datetime

from routers.admin import router as admin_router, ExitState
from other.config_reader import config
import routers.admin as admin_module
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN

class MockDbMiddleware(BaseMiddleware):
    def __init__(self, session):
        self.session = session
    async def __call__(self, handler, event, data):
        data["session"] = self.session
        return await handler(event, data)

@pytest.fixture(autouse=True)
def cleanup_router():
    # Store original admins
    original_admins = list(config.admins)
    # Set test admins
    config.admins.clear()
    config.admins.append(123)
    
    yield
    
    # Restore original admins
    config.admins.clear()
    config.admins.extend(original_admins)
    
    if admin_router.parent_router:
         admin_router._parent_router = None

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

@pytest.fixture
async def bot():
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    yield bot
    await bot.session.close()

@pytest.fixture
def dp(mock_session):
    dp = Dispatcher()
    dp.message.middleware(MockDbMiddleware(mock_session))
    dp.include_router(admin_router)
    return dp

@pytest.mark.asyncio
async def test_cmd_stats(mock_telegram, bot, dp, mock_session):
    # Mock return values for counts
    mock_session.query.return_value.limit.return_value.all.return_value = [("op1", 5), ("op2", 3)]
    
    update = types.Update(
        update_id=1,
        message=types.Message(
            message_id=1,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
            text="/stats"
        )
    )
    
    await dp.feed_update(bot=bot, update=update)
    
    # Verify message sent to mock_server
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) > 0
    args = sent_messages[0]['data']['text']
    assert "Статистика бота" in args
    assert "op1: 5" in args

@pytest.mark.asyncio
async def test_cmd_exit_restart(mock_telegram, bot, dp, mock_session):
    # Case 1: First call, sets state
    update = types.Update(
        update_id=2,
        message=types.Message(
            message_id=2,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
            text="/exit"
        )
    )
    
    await dp.feed_update(bot=bot, update=update)
    
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert any(":'[" in m['data']['text'] for m in sent_messages)
    
    # Case 2: Second call, exits
    mock_telegram.clear()
    with patch("routers.admin.exit") as mock_exit:
        update2 = types.Update(
            update_id=3,
            message=types.Message(
                message_id=3,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
                text="/exit"
            )
        )
        await dp.feed_update(bot=bot, update=update2)
        
        sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
        assert any("Chao :[[[" in m['data']['text'] for m in sent_messages)
        mock_exit.assert_called()

@pytest.mark.asyncio
async def test_cmd_horizon(mock_telegram, bot, dp, mock_session):
    with patch("routers.admin.horizont_urls", ["url1", "url2"]):
        config.horizon_url = "url1"
        
        update = types.Update(
            update_id=4,
            message=types.Message(
                message_id=4,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
                text="/horizon"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        assert config.horizon_url == "url2"
        
        sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
        assert any("Horizon url: url2" in m['data']['text'] for m in sent_messages)

@pytest.mark.asyncio
async def test_cmd_horizon_rw(mock_telegram, bot, dp, mock_session):
    with patch("routers.admin.horizont_urls", ["url1", "url2"]):
        config.horizon_url_rw = "url1"
        
        update = types.Update(
            update_id=5,
            message=types.Message(
                message_id=5,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
                text="/horizon_rw"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        assert config.horizon_url_rw == "url2"
        
        sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
        assert any("Horizon url: url2" in m['data']['text'] for m in sent_messages)

@pytest.mark.asyncio
async def test_cmd_log_err_clear(mock_telegram, bot, dp, mock_session, mock_app_context):
    mock_app_context.bot = bot
    
    # Create dummy files for aiogram to read
    log_files = ['mmwb.log', 'mmwb_check_transaction.log', 'MyMTLWallet_bot.err', 'MMWB.err', 'MMWB.log']
    for f_name in log_files:
        with open(f_name, 'w') as f:
            f.write('test log content')

    try:
        with patch("routers.admin.os.path.isfile", return_value=True), \
             patch("routers.admin.os.remove") as mock_remove:
            
            # Test /log
            update = types.Update(
                update_id=6,
                message=types.Message(
                    message_id=6,
                    date=datetime.datetime.now(),
                    chat=types.Chat(id=123, type='private'),
                    from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
                    text="/log"
                )
            )
            await dp.feed_update(bot=bot, update=update, app_context=mock_app_context)
            
            sent_docs = [r for r in mock_telegram if r['method'] == 'sendDocument']
            assert len(sent_docs) >= 1
            
            # Test /err
            mock_telegram.clear()
            update2 = types.Update(
                update_id=7,
                message=types.Message(
                    message_id=7,
                    date=datetime.datetime.now(),
                    chat=types.Chat(id=123, type='private'),
                    from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
                    text="/err"
                )
            )
            await dp.feed_update(bot=bot, update=update2, app_context=mock_app_context)
            sent_docs = [r for r in mock_telegram if r['method'] == 'sendDocument']
            assert len(sent_docs) >= 1
            
            # Test /clear
            update3 = types.Update(
                update_id=8,
                message=types.Message(
                    message_id=8,
                    date=datetime.datetime.now(),
                    chat=types.Chat(id=123, type='private'),
                    from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
                    text="/clear"
                )
            )
            await dp.feed_update(bot=bot, update=update3, app_context=mock_app_context)
            assert mock_remove.call_count >= 1
    finally:
        for f_name in log_files:
            if os.path.exists(f_name):
                os.remove(f_name)

@pytest.mark.asyncio
async def test_cmd_fee(mock_telegram, bot, dp, mock_session):
    with patch("routers.admin.async_stellar_check_fee", return_value="10-100"):
        
        update = types.Update(
            update_id=9,
            message=types.Message(
                message_id=9,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
                text="/fee"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        
        sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
        assert any("Комиссия (мин и мах) 10-100" in m['data']['text'] for m in sent_messages)

@pytest.mark.asyncio
async def test_cmd_user_wallets(mock_telegram, bot, dp, mock_session):
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
    
    update = types.Update(
        update_id=10,
        message=types.Message(
            message_id=10,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="/user_wallets @testuser"
        )
    )
    
    await dp.feed_update(bot=bot, update=update)
    
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) > 0
    args = sent_messages[0]['data']['text']
    assert "GABC" in args
    assert "main" in args
    assert "free" in args

@pytest.mark.asyncio
async def test_cmd_address_info(mock_telegram, bot, dp, mock_session):
    # Mock wallet/user join
    wallet_row = MagicMock()
    wallet_row.user_id = 111
    wallet_row.use_pin = 0
    wallet_row.free_wallet = 0
    wallet_row.need_delete = 0
    
    user_row = MagicMock()
    user_row.user_name = "testuser"
    
    mock_session.query.return_value.join.return_value.filter.return_value.first.return_value = (wallet_row, user_row)
    
    update = types.Update(
        update_id=11,
        message=types.Message(
            message_id=11,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="/address_info GABC"
        )
    )
    
    await dp.feed_update(bot=bot, update=update)
    
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) > 0
    args = sent_messages[0]['data']['text']
    assert "user_id: 111" in args
    assert "@testuser" in args

@pytest.mark.asyncio
async def test_cmd_delete_address(mock_telegram, bot, dp, mock_session):
    wallet_mock = MagicMock()
    wallet_mock.need_delete = 0
    mock_session.query.return_value.filter.return_value.one_or_none.return_value = wallet_mock
    
    update = types.Update(
        update_id=12,
        message=types.Message(
            message_id=12,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="/delete_address GABC"
        )
    )
    
    await dp.feed_update(bot=bot, update=update)
    
    assert wallet_mock.need_delete == 1
    mock_session.commit.assert_called()
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert any("Адрес помечен удалённым" in m['data']['text'] for m in sent_messages)

@pytest.mark.asyncio
async def test_cmd_help(mock_telegram, bot, dp):
    update = types.Update(
        update_id=13,
        message=types.Message(
            message_id=13,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="/help"
        )
    )
    
    await dp.feed_update(bot=bot, update=update)
    
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert any("/stats" in m['data']['text'] for m in sent_messages)

@pytest.mark.asyncio
async def test_cmd_test(mock_telegram, bot, dp, mock_app_context):
    mock_app_context.bot = bot
    chat_mock = MagicMock()
    chat_mock.json.return_value = '{"id": 215155653, "type": "private"}'
    with patch.object(bot, 'get_chat', AsyncMock(return_value=chat_mock)):
        update = types.Update(
            update_id=14,
            message=types.Message(
                message_id=14,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
                text="/test"
            )
        )
        
        await dp.feed_update(bot=bot, update=update, app_context=mock_app_context)
        
        sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
        assert len(sent_messages) >= 1

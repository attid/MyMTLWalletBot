
import pytest
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import patch, AsyncMock, MagicMock
import datetime

from routers.fest import router as fest_router
from routers.fest import StateFest
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from aiogram.dispatcher.middlewares.base import BaseMiddleware

class MockDbMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        data["session"] = MagicMock()
        return await handler(event, data)

@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if fest_router.parent_router:
         fest_router._parent_router = None

@pytest.mark.asyncio
async def test_cmd_fest_menu(mock_server, dp):
    """
    Test F.data == 'Fest2024'
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(fest_router)

    # Mock config.fest_menu
    mock_fest_menu = {"Participant1": "Address1", "Participant2": "Address2"}
    
    with patch("routers.fest.config") as mock_config, \
         patch("routers.fest.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd:
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        mock_config.fest_menu = mock_fest_menu
        
        update = types.Update(
            update_id=1,
            callback_query=types.CallbackQuery(
                id="cb1",
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
                chat_instance="ci1",
                message=types.Message(
                    message_id=1,
                    date=datetime.datetime.now(),
                    chat=types.Chat(id=123, type='private'),
                    text="msg"
                ),
                data="Fest2024"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        
        # Verify menu message sent
        assert mock_send.call_count >= 1
        assert "Choose participant" in mock_send.call_args_list[-1][0][2] # Default English

    await bot.session.close()

@pytest.mark.asyncio
async def test_fest_level_24_selection(mock_server, dp):
    """
    Test selection of a participant (SendLevel24 callback).
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(fest_router)
    
    with patch("routers.fest.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd:
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}

        # Construct callback data using the class from routers.fest if possible, 
        # or just raw string if we knew packed format. 
        # But better to use the class.
        from routers.fest import SendLevel24
        cb_data = SendLevel24(level_1="Participant1").pack()
        
        update = types.Update(
            update_id=2,
            callback_query=types.CallbackQuery(
                id="cb2",
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
                chat_instance="ci1",
                message=types.Message(
                    message_id=2,
                    date=datetime.datetime.now(),
                    chat=types.Chat(id=123, type='private'),
                    text="msg"
                ),
                data=cb_data
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        
        # Should ask for sum
        assert mock_send.call_count >= 1
        assert "Send sum" in mock_send.call_args_list[-1][0][2]

    await bot.session.close()

@pytest.mark.asyncio
async def test_fest_sending_sum(mock_server, dp):
    """
    Test sending sum state.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.message.middleware(MockDbMiddleware())
    dp.include_router(fest_router)
    
    # Mock config for address lookup
    mock_fest_menu = {"Participant1": "Address1"}
    
    with patch("routers.fest.config") as mock_config, \
         patch("infrastructure.utils.stellar_utils.my_float", return_value=10.0), \
         patch("routers.fest.cmd_send_04", new_callable=AsyncMock) as mock_cmd_send_04, \
         patch("routers.fest.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd:
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        mock_config.fest_menu = mock_fest_menu
        
        # Pre-set state data
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.fsm.context import FSMContext
        
        # Manually set state? 
        ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
        await ctx.set_state(StateFest.sending_sum)
        await ctx.update_data(level_1="Participant1", msg="Test message")
        
        update = types.Update(
            update_id=3,
            message=types.Message(
                message_id=3,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
                text="10"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        
        mock_cmd_send_04.assert_called_once()
    
    await bot.session.close()

@pytest.mark.asyncio
async def test_reload_fest_menu(mock_server, dp):
    """
    Test /reload_fest_menu
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.message.middleware(MockDbMiddleware())
    dp.include_router(fest_router)
    
    with patch("routers.fest.config") as mock_config, \
         patch("routers.fest.load_fest_info", new_callable=AsyncMock, create=True) as mock_load:
         
        mock_load.return_value = {"New": "Menu"}
        
        update = types.Update(
            update_id=4,
            message=types.Message(
                message_id=4,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="itolstov"),
                text="/reload_fest_menu"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        
        mock_load.assert_called_once()
        assert mock_config.fest_menu == {"New": "Menu"}

        # Verify response
        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None
        assert "redy" in req["data"]["text"]

    await bot.session.close()

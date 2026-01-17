
import pytest
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import patch, AsyncMock, MagicMock
import datetime

from routers.veche import router as veche_router
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from aiogram.dispatcher.middlewares.base import BaseMiddleware

class MockDbMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        data["session"] = MagicMock()
        return await handler(event, data)

@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if veche_router.parent_router:
         veche_router._parent_router = None

@pytest.mark.asyncio
async def test_cmd_start_veche_no_user(mock_server, dp):
    """
    Test /start veche_... when user does not exist.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.message.middleware(MockDbMiddleware())
    dp.include_router(veche_router)
    
    with patch("routers.veche.check_user_id", return_value=False) as mock_check, \
         patch("routers.veche.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.veche.clear_state", new_callable=AsyncMock):
        
        update = types.Update(
            update_id=1,
            message=types.Message(
                message_id=1,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
                text="/start veche_token123"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        
        # Verify check_user_id was called
        mock_check.assert_called_once()
        # Verify error message sent
        assert mock_send.call_count >= 1
        assert "You dont have wallet" in mock_send.call_args_list[-1][0][2]

    await bot.session.close()

@pytest.mark.asyncio
async def test_cmd_start_veche_success(mock_server, dp):
    """
    Test /start veche_... success flow.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.message.middleware(MockDbMiddleware())
    dp.include_router(veche_router)
    
    mock_account = MagicMock()
    mock_account.account.account_id = "GABC123"

    with patch("routers.veche.check_user_id", return_value=True), \
         patch("routers.veche.stellar_get_user_account", return_value=mock_account), \
         patch("routers.veche.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.veche.clear_state", new_callable=AsyncMock), \
         patch("other.lang_tools.global_data") as mock_gd:
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        # We need to ensure my_gettext returns the key if not found, or mock dictionary to return key
        # my_gettext logic: global_data.lang_dict[lang].get(text, ...)
        # Let's just mock the dictionary get method? 
        # But lang_dict['en'] is a dict.
        # We can make it a specific dict subclass or wrap it.
        # Or simpler: just let it return defaults if empty, but my_gettext implementation handles returns.
        # line 51: text = global_data.lang_dict[lang].get(text, global_data.lang_dict['en'].get(text, f'{text} 0_0'))
        # If I leave lang_dict as empty dicts, it returns f'{text} 0_0'.
        # That's acceptable for verification ("veche_ask 0_0" contains "veche_ask").

        update = types.Update(
            update_id=2,
            message=types.Message(
                message_id=2,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
                text="/start veche_token123"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        
        # Verify ask message sent
        assert mock_send.call_count >= 1
        assert "veche_ask" in mock_send.call_args_list[-1][0][2]

    await bot.session.close()

@pytest.mark.asyncio
async def test_callback_tools_delegate(mock_server, dp):
    """
    Test callback MTLToolsVeche
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(veche_router)

    mock_account = MagicMock()
    mock_account.account.account_id = "GABC123"
    
    with patch("routers.veche.stellar_get_user_account", return_value=mock_account), \
         patch("routers.veche.get_web_request", return_value=(200, "verifier_code")), \
         patch("routers.veche.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd:
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
         
        update = types.Update(
            update_id=3,
            callback_query=types.CallbackQuery(
                id="cb1",
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
                chat_instance="ci1",
                message=types.Message(
                    message_id=3,
                    date=datetime.datetime.now(),
                    chat=types.Chat(id=123, type='private'),
                    text="msg"
                ),
                data="MTLToolsVeche"
            )
        )
        
        await dp.feed_update(bot=bot, update=update)
        
        # Should trigger cmd_login_to_veche which sends veche_ask
        assert mock_send.call_count >= 1
        assert "veche_ask" in mock_send.call_args_list[-1][0][2]

    await bot.session.close()

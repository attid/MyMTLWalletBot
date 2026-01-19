
import pytest
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import MagicMock
import datetime

from routers.monitoring import router as monitoring_router
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN

@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if monitoring_router.parent_router:
        monitoring_router._parent_router = None

@pytest.mark.asyncio
async def test_handle_monitoring_message(mock_telegram, dp):
    session = AiohttpSession(api=TelegramAPIServer.from_base(MOCK_SERVER_URL))
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.include_router(monitoring_router)
    
    update = types.Update(
        update_id=1,
        channel_post=types.Message(
            message_id=1,
            date=datetime.datetime.now(),
            chat=types.Chat(id=-1002263825546, type='channel', title="Channel"),
            from_user=None, # channel posts don't always have from_user
            text="#mmwb #skynet command=ping"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp

    await dp.feed_update(bot=bot, update=update, app_context=app_context)
    
    # Check if sendMessage was called with expected text
    req = next((r for r in mock_telegram if r["method"] == "sendMessage"), None)
    assert req is not None, "sendMessage should have been called"
    assert req["data"]["text"] == "#skynet #mmwb command=pong"
    
    await bot.session.close()

@pytest.mark.asyncio
async def test_handle_monitoring_message_ignore(mock_telegram, dp):
    session = AiohttpSession(api=TelegramAPIServer.from_base(MOCK_SERVER_URL))
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    
    dp.include_router(monitoring_router)
    
    update = types.Update(
        update_id=2,
        channel_post=types.Message(
            message_id=2,
            date=datetime.datetime.now(),
            chat=types.Chat(id=-1002263825546, type='channel', title="Channel"),
            from_user=None,
            text="Just some text"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp

    await dp.feed_update(bot=bot, update=update, app_context=app_context)
    
    # Check that NO sendMessage was called
    req = next((r for r in mock_telegram if r["method"] == "sendMessage"), None)
    assert req is None, "sendMessage should NOT have been called"
    
    await bot.session.close()

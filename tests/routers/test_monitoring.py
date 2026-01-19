import pytest
from aiogram import Bot, Dispatcher, types
from unittest.mock import MagicMock
import datetime

from routers.monitoring import router as monitoring_router
from tests.conftest import (
    RouterTestMiddleware,
    get_telegram_request,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if monitoring_router.parent_router:
        monitoring_router._parent_router = None

def create_channel_post_update(chat_id: int, text: str, update_id: int = 1, message_id: int = 1) -> types.Update:
    """Helper to create channel post updates for monitoring tests."""
    return types.Update(
        update_id=update_id,
        channel_post=types.Message(
            message_id=message_id,
            date=datetime.datetime.now(),
            chat=types.Chat(id=chat_id, type='channel', title="Monitoring Channel"),
            text=text
        )
    )

@pytest.mark.asyncio
async def test_handle_monitoring_ping_pong(mock_telegram, router_app_context):
    """Test ping-pong monitor: should reply pong to ping command in specific channel."""
    dp = router_app_context.dispatcher
    dp.channel_post.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(monitoring_router)

    # Specific channel ID from monitoring.py
    channel_id = -1002263825546
    ping_text = "#mmwb #skynet command=ping"
    
    update = create_channel_post_update(chat_id=channel_id, text=ping_text)
    
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify pong response
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert req["data"]["text"] == "#skynet #mmwb command=pong"
    assert int(req["data"]["chat_id"]) == channel_id


@pytest.mark.asyncio
async def test_handle_monitoring_ignore_wrong_channel(mock_telegram, router_app_context):
    """Test monitor: should ignore messages from other channels."""
    dp = router_app_context.dispatcher
    dp.channel_post.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(monitoring_router)

    wrong_channel_id = -123456789
    ping_text = "#mmwb #skynet command=ping"
    
    update = create_channel_post_update(chat_id=wrong_channel_id, text=ping_text)
    
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify NO response
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is None


@pytest.mark.asyncio
async def test_handle_monitoring_ignore_wrong_text(mock_telegram, router_app_context):
    """Test monitor: should ignore messages with wrong pattern."""
    dp = router_app_context.dispatcher
    dp.channel_post.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(monitoring_router)

    channel_id = -1002263825546
    wrong_text = "Hello world"
    
    update = create_channel_post_update(chat_id=channel_id, text=wrong_text)
    
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify NO response
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is None
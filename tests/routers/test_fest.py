import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.storage.base import StorageKey

from routers.fest import (
    router as fest_router,
    StateFest,
    SendLevel24,
)
from core.domain.value_objects import PaymentResult
from other.config_reader import config
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached and config is restored."""
    original_menu = getattr(config, 'fest_menu', {})
    yield
    config.fest_menu = original_menu
    if fest_router.parent_router:
        fest_router._parent_router = None

@pytest.fixture
def setup_fest_mocks(router_app_context):
    """
    Common mock setup for fest router tests.
    """
    class FestMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Setup test menu in config
            config.fest_menu = {"Participant1": "GADDRESS1"}
            
            # Mock send payment use case (needed by cmd_send_04)
            self.send_uc = MagicMock()
            self.send_uc.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR_FEST"))
            self.ctx.use_case_factory.create_send_payment.return_value = self.send_uc

    return FestMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')]
    return msgs[-1] if msgs else None


@pytest.mark.asyncio
async def test_cmd_fest_menu(mock_telegram, router_app_context, setup_fest_mocks):
    """Test clicking Fest2024: should show participant selection."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(fest_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "Fest2024"))
    
    req = get_latest_msg(mock_telegram)
    assert req is not None
    # Check for participant name in keyboard
    assert "Participant1" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_fest_level_24(mock_telegram, router_app_context, setup_fest_mocks):
    """Test selecting a participant: should ask for amount."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(fest_router)

    user_id = 123
    cb_data = SendLevel24(level_1="Participant1").pack()
    
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, cb_data))
    
    req = get_latest_msg(mock_telegram)
    assert "Send sum in EURMTL" in req["data"]["text"]
    assert "Participant1" in req["data"]["text"]
    
    # Verify state
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    assert await dp.storage.get_state(state_key) == StateFest.sending_sum


@pytest.mark.asyncio
async def test_cmd_fest_get_sum_flow(mock_telegram, router_app_context, setup_fest_mocks):
    """Test entering amount for fest: should move to payment confirmation."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(fest_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    
    # Pre-set state and data
    await dp.storage.set_state(state_key, StateFest.sending_sum)
    await dp.storage.update_data(state_key, {'level_1': 'Participant1', 'msg': 'Prompt'})

    await dp.feed_update(router_app_context.bot, create_message_update(user_id, "10.5"))
    
    # Should call send use case (via cmd_send_04)
    setup_fest_mocks.send_uc.execute.assert_called_once()
    
    # Verify state cleared
    assert await dp.storage.get_state(state_key) is None
    
    # Verify confirmation message (localized as confirm_send usually)
    req = get_latest_msg(mock_telegram)
    assert req is not None
    # confirm_send is the key usually returned by mock localization
    assert "confirm_send" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_reload_fest_menu(mock_telegram, router_app_context, setup_fest_mocks):
    """Test /reload_fest_menu command (admin only)."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(fest_router)

    user_id = 123
    # Username must match the itolstov in router
    update = create_message_update(user_id, "/reload_fest_menu", username="itolstov")
    
    with patch("routers.fest.load_fest_info", AsyncMock(return_value={"New": "Menu"})):
        await dp.feed_update(router_app_context.bot, update, app_context=router_app_context)

    assert config.fest_menu == {"New": "Menu"}
    req = get_latest_msg(mock_telegram)
    assert "redy" in req["data"]["text"]
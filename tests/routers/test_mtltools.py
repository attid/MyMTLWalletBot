import pytest
import jsonpickle  # type: ignore
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import types
from aiogram.fsm.storage.base import StorageKey

from routers.mtltools import (
    router as mtltools_router,
    StateTools,
    DonateCallbackData,
    BIMCallbackData,
)
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if mtltools_router.parent_router:
        mtltools_router._parent_router = None

@pytest.fixture
def setup_mtltools_mocks(router_app_context):
    """
    Common mock setup for mtltools router tests.
    """
    class MTLToolsMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default Stellar mocks
            self.mock_acc = MagicMock()
            self.mock_acc.account.account_id = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            self.mock_acc.account.account.account_id = self.mock_acc.account.account_id
            
    return MTLToolsMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')]
    return msgs[-1] if msgs else None


@pytest.mark.asyncio
async def test_cmd_tools_menu(mock_telegram, router_app_context, setup_mtltools_mocks):
    """Test clicking MTLTools: should show tools menu."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtltools_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "MTLTools"))
    
    req = get_latest_msg(mock_telegram)
    assert "mtl_tools_msg" in req["data"]["text"]
    assert "MTLToolsDonate" in req["data"]["reply_markup"]
    assert "MTLToolsDelegate" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_tools_delegate_view(mock_telegram, router_app_context, setup_mtltools_mocks):
    """Test viewing delegate status."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtltools_router)

    with patch("routers.mtltools.stellar_get_data", AsyncMock(return_value={"mtl_delegate": "GDELEGATE"})):
        await dp.feed_update(router_app_context.bot, create_callback_update(123, "MTLToolsDelegate"))
    
    req = get_latest_msg(mock_telegram)
    assert "delegate_start" in req["data"]["text"]
    assert "MTLToolsAddDelegate" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_tools_del_delegate(mock_telegram, router_app_context, setup_mtltools_mocks):
    """Test deleting delegate."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtltools_router)

    with patch("routers.mtltools.stellar_get_data", AsyncMock(return_value={"mtl_delegate": "GDELEGATE"})), \
         patch("routers.mtltools.stellar_get_user_account", AsyncMock(return_value=setup_mtltools_mocks.mock_acc)), \
         patch("routers.mtltools.cmd_gen_data_xdr", AsyncMock(return_value="XDR_DEL")):
        
        await dp.feed_update(router_app_context.bot, create_callback_update(123, "MTLToolsDelDelegate"))
    
    req = get_latest_msg(mock_telegram)
    assert "delegate_delete" in req["data"]["text"]
    assert "Yes" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_add_delegate_flow(mock_telegram, router_app_context, setup_mtltools_mocks):
    """Test full add delegate flow."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtltools_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)

    # 1. Start Add
    with patch("routers.mtltools.have_free_xlm", AsyncMock(return_value=True)):
        await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "MTLToolsAddDelegate"))
    
    assert await dp.storage.get_state(state_key) == StateTools.delegate_for

    # 2. Send Address
    mock_target = MagicMock()
    mock_target.account.account.account_id = "GTARGET"
    
    with patch("routers.mtltools.stellar_check_account", AsyncMock(return_value=mock_target)), \
         patch("routers.mtltools.stellar_get_user_account", AsyncMock(return_value=setup_mtltools_mocks.mock_acc)), \
         patch("routers.mtltools.cmd_gen_data_xdr", AsyncMock(return_value="XDR_ADD")):
        
        await dp.feed_update(router_app_context.bot, create_message_update(user_id, "GTARGET", update_id=2, message_id=2))

    req = get_latest_msg(mock_telegram)
    assert "delegate_add" in req["data"]["text"]
    assert "Yes" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_donate_management_flow(mock_telegram, router_app_context, setup_mtltools_mocks):
    """Test viewing and adding a donation."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtltools_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)

    # 1. View Donates
    with patch("routers.mtltools.stellar_get_data", AsyncMock(return_value={"mtl_donate_test=5": "GADDR"})):
        await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "MTLToolsDonate"))
    
    req = get_latest_msg(mock_telegram)
    assert "donate_show" in req["data"]["text"]
    assert "test" in req["data"]["reply_markup"]

    # 2. Start Add Donate
    with patch("routers.mtltools.have_free_xlm", AsyncMock(return_value=True)):
        await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "AddDonate", update_id=2))
    
    assert await dp.storage.get_state(state_key) == StateTools.donate_address

    # 3. Enter Address -> enter name -> enter percent
    mock_target = MagicMock()
    mock_target.account.account.account_id = "GTARGET"
    
    with patch("routers.mtltools.stellar_check_account", AsyncMock(return_value=mock_target)):
        await dp.feed_update(router_app_context.bot, create_message_update(user_id, "GTARGET", update_id=3, message_id=3))
    assert await dp.storage.get_state(state_key) == StateTools.donate_name
    
    await dp.feed_update(router_app_context.bot, create_message_update(user_id, "Charity", update_id=4, message_id=4))
    assert await dp.storage.get_state(state_key) == StateTools.donate_persent

    with patch("routers.mtltools.stellar_get_user_account", AsyncMock(return_value=setup_mtltools_mocks.mock_acc)), \
         patch("routers.mtltools.cmd_gen_data_xdr", AsyncMock(return_value="XDR_DONATE")):
        await dp.feed_update(router_app_context.bot, create_message_update(user_id, "10.5", update_id=5, message_id=5))

    req = get_latest_msg(mock_telegram)
    assert "donate_end" in req["data"]["text"]
    assert "Yes" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_bim_management_flow(mock_telegram, router_app_context, setup_mtltools_mocks):
    """Test viewing and adding a BIM (Business Identification)."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtltools_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)

    # 1. View BIMs
    with patch("routers.mtltools.stellar_get_data", AsyncMock(return_value={"bod_shop": "GADDR"})):
        await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "MTLToolsAddBIM"))
    
    req = get_latest_msg(mock_telegram)
    assert "show_bim" in req["data"]["text"]
    assert "shop" in req["data"]["reply_markup"]

    # 2. Start Add BIM
    with patch("routers.mtltools.have_free_xlm", AsyncMock(return_value=True)):
        await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "AddBIM", update_id=2))
    
    assert await dp.storage.get_state(state_key) == StateTools.bim_address

    # 3. Enter Address -> enter name
    mock_target = MagicMock()
    mock_target.account.account.account_id = "GTARGET"
    
    with patch("routers.mtltools.stellar_check_account", AsyncMock(return_value=mock_target)):
        await dp.feed_update(router_app_context.bot, create_message_update(user_id, "GTARGET", update_id=3, message_id=3))
    assert await dp.storage.get_state(state_key) == StateTools.bim_name

    with patch("routers.mtltools.stellar_get_user_account", AsyncMock(return_value=setup_mtltools_mocks.mock_acc)), \
         patch("routers.mtltools.cmd_gen_data_xdr", AsyncMock(return_value="XDR_BIM")):
        await dp.feed_update(router_app_context.bot, create_message_update(user_id, "ShopName", update_id=4, message_id=4))

    req = get_latest_msg(mock_telegram)
    assert "add_bim_end" in req["data"]["text"]
    assert "Yes" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_tools_update_multi(mock_telegram, router_app_context, setup_mtltools_mocks):
    """Test MTLToolsUpdateMulti flow."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtltools_router)

    user_id = 123
    
    with patch("routers.mtltools.stellar_get_user_account", AsyncMock(return_value=setup_mtltools_mocks.mock_acc)), \
         patch("routers.mtltools.check_account_id_from_grist", AsyncMock(return_value=True)), \
         patch("routers.mtltools.stellar_get_multi_sign_xdr", AsyncMock(return_value="XDR_MULTI")), \
         patch("routers.mtltools.get_web_request", AsyncMock(return_value=(200, {"text": "Decoded XDR Info"}))), \
         patch("routers.mtltools.cmd_check_xdr", AsyncMock()) as mock_check:
        
        await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "MTLToolsUpdateMulti"))

    # Verify user received info and transition to signing
    msgs = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert any("Decoded XDR Info" in m["data"]["text"] for m in msgs)
    mock_check.assert_called_once()

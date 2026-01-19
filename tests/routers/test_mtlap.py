"""
Router tests for routers/mtlap.py

Tests MTLAP (Mass Transfer Ledger Asset Platform) tools:
- Delegate management for Assembly (A) and Council (C)
- Recommendation system

Follows testing rules from tests/README.md:
- Uses mock_telegram for Telegram API
- Uses mock_horizon for Stellar API (no patches!)
- Uses router_app_context for dependency injection
- Tests end-to-end behavior via dp.feed_update
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from aiogram.fsm.storage.base import StorageKey

from routers.mtlap import (
    MTLAPStateTools,
    RECOMMEND_PREFIX,
    router as mtlap_router,
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
    if mtlap_router.parent_router:
        mtlap_router._parent_router = None


@pytest.fixture
def setup_mtlap_mocks(router_app_context):
    """
    Common mock setup for mtlap router tests.
    Provides helper methods to configure specific test scenarios.
    """
    class MtlapMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = "GUSER1234567890123456789012345678901234567890123456"

            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

            # Default user mock
            self.user = MagicMock()
            self.user.lang = 'en'

            user_repo = MagicMock()
            user_repo.get_by_id = AsyncMock(return_value=self.user)
            self.ctx.repository_factory.get_user_repository.return_value = user_repo
            
            # Default stellar service mocks
            # get_account_details returns dict with 'data' field
            self.ctx.stellar_service.get_account_details = AsyncMock(return_value={
                'data': {}  # Empty data by default
            })
            
            # check_account_exists returns bool
            self.ctx.stellar_service.check_account_exists = AsyncMock(return_value=True)
            
            # build_manage_data_transaction returns XDR string
            self.ctx.stellar_service.build_manage_data_transaction = AsyncMock(return_value="MOCK_XDR_STRING")

        def set_account_data(self, data: dict):
            """Configure account data entries (already decoded)."""
            self.ctx.stellar_service.get_account_details = AsyncMock(return_value={
                'data': data
            })

        def set_account_exists(self, exists: bool):
            """Configure whether account exists check returns True/False."""
            self.ctx.stellar_service.check_account_exists = AsyncMock(return_value=exists)

        def set_free_xlm(self, amount: float):
            """Helper to set free_xlm in state data."""
            # Note: This is a helper that tests should call with state
            # Tests need to manually set state data
            return {"free_xlm": amount}

    return MtlapMockHelper(router_app_context)


# --- Tests for MTLAP Tools Menu ---

@pytest.mark.asyncio
async def test_cmd_mtlap_tools(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test MTLAPTools callback: should show tools menu.
    Verifies main menu with Assembly, Council, Recommend buttons.
    """
    user_id = 123

    # Setup router with middleware
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Trigger MTLAP tools menu
    update = create_callback_update(user_id, "MTLAPTools")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify menu was sent
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None, "sendMessage should be called"
    assert "mtlap_tools_text" in req["data"]["text"]

    # Verify callback was answered
    answer = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert answer is not None


# --- Tests for Delegate A (Assembly) ---

@pytest.mark.asyncio
async def test_cmd_mtlap_tools_delegate_a(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test Delegate A callback: should show delegate management menu.
    Displays current delegate status with add/delete options.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state with existing delegate data
    setup_mtlap_mocks.set_account_data({"mtla_a_delegate": "DelegateA"})

    # Trigger delegate A menu
    update = create_callback_update(user_id, "MTLAPToolsDelegateA")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify delegate menu was sent
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "delegate_start" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_mtlap_tools_add_delegate_a_low_xlm(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test Add Delegate A when user has low XLM: should show alert.
    have_free_xlm returns False, blocking the operation.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state with low free_xlm
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_data(key=storage_key, data={"free_xlm": 0.1})  # Low XLM

    # Try to add delegate
    update = create_callback_update(user_id, "MTLAPToolsAddDelegateA")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify alert was shown (no sendMessage, only answerCallbackQuery with alert)
    msg_req = get_telegram_request(mock_telegram, "sendMessage")
    assert msg_req is None, "Should not send message on low XLM"

    answer = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert answer is not None
    assert answer["data"].get("show_alert") == "true"  # Mock returns string, not bool
    assert "low_xlm" in answer["data"].get("text", "")


@pytest.mark.asyncio
async def test_cmd_mtlap_tools_add_delegate_a_ok(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test Add Delegate A with sufficient XLM: should prompt for delegate address.
    have_free_xlm returns True, allowing the operation.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state with sufficient free_xlm
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_data(key=storage_key, data={"free_xlm": 1.0})

    # Add delegate
    update = create_callback_update(user_id, "MTLAPToolsAddDelegateA")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify address prompt was sent
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "delegate_send_address" in req["data"]["text"]

    # Verify state was set
    state = await dp.storage.get_state(key=storage_key)
    assert state == MTLAPStateTools.delegate_for_a


@pytest.mark.asyncio
async def test_cmd_mtlap_send_add_delegate_for_a_valid(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test sending valid delegate address for A: should generate XDR and confirm.
    mock_horizon provides the account data.
    """
    user_id = 123
    delegate_address = "GDELEGATE1234567890123456789012345678901234567890123456"

    # Configure mock_horizon with delegate account
    mock_horizon.set_account(delegate_address, balances=[
        {"asset_type": "native", "balance": "100.0"}
    ])

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=MTLAPStateTools.delegate_for_a)

    # Send delegate address
    update = create_message_update(user_id, delegate_address)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify confirmation message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "delegate_add" in req["data"]["text"]

    # Verify XDR was stored in state
    data = await dp.storage.get_data(key=storage_key)
    assert "xdr" in data


@pytest.mark.asyncio
async def test_cmd_mtlap_send_add_delegate_for_a_invalid(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test sending invalid delegate address for A: should show error.
    mock_horizon returns 404 for unknown accounts.
    """
    user_id = 123
    invalid_address = "GINVALID12345678901234567890123456789012345678901234"
    
    # Configure account exists to return False
    setup_mtlap_mocks.set_account_exists(False)

    # Setup router (mock_horizon will return 404 for unknown account)
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=MTLAPStateTools.delegate_for_a)

    # Send invalid address
    update = create_message_update(user_id, invalid_address)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify error message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_error2" in req["data"]["text"]


# --- Tests for Delegate C (Council) ---

@pytest.mark.asyncio
async def test_cmd_mtlap_tools_delegate_c(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test Delegate C callback: should show council delegate management menu.
    Displays current C delegate status with add/delete options.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state with existing C delegate
    setup_mtlap_mocks.set_account_data({"mtla_c_delegate": "DelegateC"})

    # Trigger delegate C menu
    update = create_callback_update(user_id, "MTLAPToolsDelegateC")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify delegate menu was sent
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "delegate_start" in req["data"]["text"]


# --- Tests for Recommendations ---

@pytest.mark.asyncio
async def test_cmd_mtlap_tools_recommend(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test Recommend callback: should show recommendation prompt.
    Displays existing recommendations count.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state with existing recommendations
    setup_mtlap_mocks.set_account_data({
        "RecommendToMTLA": "GACC1",
        "RecommendToMTLA1": "GACC2",
    })

    # Trigger recommend menu
    update = create_callback_update(user_id, "MTLAPToolsRecommend")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify recommendation prompt
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "recommend_prompt" in req["data"]["text"]

    # Verify state was set
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    state = await dp.storage.get_state(key=storage_key)
    assert state == MTLAPStateTools.recommend_for


@pytest.mark.asyncio
async def test_cmd_mtlap_send_recommend_valid(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test sending valid recommendation: should generate XDR and confirm.
    mock_horizon validates the recommended account.
    """
    user_id = 123
    recommend_address = "GRECOMMEND1234567890123456789012345678901234567890"

    # Configure mock_horizon with recommended account
    mock_horizon.set_account(recommend_address, balances=[
        {"asset_type": "native", "balance": "50.0"}
    ])
    
    # Configure account exists check
    setup_mtlap_mocks.set_account_exists(True)

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state with existing recommendations
    setup_mtlap_mocks.set_account_data({"RecommendToMTLA": "GOLD1"})
    
    # Set FSM state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=MTLAPStateTools.recommend_for)

    # Send recommendation
    update = create_message_update(user_id, recommend_address)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify confirmation message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "recommend_confirm" in req["data"]["text"]

    # Verify XDR was stored
    data = await dp.storage.get_data(key=storage_key)
    assert "xdr" in data


@pytest.mark.asyncio
async def test_cmd_mtlap_send_recommend_invalid(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test sending invalid recommendation: should show error.
    mock_horizon returns 404 for unknown accounts.
    """
    user_id = 123
    invalid_address = "GINVALID12345678901234567890123456789012345678901234"
    
    # Configure account exists check to return False
    setup_mtlap_mocks.set_account_exists(False)

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=MTLAPStateTools.recommend_for)

    # Send invalid address
    update = create_message_update(user_id, invalid_address)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify error message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_error2" in req["data"]["text"]


# --- Tests for Delegate Deletion ---

@pytest.mark.asyncio
async def test_cmd_mtlap_tools_del_delegate_a_with_delegate(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test deleting existing A delegate: should generate XDR for removal.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state with delegate to delete
    setup_mtlap_mocks.set_account_data({"mtla_a_delegate": "GDELEGATE"})

    # Trigger delete
    update = create_callback_update(user_id, "MTLAPToolsDelDelegateA")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify delete confirmation
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "delegate_delete" in req["data"]["text"]

    # Verify XDR was stored
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    data = await dp.storage.get_data(key=storage_key)
    assert "xdr" in data


@pytest.mark.asyncio
async def test_cmd_mtlap_tools_del_delegate_a_no_delegate(mock_telegram, mock_horizon, router_app_context, dp, setup_mtlap_mocks):
    """
    Test deleting when no A delegate exists: should show "Nothing to delete".
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(mtlap_router)

    # Set state without delegate
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_data(key=storage_key, data={})

    # Try to delete
    update = create_callback_update(user_id, "MTLAPToolsDelDelegateA")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify "nothing to delete" answer (no sendMessage)
    msg_req = get_telegram_request(mock_telegram, "sendMessage")
    assert msg_req is None

    answer = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert answer is not None
    assert "Nothing to delete" in answer["data"].get("text", "")

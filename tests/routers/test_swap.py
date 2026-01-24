
import pytest
import jsonpickle  # type: ignore
from unittest.mock import AsyncMock, MagicMock, patch

from routers.swap import (
    router as swap_router,
    StateSwapToken,
    SwapAssetFromCallbackData,
    SwapAssetForCallbackData,
)
from core.domain.value_objects import Balance, PaymentResult
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
    if swap_router.parent_router:
        swap_router._parent_router = None

@pytest.fixture
def setup_swap_mocks(router_app_context):
    """
    Common mock setup for swap router tests.
    """
    class SwapMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            self.wallet.assets_visibility = "{}"
            
            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

            # Default user mock
            self.user = MagicMock()
            self.user.can_5000 = 1
            self.user.lang = 'en'
            user_repo = MagicMock()
            user_repo.get_by_id = AsyncMock(return_value=self.user)
            self.ctx.repository_factory.get_user_repository.return_value = user_repo

            # Default balances
            valid_issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
            self.balances = [
                Balance(asset_code="XLM", balance="100.0", asset_issuer=None, asset_type="native"),
                Balance(asset_code="EURMTL", balance="50.0", asset_issuer=valid_issuer, asset_type="credit_alphanum12"),
            ]
            balance_uc = MagicMock()
            balance_uc.execute = AsyncMock(return_value=self.balances)
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = balance_uc

            # Default swap use case
            swap_uc = MagicMock()
            swap_uc.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR_SWAP"))
            self.ctx.use_case_factory.create_swap_assets.return_value = swap_uc

    return SwapMockHelper(router_app_context)


@pytest.mark.asyncio
async def test_cmd_swap_start(mock_telegram, router_app_context, setup_swap_mocks):
    """Test clicking Swap button: should show token selection."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(swap_router)

    update = create_callback_update(user_id=123, callback_data="Swap")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "choose_token_swap" in req["data"]["text"]
    # Verify tokens in keyboard
    assert "XLM" in req["data"]["reply_markup"]
    assert "EURMTL" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cq_swap_choose_token_from(mock_telegram, router_app_context, setup_swap_mocks, mock_horizon, horizon_server_config):
    """Test selecting source token: should show destination tokens."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(swap_router)

    user_id = 123
    # Set state data with available assets
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    await state.update_data(assets=jsonpickle.encode(setup_swap_mocks.balances))

    cb_data = SwapAssetFromCallbackData(answer="XLM").pack()
    
    # Configure Mock Horizon to return valid paths for EURMTL
    # stellar_check_receive_asset calls strict-send paths
    mock_horizon.set_paths([
        {
            "destination_asset_type": "credit_alphanum12",
            "destination_asset_code": "EURMTL",
            "destination_asset_issuer": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V", 
            "destination_amount": "9.5",
            "source_amount": "10.0",
            "path": []
        }
    ])
    
    # Patch the global config used by legacy stellar_tools
    with patch("other.config_reader.config.horizon_url", horizon_server_config["url"]):
        update = create_callback_update(user_id=user_id, callback_data=cb_data)
        await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "choose_token_swap2" in req["data"]["text"]
    assert "EURMTL" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cq_swap_choose_token_for(mock_telegram, router_app_context, setup_swap_mocks):
    """Test selecting destination token: should ask for amount."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(swap_router)

    user_id = 123
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    await state.update_data(
        assets=jsonpickle.encode(setup_swap_mocks.balances),
        send_asset_code="XLM",
        send_asset_issuer=None,
        send_asset_max_sum="100.0",
        send_asset_blocked_sum=0.0
    )

    cb_data = SwapAssetForCallbackData(answer="EURMTL").pack()
    update = create_callback_update(user_id, cb_data)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "send_sum_swap" in req["data"]["text"]
    assert "SwapStrictReceive" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_swap_sum_execution(mock_telegram, router_app_context, setup_swap_mocks, mock_horizon, horizon_server_config):
    """Test entering amount: should show confirmation."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(swap_router)

    user_id = 123
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    await state.set_state(StateSwapToken.swap_sum)
    valid_issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    await state.update_data(
        send_asset_code="XLM",
        send_asset_issuer=None,
        receive_asset_code="EURMTL",
        receive_asset_issuer=valid_issuer,
        cancel_offers=False,
        msg="Prompt"
    )

    # Configure Mock Horizon for strict-send path
    mock_horizon.set_paths([
        {
            "destination_asset_type": "credit_alphanum12",
            "destination_asset_code": "EURMTL",
            "destination_asset_issuer": valid_issuer,
            "destination_amount": "9.5",
            "source_amount": "10.0",
            "path": []
        }
    ])

    # Patch external check for estimated receive sum
    with patch("other.config_reader.config.horizon_url", horizon_server_config["url"]):
        update = create_message_update(user_id, "10.0")
        await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    # Verify TEMPLATE key is present (mock my_gettext returns key or "text KEY")
    assert "confirm_swap" in req["data"]["text"]
    
    # Verify UseCase call
    router_app_context.use_case_factory.create_swap_assets.return_value.execute.assert_called_once()


@pytest.mark.asyncio
async def test_cq_swap_strict_receive_switch(mock_telegram, router_app_context, setup_swap_mocks):
    """Test clicking 'Exact amount to receive': should ask for receive sum."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(swap_router)

    user_id = 123
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    await state.set_state(StateSwapToken.swap_sum)
    await state.update_data(receive_asset_code="EURMTL")

    update = create_callback_update(user_id, "SwapStrictReceive")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    assert await state.get_state() == StateSwapToken.swap_receive_sum
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "enter_strict_receive_sum" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_swap_receive_sum_execution(mock_telegram, router_app_context, setup_swap_mocks, mock_horizon, horizon_server_config):
    """Test entering receive amount: should show strict swap confirmation."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(swap_router)

    user_id = 123
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    await state.set_state(StateSwapToken.swap_receive_sum)
    valid_issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    await state.update_data(
        send_asset_code="XLM",
        send_asset_issuer=None,
        receive_asset_code="EURMTL",
        receive_asset_issuer=valid_issuer,
        cancel_offers=False
    )

    # Configure Mock Horizon for strict-receive path
    mock_horizon.set_paths([
        {
            "destination_asset_type": "credit_alphanum12",
            "destination_asset_code": "EURMTL",
            "destination_asset_issuer": valid_issuer,
            "destination_amount": "10.0",
            "source_amount": "10.5",
            "path": []
        }
    ])

    # Patch external check for estimated send sum
    with patch("other.config_reader.config.horizon_url", horizon_server_config["url"]):
        update = create_message_update(user_id, "10.0")
        await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "confirm_swap" in req["data"]["text"]
    
    # Verify UseCase call with strict_receive=True
    call_kwargs = router_app_context.use_case_factory.create_swap_assets.return_value.execute.call_args.kwargs
    assert call_kwargs.get("strict_receive") is True


@pytest.mark.asyncio
async def test_cq_swap_cancel_offers_toggle(mock_telegram, router_app_context, setup_swap_mocks):
    """Test toggling offer cancellation."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(swap_router)

    user_id = 123
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    await state.set_state(StateSwapToken.swap_sum)
    await state.update_data(
        cancel_offers=False,
        msg="Test Prompt",
        send_asset_code="XLM",
        receive_asset_code="EURMTL"
    )

    update = create_callback_update(user_id, "CancelOffers")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    data = await state.get_data()
    assert data.get("cancel_offers") is True
    
    # UI should be refreshed
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None


@pytest.mark.asyncio
async def test_cmd_swap_start_custom_token(mock_telegram, router_app_context, setup_swap_mocks):
    """
    Mandatory test: Ensure custom tokens (e.g. UNLIMITED) are visible in SWAP list.
    User requirement: 'my token should be here and in send and in swap'.
    """
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(swap_router)

    # Add UNLIMITED token to balances
    custom_balance = Balance(
        asset_code="UNLIMITED", 
        balance="1000.0", 
        asset_issuer="G_UNLIMITED_ISSUER", 
        asset_type="credit_alphanum12"
    )
    setup_swap_mocks.balances.append(custom_balance)
    setup_swap_mocks.ctx.use_case_factory.create_get_wallet_balance.return_value.execute.return_value = setup_swap_mocks.balances

    update = create_callback_update(user_id=123, callback_data="Swap")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "UNLIMITED" in req["data"]["reply_markup"]

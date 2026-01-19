import pytest
import jsonpickle
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram.fsm.storage.base import StorageKey

from routers.trade import (
    router as trade_router,
    StateSaleToken,
    SaleAssetCallbackData,
    BuyAssetCallbackData,
    EditOrderCallbackData,
)
from core.domain.value_objects import Balance, PaymentResult, Asset as DomainAsset
from other.mytypes import MyOffer, MyAsset
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)

VALID_ISSUER = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if trade_router.parent_router:
        trade_router._parent_router = None

@pytest.fixture
def setup_trade_mocks(router_app_context):
    """
    Common mock setup for trade router tests.
    """
    class TradeMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default Wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            self.wallet.assets_visibility = "{}"
            
            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

            # Default User mock
            self.user = MagicMock()
            self.user.can_5000 = 1
            user_repo = MagicMock()
            user_repo.get_by_id = AsyncMock(return_value=self.user)
            self.ctx.repository_factory.get_user_repository.return_value = user_repo

            # Default Balances
            self.balances = [
                Balance(asset_code="XLM", balance="100.0", asset_issuer=None, asset_type="native"),
                Balance(asset_code="EURMTL", balance="50.0", 
                       asset_issuer=VALID_ISSUER, 
                       asset_type="credit_alphanum12"),
            ]
            balance_uc = MagicMock()
            balance_uc.execute = AsyncMock(return_value=self.balances)
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = balance_uc

            # Default ManageOffer use case
            manage_uc = MagicMock()
            manage_uc.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR_MANAGE_OFFER"))
            self.ctx.use_case_factory.create_manage_offer.return_value = manage_uc

    return TradeMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')]
    return msgs[-1] if msgs else None


@pytest.mark.asyncio
async def test_cmd_market_menu(mock_telegram, router_app_context, setup_trade_mocks):
    """Test clicking Market: should show main trade menu."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(trade_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "Market"))
    
    req = get_latest_msg(mock_telegram)
    assert req is not None
    assert "kb_market" in req["data"]["text"]
    assert "NewOrder" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_sale_new_order_start(mock_telegram, router_app_context, setup_trade_mocks):
    """Test 'NewOrder' callback: should show asset selection."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(trade_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "NewOrder"))
    
    req = get_latest_msg(mock_telegram)
    assert "choose_token_sale" in req["data"]["text"]
    assert "XLM" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cq_trade_choose_token_sell(mock_telegram, router_app_context, setup_trade_mocks):
    """Test selecting token to sell: should show token to buy selection."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(trade_router)

    user_id = 123
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_data(storage_key, {"assets": jsonpickle.encode(setup_trade_mocks.balances)})

    cb_data = SaleAssetCallbackData(answer="XLM").pack()
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, cb_data))
    
    req = get_latest_msg(mock_telegram)
    assert "choose_token_swap2" in req["data"]["text"]
    assert "EURMTL" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_trade_creation_flow(mock_telegram, router_app_context, setup_trade_mocks):
    """Test full trade creation flow: sell sum -> buy sum -> confirmation."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(trade_router)

    user_id = 123
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    
    # 1. Start in selling_sum state
    await dp.storage.set_state(storage_key, StateSaleToken.selling_sum)
    await dp.storage.set_data(storage_key, {
        "send_asset_code": "XLM", "send_asset_issuer": None,
        "receive_asset_code": "EURMTL", 
        "receive_asset_issuer": VALID_ISSUER,
        "market_link": "link"
    })

    # Enter Sell Amount
    await dp.feed_update(router_app_context.bot, create_message_update(user_id, "100.0"))
    assert await dp.storage.get_state(storage_key) == StateSaleToken.selling_receive_sum
    # Don't clear telegram log, just look at latest later

    # 2. Enter Buy Amount (Price)
    await dp.feed_update(router_app_context.bot, create_message_update(user_id, "10.0", message_id=2, update_id=2))
    
    # Verify XDR generation and confirmation message
    req = get_latest_msg(mock_telegram)
    assert req is not None
    assert "confirm_sale" in req["data"]["text"]
    
    # Verify UseCase called with correct price (10 / 100 = 0.1)
    router_app_context.use_case_factory.create_manage_offer.return_value.execute.assert_called_once()
    args = router_app_context.use_case_factory.create_manage_offer.return_value.execute.call_args[1]
    assert args['amount'] == 100.0
    assert args['price'] == 0.1


@pytest.mark.asyncio
async def test_cmd_show_orders(mock_telegram, mock_horizon, router_app_context, setup_trade_mocks):
    """Test ShowOrders: should list user's active offers."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(trade_router)

    # Mock active offers via mock_horizon
    mock_offer = {
        "id": "12345",
        "amount": "100.0",
        "price": "0.5",
        "selling": {"asset_code": "XLM", "asset_type": "native"},
        "buying": {"asset_code": "EURMTL", "asset_issuer": VALID_ISSUER}
    }
    mock_horizon.set_offers(setup_trade_mocks.wallet.public_key, [mock_offer])

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "ShowOrders"))
    
    req = get_latest_msg(mock_telegram)
    assert "Choose order" in req["data"]["text"]
    assert "100.0 XLM" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_edit_order_options(mock_telegram, router_app_context, setup_trade_mocks):
    """Test selecting an order to edit: should show Edit options."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(trade_router)

    user_id = 123
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    
    # Setup offers in state. ID as int is fine here as it's not going through from_dict
    offer = MyOffer(
        id=555, amount="10.0", price="2.0",
        selling=MyAsset(asset_code="XLM"),
        buying=MyAsset(asset_code="EURMTL", asset_issuer=VALID_ISSUER)
    )
    await dp.storage.set_data(storage_key, {"offers": jsonpickle.encode([offer])})

    cb_data = EditOrderCallbackData(answer=555).pack()
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, cb_data))
    
    req = get_latest_msg(mock_telegram)
    assert "EditOrderAmount" in req["data"]["reply_markup"]
    assert "EditOrderCost" in req["data"]["reply_markup"]
    assert "DeleteOrder" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_delete_order_execution(mock_telegram, router_app_context, setup_trade_mocks):
    """Test clicking DeleteOrder: should generate deletion XDR."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(trade_router)

    user_id = 123
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    
    offer = MyOffer(
        id=555, amount="10.0", price="2.0",
        selling=MyAsset(asset_code="XLM"),
        buying=MyAsset(asset_code="EURMTL", asset_issuer=VALID_ISSUER)
    )
    await dp.storage.set_data(storage_key, {
        "offers": jsonpickle.encode([offer]),
        "edit_offer_id": 555
    })

    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "DeleteOrder"))
    
    # Verify deletion UseCase call (amount=0)
    router_app_context.use_case_factory.create_manage_offer.return_value.execute.assert_called_once()
    args = router_app_context.use_case_factory.create_manage_offer.return_value.execute.call_args[1]
    assert args['amount'] == 0.0
    assert args['offer_id'] == 555
    
    req = get_latest_msg(mock_telegram)
    assert "delete_sale" in req["data"]["text"]
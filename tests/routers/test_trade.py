
import pytest
import jsonpickle
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import AsyncMock, MagicMock, patch
import datetime

from routers.trade import (
    router as trade_router,
    StateSaleToken,
    SaleAssetCallbackData,
    BuyAssetCallbackData,
    EditOrderCallbackData,
)
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from other.mytypes import Balance


class MockDbMiddleware(BaseMiddleware):
    def __init__(self, app_context):
        self.app_context = app_context

    async def __call__(self, handler, event, data):
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.all.return_value = []
        session.execute.return_value = result
        data["session"] = session
        data["app_context"] = self.app_context
        return await handler(event, data)


@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if trade_router.parent_router:
         trade_router._parent_router = None


@pytest.fixture
async def trade_app_context(mock_app_context, mock_telegram):
    """Setup app_context with real bot for mock_server integration."""
    session = AiohttpSession(api=TelegramAPIServer.from_base(MOCK_SERVER_URL))
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    mock_app_context.bot = bot
    mock_app_context.dispatcher = Dispatcher()
    yield mock_app_context
    await bot.session.close()


def _last_request(mock_server, method):
    return next((req for req in reversed(mock_server) if req["method"] == method), None)


# --- Market menu ---

@pytest.mark.asyncio
async def test_cmd_market(mock_telegram, trade_app_context, dp):
    """
    Test Market callback: should show market menu.
    """
    dp.callback_query.middleware(MockDbMiddleware(trade_app_context))
    dp.include_router(trade_router)

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
            data="Market"
        )
    )

    await dp.feed_update(bot=trade_app_context.bot, update=update, app_context=trade_app_context)

    req = _last_request(mock_telegram, "sendMessage")
    assert req is not None, "sendMessage should be called"

    req_answer = _last_request(mock_telegram, "answerCallbackQuery")
    assert req_answer is not None, "answerCallbackQuery should be called"


@pytest.mark.asyncio
async def test_cmd_sale_new_order(mock_telegram, trade_app_context, dp):
    """
    Test NewOrder callback: should show available tokens for sale.
    """
    dp.callback_query.middleware(MockDbMiddleware(trade_app_context))
    dp.include_router(trade_router)

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
            data="NewOrder"
        )
    )

    # Mock wallet repository via app_context DI
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"

    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    trade_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Mock get wallet balance use case via app_context DI
    mock_balance = Balance(asset_code="XLM", balance="100.0", asset_issuer=None)

    mock_use_case = AsyncMock()
    mock_use_case.execute = AsyncMock(return_value=[mock_balance])
    trade_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_use_case

    await dp.feed_update(bot=trade_app_context.bot, update=update, app_context=trade_app_context)

    req = _last_request(mock_telegram, "sendMessage")
    assert req is not None, "sendMessage should be called"


@pytest.mark.asyncio
async def test_cmd_sale_new_order_low_xlm(mock_telegram, trade_app_context, dp):
    """
    Test NewOrder callback with low XLM: should show alert.
    """
    dp.callback_query.middleware(MockDbMiddleware(trade_app_context))
    dp.include_router(trade_router)

    update = types.Update(
        update_id=3,
        callback_query=types.CallbackQuery(
            id="cb3",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=3,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="NewOrder"
        )
    )

    # Mock wallet repository via app_context DI
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"

    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    trade_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Mock get wallet balance use case - return low XLM balance
    mock_balance = Balance(asset_code="XLM", balance="0.1", asset_issuer=None)  # Less than 0.5

    mock_use_case = AsyncMock()
    mock_use_case.execute = AsyncMock(return_value=[mock_balance])
    trade_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_use_case

    await dp.feed_update(bot=trade_app_context.bot, update=update, app_context=trade_app_context)

    req = _last_request(mock_telegram, "answerCallbackQuery")
    assert req is not None, "answerCallbackQuery should be called"
    assert req["data"].get("show_alert") == "true", "Should show alert for low XLM"


@pytest.mark.asyncio
async def test_cq_trade_choose_token_sell(mock_telegram, trade_app_context, dp):
    """
    Test SaleAssetCallbackData: should show buy options.
    """
    dp.callback_query.middleware(MockDbMiddleware(trade_app_context))
    dp.include_router(trade_router)

    # Set up state with assets
    ctx = dp.fsm.get_context(bot=trade_app_context.bot, chat_id=123, user_id=123)
    mock_balance = Balance(asset_code="XLM", balance="100.0", asset_issuer=None)
    await ctx.update_data(assets=jsonpickle.encode([mock_balance]))

    callback_data = SaleAssetCallbackData(answer="XLM")

    update = types.Update(
        update_id=4,
        callback_query=types.CallbackQuery(
            id="cb4",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=4,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data=callback_data.pack()
        )
    )

    await dp.feed_update(bot=trade_app_context.bot, update=update, app_context=trade_app_context)

    req = _last_request(mock_telegram, "sendMessage")
    assert req is not None, "sendMessage should be called"


@pytest.mark.asyncio
async def test_cq_trade_choose_token_buy(mock_telegram, trade_app_context, dp):
    """
    Test BuyAssetCallbackData: should set state to selling_sum.
    """
    dp.callback_query.middleware(MockDbMiddleware(trade_app_context))
    dp.include_router(trade_router)

    # Set up state with assets and send token
    ctx = dp.fsm.get_context(bot=trade_app_context.bot, chat_id=123, user_id=123)
    mock_assets = [Balance(asset_code="USD", balance="50.0", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA")]
    await ctx.update_data(
        assets=jsonpickle.encode(mock_assets),
        send_asset_code="XLM",
        send_asset_issuer=None,
        send_asset_max_sum=100.0
    )

    callback_data = BuyAssetCallbackData(answer="USD")

    update = types.Update(
        update_id=5,
        callback_query=types.CallbackQuery(
            id="cb5",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=5,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data=callback_data.pack()
        )
    )

    await dp.feed_update(bot=trade_app_context.bot, update=update, app_context=trade_app_context)

    req = _last_request(mock_telegram, "sendMessage")
    assert req is not None, "sendMessage should be called"

    # Verify state was set
    state = await ctx.get_state()
    assert state == StateSaleToken.selling_sum


@pytest.mark.asyncio
async def test_cmd_send_sale_sum(mock_telegram, trade_app_context, dp):
    """
    Test sending sale sum: should ask for receive cost.
    """
    dp.message.middleware(MockDbMiddleware(trade_app_context))
    dp.include_router(trade_router)

    # Set up state
    ctx = dp.fsm.get_context(bot=trade_app_context.bot, chat_id=123, user_id=123)
    await ctx.set_state(StateSaleToken.selling_sum)
    await ctx.update_data(
        receive_asset_code="USD",
        send_asset_code="XLM",
        market_link="link"
    )

    update = types.Update(
        update_id=6,
        message=types.Message(
            message_id=6,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="10.0"
        )
    )

    await dp.feed_update(bot=trade_app_context.bot, update=update, app_context=trade_app_context)

    req = _last_request(mock_telegram, "sendMessage")
    assert req is not None, "sendMessage should be called"

    # Verify state changed to selling_receive_sum
    state = await ctx.get_state()
    assert state == StateSaleToken.selling_receive_sum

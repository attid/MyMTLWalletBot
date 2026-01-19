
import pytest
import jsonpickle
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import AsyncMock, MagicMock, patch
import datetime

from routers.swap import (
    router as swap_router,
    StateSwapToken,
    SwapAssetFromCallbackData,
    SwapAssetForCallbackData,
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
    if swap_router.parent_router:
        swap_router._parent_router = None


@pytest.fixture
async def swap_app_context(mock_app_context, mock_server):
    """Setup app_context with real bot for mock_server integration."""
    session = AiohttpSession(api=TelegramAPIServer.from_base(MOCK_SERVER_URL))
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    mock_app_context.bot = bot
    mock_app_context.dispatcher = Dispatcher()
    yield mock_app_context
    await bot.session.close()


def _last_request(mock_server, method):
    return next((req for req in reversed(mock_server) if req["method"] == method), None)


def _text_requests(mock_server):
    return [req for req in mock_server if req["method"] in ("sendMessage", "editMessageText")]


# --- Swap handlers ---

@pytest.mark.asyncio
async def test_cmd_swap_01(mock_server, swap_app_context, dp):
    """
    Test Swap callback: should show available tokens for swap.
    """
    dp.callback_query.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    # Mock wallet repository via app_context DI
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"
    mock_wallet.public_key = "GTEST"

    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    swap_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Mock get wallet balance use case via app_context DI
    mock_balance = Balance(asset_code="XLM", balance="100.0", asset_issuer=None)

    mock_use_case = AsyncMock()
    mock_use_case.execute = AsyncMock(return_value=[mock_balance])
    swap_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_use_case

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
            data="Swap"
        )
    )

    await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

    req = _last_request(mock_server, "sendMessage")
    assert req is not None, "sendMessage should be called"
    # Verify the use case was called
    mock_use_case.execute.assert_called()


@pytest.mark.asyncio
async def test_cmd_swap_01_shows_tokens(mock_server, swap_app_context, dp):
    """
    Test Swap callback: verifies token list is displayed correctly.
    """
    dp.callback_query.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = None  # All visible
    mock_wallet.public_key = "GTEST"

    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    swap_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Multiple balances
    mock_balances = [
        Balance(asset_code="XLM", balance="100.0", asset_issuer=None),
        Balance(asset_code="EURMTL", balance="50.0", asset_issuer="GISSUER"),
    ]

    mock_use_case = AsyncMock()
    mock_use_case.execute = AsyncMock(return_value=mock_balances)
    swap_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_use_case

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
            data="Swap"
        )
    )

    await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

    req = _last_request(mock_server, "sendMessage")
    assert req is not None
    # Verify keyboard contains tokens
    markup = req["data"].get("reply_markup", "")
    assert "XLM" in markup
    assert "EURMTL" in markup


@pytest.mark.asyncio
async def test_cq_swap_choose_token_from(mock_server, swap_app_context, dp):
    """
    Test SwapAssetFromCallbackData: should show tokens to swap for.
    """
    dp.callback_query.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    # Set up state with assets
    ctx = dp.fsm.get_context(bot=swap_app_context.bot, chat_id=123, user_id=123)
    mock_assets = [Balance(asset_code="XLM", balance="100.0", asset_issuer=None)]
    await ctx.update_data(assets=jsonpickle.encode(mock_assets))

    # Mock wallet repository
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"
    mock_wallet.public_key = "GTEST"

    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    swap_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Mock stellar service for offers
    swap_app_context.stellar_service.get_selling_offers = AsyncMock(return_value=[])

    # Mock balance use case
    mock_use_case = AsyncMock()
    mock_use_case.execute = AsyncMock(return_value=mock_assets)
    swap_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_use_case

    callback_data = SwapAssetFromCallbackData(answer="XLM")

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
            data=callback_data.pack()
        )
    )

    # Patch stellar_check_receive_asset - external Stellar API call (allowed per testing rules)
    with patch(
        "routers.swap.stellar_check_receive_asset",
        new_callable=AsyncMock,
        return_value=["USD", "EUR"],
    ):
        await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

        req = _last_request(mock_server, "sendMessage")
        assert req is not None, "sendMessage should be called"


@pytest.mark.asyncio
async def test_cq_swap_choose_token_for(mock_server, swap_app_context, dp):
    """
    Test SwapAssetForCallbackData: should set state to swap_sum.
    """
    dp.callback_query.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    # Set up state with assets and send token
    ctx = dp.fsm.get_context(bot=swap_app_context.bot, chat_id=123, user_id=123)
    mock_assets = [Balance(asset_code="USD", balance="50.0", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA")]
    await ctx.update_data(
        assets=jsonpickle.encode(mock_assets),
        send_asset_code="XLM",
        send_asset_issuer=None,
        send_asset_max_sum=100.0,
        send_asset_blocked_sum=0
    )

    callback_data = SwapAssetForCallbackData(answer="USD")

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

    await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

    req = _last_request(mock_server, "sendMessage")
    assert req is not None, "sendMessage should be called"

    # Verify state was set
    state = await ctx.get_state()
    assert state == StateSwapToken.swap_sum


@pytest.mark.asyncio
async def test_cmd_swap_sum(mock_server, swap_app_context, dp):
    """
    Test sending swap sum: should calculate and show result.
    """
    dp.message.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    # Set up state
    ctx = dp.fsm.get_context(bot=swap_app_context.bot, chat_id=123, user_id=123)
    await ctx.set_state(StateSwapToken.swap_sum)
    await ctx.update_data(
        send_asset_code="XLM",
        send_asset_issuer=None,
        receive_asset_code="USD",
        receive_asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA",
        cancel_offers=False,
        xdr=None,
        msg="Test prompt"
    )

    # Mock user repository via app_context DI
    mock_user = MagicMock()
    mock_user.can_5000 = 1

    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
    swap_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    # Mock swap use case via app_context DI
    mock_swap_use_case = AsyncMock()
    mock_swap_use_case.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR_SWAP"))
    swap_app_context.use_case_factory.create_swap_assets.return_value = mock_swap_use_case

    update = types.Update(
        update_id=5,
        message=types.Message(
            message_id=5,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="10.0"
        )
    )

    # Patch stellar_check_receive_sum - external Stellar API call (allowed per testing rules)
    with patch(
        "routers.swap.stellar_check_receive_sum",
        new_callable=AsyncMock,
        return_value=("9.5", False),
    ):
        await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

        req = _last_request(mock_server, "sendMessage")
        assert req is not None, "sendMessage should be called"

        # Verify swap use case was called
        mock_swap_use_case.execute.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_swap_sum_exceeds_limit(mock_server, swap_app_context, dp):
    """
    Test sending swap sum: should block if sum exceeds limit for restricted users.
    """
    dp.message.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    ctx = dp.fsm.get_context(bot=swap_app_context.bot, chat_id=123, user_id=123)
    await ctx.set_state(StateSwapToken.swap_sum)
    await ctx.update_data(
        send_asset_code="XLM",
        send_asset_issuer=None,
        receive_asset_code="USD",
        receive_asset_issuer="GISSUER",
        cancel_offers=False,
        msg="Test prompt"
    )

    # Mock user with can_5000=0 (restricted)
    mock_user = MagicMock()
    mock_user.can_5000 = 0

    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
    swap_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    update = types.Update(
        update_id=6,
        message=types.Message(
            message_id=6,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="6000"  # Exceeds 5000 limit
        )
    )

    await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

    req = _last_request(mock_server, "sendMessage")
    assert req is not None
    # Should show limit warning
    assert "need_update_limits" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cq_swap_strict_receive(mock_server, swap_app_context, dp):
    """
    Test strict receive callback: should set state to swap_receive_sum.
    """
    dp.callback_query.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    # Set up state - need to be in swap_sum state
    ctx = dp.fsm.get_context(bot=swap_app_context.bot, chat_id=123, user_id=123)
    await ctx.set_state(StateSwapToken.swap_sum)
    await ctx.update_data(receive_asset_code="USD")

    update = types.Update(
        update_id=7,
        callback_query=types.CallbackQuery(
            id="cb7",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=7,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="SwapStrictReceive"
        )
    )

    await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

    req = _last_request(mock_server, "sendMessage")
    assert req is not None, "sendMessage should be called"

    # Verify state was set to swap_receive_sum
    state = await ctx.get_state()
    assert state == StateSwapToken.swap_receive_sum


@pytest.mark.asyncio
async def test_cmd_swap_receive_sum(mock_server, swap_app_context, dp):
    """
    Test sending swap receive sum: should calculate and show result.
    """
    dp.message.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    # Set up state
    ctx = dp.fsm.get_context(bot=swap_app_context.bot, chat_id=123, user_id=123)
    await ctx.set_state(StateSwapToken.swap_receive_sum)
    await ctx.update_data(
        send_asset_code="XLM",
        send_asset_issuer=None,
        receive_asset_code="USD",
        receive_asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA",
        cancel_offers=False
    )

    # Mock user repository via app_context DI
    mock_user = MagicMock()
    mock_user.can_5000 = 1

    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
    swap_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    # Mock swap use case via app_context DI
    mock_swap_use_case = AsyncMock()
    mock_swap_use_case.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR_SWAP_STRICT"))
    swap_app_context.use_case_factory.create_swap_assets.return_value = mock_swap_use_case

    update = types.Update(
        update_id=8,
        message=types.Message(
            message_id=8,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="10.0"
        )
    )

    # Patch stellar_check_send_sum - external Stellar API call (allowed per testing rules)
    with patch(
        "routers.swap.stellar_check_send_sum",
        new_callable=AsyncMock,
        return_value=("11.0", False),
    ):
        await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

        req = _last_request(mock_server, "sendMessage")
        assert req is not None, "sendMessage should be called"

        # Verify swap use case was called with strict_receive=True
        mock_swap_use_case.execute.assert_called_once()
        call_kwargs = mock_swap_use_case.execute.call_args.kwargs
        assert call_kwargs.get("strict_receive") is True


@pytest.mark.asyncio
async def test_cq_swap_cancel_offers_toggle(mock_server, swap_app_context, dp):
    """
    Test CancelOffers callback: should toggle cancel_offers flag.
    """
    dp.callback_query.middleware(MockDbMiddleware(swap_app_context))
    dp.include_router(swap_router)

    # Set up state
    ctx = dp.fsm.get_context(bot=swap_app_context.bot, chat_id=123, user_id=123)
    await ctx.set_state(StateSwapToken.swap_sum)
    await ctx.update_data(
        cancel_offers=False,
        msg="Test message",
        send_asset_code="XLM",
        receive_asset_code="USD"
    )

    update = types.Update(
        update_id=9,
        callback_query=types.CallbackQuery(
            id="cb9",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=9,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="CancelOffers"
        )
    )

    await dp.feed_update(bot=swap_app_context.bot, update=update, app_context=swap_app_context)

    # Verify state was updated
    data = await ctx.get_data()
    assert data.get("cancel_offers") is True

    req = _last_request(mock_server, "sendMessage")
    assert req is not None

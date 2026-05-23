from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.storage.base import StorageKey

from core.domain.entities import Wallet
from core.domain.value_objects import Asset, Balance
from core.models.anchor_asset import (
    AnchorAssetSupport,
    SepOperationSupport,
    SepProtocol,
    SepProtocolSupport,
)
from core.models.anchor_transaction import AnchorTransaction, AnchorTransactionProtocol
from keyboards.assets import AssetAction
from routers.assets import (
    _show_asset_requests_after_pin,
    _show_sep24_interactive_after_pin,
    router as assets_router,
)
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)


ISSUER = "GDPKQ2TSNJOFSEE7XSUXPWRP27H6GFGLWD7JCHNEYYWQVGFA543EVBVT"


@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if assets_router.parent_router:
        assets_router._parent_router = None


def make_support(code: str = "BTCLN", *, sep24: bool = False) -> AnchorAssetSupport:
    return AnchorAssetSupport(
        asset=Asset(code, ISSUER),
        anchor_domain="kbtrading.org",
        web_auth_endpoint="https://kbtrading.org/auth",
        sep6=SepProtocolSupport(
            protocol=SepProtocol.SEP6,
            transfer_server="https://kbtrading.org/sep6",
            deposit=SepOperationSupport(
                enabled=True,
                min_amount=1000.0,
                max_amount=500000.0,
                fee_percent=1.0,
            ),
            withdraw=SepOperationSupport(
                enabled=True,
                min_amount=10000.0,
                max_amount=500000.0,
                types={"lightning": {"fields": {"dest": {"description": "invoice"}}}},
            ),
            transactions_enabled=True,
        ),
        sep24=SepProtocolSupport(
            protocol=SepProtocol.SEP24,
            transfer_server="https://kbtrading.org/sep24",
        )
        if sep24
        else None,
    )


@pytest.mark.asyncio
async def test_assets_command_shows_only_sep_supported_trustlines(
    mock_telegram, router_app_context
):
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    get_balance = MagicMock()
    get_balance.execute = AsyncMock(
        return_value=[
            Balance("XLM", None, "native", "10"),
            Balance("BTCLN", ISSUER, "credit_alphanum12", "12000"),
            Balance("NOS", "GNOSEPISSUER", "credit_alphanum4", "1"),
        ]
    )
    router_app_context.use_case_factory.create_get_wallet_balance.return_value = (
        get_balance
    )
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_assets = AsyncMock(
        return_value=[make_support()]
    )

    await dp.feed_update(router_app_context.bot, create_message_update(123, "/assets"))

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "SEP assets" in req["data"]["text"]
    assert "BTCLN" in req["data"]["reply_markup"]
    assert "NOS" not in req["data"]["reply_markup"]
    router_app_context.anchor_discovery_service.discover_assets.assert_awaited_once_with(
        [Asset("BTCLN", ISSUER), Asset("NOS", "GNOSEPISSUER")]
    )


@pytest.mark.asyncio
async def test_assets_command_clears_last_message_and_sends_new_menu(
    mock_telegram, router_app_context
):
    user_id = 123
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    state_key = StorageKey(
        bot_id=router_app_context.bot.id,
        chat_id=user_id,
        user_id=user_id,
    )
    await dp.storage.set_data(
        state_key,
        {
            "last_message_id": 99,
            "anchor_request_asset": "STALE:GSTALE",
            "fsm_func": "stale",
        },
    )

    get_balance = MagicMock()
    get_balance.execute = AsyncMock(
        return_value=[Balance("BTCLN", ISSUER, "credit_alphanum12", "12000")]
    )
    router_app_context.use_case_factory.create_get_wallet_balance.return_value = (
        get_balance
    )
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_assets = AsyncMock(
        return_value=[make_support()]
    )

    await dp.feed_update(
        router_app_context.bot,
        create_message_update(user_id, "/assets", message_id=10),
    )

    assert not any(req["method"] == "deleteMessage" for req in mock_telegram)
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "SEP assets" in req["data"]["text"]
    state_data = await dp.storage.get_data(state_key)
    assert state_data["last_message_id"] != 99
    assert "anchor_request_asset" not in state_data
    assert "fsm_func" not in state_data
    assert state_data["anchor_assets"] == {"a0": make_support().asset.to_string()}


@pytest.mark.asyncio
async def test_asset_button_shows_conditions_and_action_buttons(
    mock_telegram, router_app_context
):
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=123, user_id=123)
    await dp.storage.set_data(
        state_key,
        {"anchor_assets": {"a0": make_support().asset.to_string()}},
    )
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=make_support()
    )

    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(
            123,
            AssetAction(action="view", key="a0").pack(),
        ),
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "BTCLN" in req["data"]["text"]
    assert "SEP-6" in req["data"]["text"]
    assert "Deposit" in req["data"]["text"]
    assert "Withdraw" in req["data"]["text"]
    assert "Requests" in req["data"]["reply_markup"]
    assert "Deposit" in req["data"]["reply_markup"]
    assert "Withdraw" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_asset_button_edits_current_menu_for_action_buttons(
    mock_telegram, router_app_context
):
    user_id = 123
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    state_key = StorageKey(
        bot_id=router_app_context.bot.id,
        chat_id=user_id,
        user_id=user_id,
    )
    await dp.storage.set_data(
        state_key,
        {
            "last_message_id": 99,
            "anchor_assets": {"a0": make_support().asset.to_string()},
        },
    )
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=make_support()
    )

    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(
            user_id,
            AssetAction(action="view", key="a0").pack(),
            message_id=99,
        ),
    )

    req = get_telegram_request(mock_telegram, "editMessageText")
    assert req["data"]["message_id"] == "99"
    assert "BTCLN" in req["data"]["text"]
    assert "Deposit" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_asset_requests_read_only_wallet_reports_webapp_not_enabled(
    mock_telegram, router_app_context
):
    user_id = 123
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    state_key = StorageKey(
        bot_id=router_app_context.bot.id,
        chat_id=user_id,
        user_id=user_id,
    )
    await dp.storage.set_data(
        state_key,
        {
            "last_message_id": 99,
            "anchor_assets": {"a0": make_support().asset.to_string()},
        },
    )
    wallet_repo = MagicMock()
    wallet_repo.get_default_wallet = AsyncMock(
        return_value=Wallet(
            id=1,
            user_id=user_id,
            public_key="GPUBLIC",
            is_default=True,
            is_free=False,
            use_pin=10,
        )
    )
    router_app_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )

    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(
            user_id,
            AssetAction(action="requests", key="a0").pack(),
            message_id=99,
        ),
    )

    req = get_telegram_request(mock_telegram, "editMessageText")
    assert "SEP-10 signing" in req["data"]["text"]
    assert "WebApp signing is not enabled" in req["data"]["text"]


@pytest.mark.asyncio
async def test_show_asset_requests_after_pin_sends_transactions(
    mock_telegram, router_app_context
):
    user_id = 123
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={
            "pin": "1234",
            "anchor_request_asset": make_support().asset.to_string(),
            "anchor_request_key": "a0",
        }
    )
    session = MagicMock()
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=make_support()
    )
    router_app_context.stellar_service.get_user_keypair = AsyncMock(
        return_value=MagicMock()
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.fetch_transactions = AsyncMock(
        return_value=[
            AnchorTransaction(
                protocol=AnchorTransactionProtocol.SEP24,
                id="tx-1",
                kind="deposit",
                status="completed",
                amount_in="100",
                updated_at="2026-05-23T10:00:00Z",
                more_info_url="https://anchor.test/tx-1",
            )
        ]
    )

    await _show_asset_requests_after_pin(
        session,
        user_id,
        state,
        app_context=router_app_context,
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "Requests" in req["data"]["text"]
    assert "SEP-24 / deposit / completed" in req["data"]["text"]
    assert "tx-1" in req["data"]["text"]
    assert "100" in req["data"]["text"]


@pytest.mark.asyncio
async def test_asset_deposit_read_only_wallet_reports_webapp_not_enabled(
    mock_telegram, router_app_context
):
    user_id = 123
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    state_key = StorageKey(
        bot_id=router_app_context.bot.id,
        chat_id=user_id,
        user_id=user_id,
    )
    await dp.storage.set_data(
        state_key,
        {
            "last_message_id": 99,
            "anchor_assets": {"a0": make_support().asset.to_string()},
        },
    )
    wallet_repo = MagicMock()
    wallet_repo.get_default_wallet = AsyncMock(
        return_value=Wallet(
            id=1,
            user_id=user_id,
            public_key="GPUBLIC",
            is_default=True,
            is_free=False,
            use_pin=10,
        )
    )
    router_app_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )

    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(
            user_id,
            AssetAction(action="deposit", key="a0").pack(),
            message_id=99,
        ),
    )

    req = get_telegram_request(mock_telegram, "editMessageText")
    assert "SEP-24 transfer requires SEP-10 signing" in req["data"]["text"]


@pytest.mark.asyncio
async def test_show_sep24_interactive_after_pin_sends_url_button(
    mock_telegram, router_app_context
):
    user_id = 123
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={
            "pin": "1234",
            "anchor_transfer_asset": make_support().asset.to_string(),
            "anchor_transfer_operation": "deposit",
        }
    )
    session = MagicMock()
    support = make_support(sep24=True)
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=support
    )
    router_app_context.stellar_service.get_user_keypair = AsyncMock(
        return_value=MagicMock()
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.start_sep24_interactive = AsyncMock(
        return_value="https://anchor.test/interactive/deposit/1"
    )

    await _show_sep24_interactive_after_pin(
        session,
        user_id,
        state,
        app_context=router_app_context,
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "SEP-24 deposit is ready" in req["data"]["text"]
    assert "https://anchor.test/interactive/deposit/1" in req["data"]["reply_markup"]

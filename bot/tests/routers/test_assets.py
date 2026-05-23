from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.storage.base import StorageKey

from core.domain.value_objects import Asset, Balance
from core.models.anchor_asset import (
    AnchorAssetSupport,
    SepOperationSupport,
    SepProtocol,
    SepProtocolSupport,
)
from keyboards.assets import AssetAction
from routers.assets import router as assets_router
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


def make_support(code: str = "BTCLN") -> AnchorAssetSupport:
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

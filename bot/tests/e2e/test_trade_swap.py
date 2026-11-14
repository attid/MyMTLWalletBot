"""Order creation and a real swap on the testnet."""

import pytest
from stellar_sdk import Account, Asset as SdkAsset, TransactionBuilder

from core.domain.value_objects import Asset
from routers.sign import router as sign_router
from routers.swap import router as swap_router
from routers.trade import router as trade_router
from shared.constants import TESTNET_NETWORK_PASSPHRASE
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)

pytestmark = [pytest.mark.external, pytest.mark.testnet]

PIN = "4321"


@pytest.fixture
async def dispatcher(e2e_app_context, sqlite_pool):
    dp = e2e_app_context.dispatcher
    async with sqlite_pool.get_session() as session:
        middleware = RouterTestMiddleware(e2e_app_context, session=session)
        dp.message.middleware(middleware)
        dp.callback_query.middleware(middleware)
        dp.include_router(trade_router)
        dp.include_router(swap_router)
        dp.include_router(sign_router)
        yield dp


@pytest.fixture
async def market(stellar_service, funded_account):
    """Issuer of E2EUSD that quotes 1 E2EUSD = 0.5 XLM on the order book."""
    issuer = await funded_account()
    asset = Asset("E2EUSD", issuer.public_key)
    await sdk_offer(
        stellar_service,
        keypair=issuer,
        selling=SdkAsset(asset.code, str(asset.issuer)),
        buying=SdkAsset.native(),
        amount="100",
        price="0.5",
    )
    return asset, issuer


async def sdk_offer(stellar_service, *, keypair, selling, buying, amount, price):
    details = await stellar_service.get_account_details(keypair.public_key)
    transaction = (
        TransactionBuilder(
            Account(keypair.public_key, int(details["sequence"])),
            TESTNET_NETWORK_PASSPHRASE,
            100,
        )
        .append_manage_sell_offer_op(
            selling=selling,
            buying=buying,
            amount=amount,
            price=price,
        )
        .set_timeout(60)
        .build()
    )
    transaction.sign(keypair.secret)
    await stellar_service.submit_transaction(transaction.to_xdr())


async def add_trustline(stellar_service, keypair, asset: Asset) -> None:
    xdr = await stellar_service.build_change_trust_transaction(
        source_account_id=keypair.public_key,
        asset_code=asset.code,
        asset_issuer=str(asset.issuer),
    )
    await stellar_service.submit_transaction(
        await stellar_service.sign_transaction(xdr, keypair.secret)
    )


async def confirm_and_sign(dispatcher, bot, user_id: int) -> None:
    await dispatcher.feed_update(bot, create_callback_update(user_id, "Yes_send_xdr"))
    await dispatcher.feed_update(bot, create_message_update(user_id, PIN))


@pytest.mark.asyncio
async def test_order_is_placed_on_the_testnet_book(
    mock_telegram,
    e2e_app_context,
    dispatcher,
    market,
    funded_account,
    seed_wallet,
    stellar_service,
):
    asset, _issuer = market
    trader = await funded_account()
    await add_trustline(stellar_service, trader, asset)
    user_id = 777004
    await seed_wallet(user_id, trader, pin=PIN)

    await dispatcher.feed_update(
        e2e_app_context.bot,
        create_message_update(user_id, f"/trade 2 XLM {asset.code} 3"),
    )
    await confirm_and_sign(dispatcher, e2e_app_context.bot, user_id)

    offers = await stellar_service.get_selling_offers(trader.public_key)
    mine = [
        offer
        for offer in offers
        if offer.get("selling", {}).get("asset_type") == "native"
        and offer.get("buying", {}).get("asset_code") == asset.code
    ]
    assert mine, f"offer was not created; horizon offers: {offers}"
    assert float(mine[0]["amount"]) == pytest.approx(2.0, abs=1e-6)


@pytest.mark.asyncio
async def test_swap_buys_the_asset_from_the_book(
    mock_telegram,
    e2e_app_context,
    dispatcher,
    market,
    funded_account,
    seed_wallet,
    stellar_service,
):
    asset, _issuer = market
    trader = await funded_account()
    await add_trustline(stellar_service, trader, asset)
    user_id = 777005
    await seed_wallet(user_id, trader, pin=PIN)

    before = await stellar_service.get_account_details(trader.public_key)
    before_asset = next(
        (
            float(balance["balance"])
            for balance in before["balances"]
            if balance.get("asset_code") == asset.code
        ),
        0.0,
    )

    await dispatcher.feed_update(
        e2e_app_context.bot,
        create_message_update(user_id, f"/swap 2 XLM {asset.code}"),
    )
    await confirm_and_sign(dispatcher, e2e_app_context.bot, user_id)

    after = await stellar_service.get_account_details(trader.public_key)
    after_asset = next(
        (
            float(balance["balance"])
            for balance in after["balances"]
            if balance.get("asset_code") == asset.code
        ),
        0.0,
    )

    assert after_asset > before_asset, "swap must deliver the bought asset"
    texts = [
        request["data"]["text"]
        for method in ("sendMessage", "editMessageText")
        for request in get_telegram_request(mock_telegram, method, last=False) or []
        if "text" in request["data"]
    ]
    assert not any("Ошибка" in text or "failed" in text.lower() for text in texts[-2:])

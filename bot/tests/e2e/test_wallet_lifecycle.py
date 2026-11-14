"""The scenario that silently rotted for months: create a free wallet."""

import pytest
from sqlalchemy import select

from db.models import MyMtlWalletBot
from routers.add_wallet import router as add_wallet_router
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    get_telegram_request,
)

pytestmark = [pytest.mark.external, pytest.mark.testnet]


@pytest.fixture
async def dispatcher(e2e_app_context, sqlite_pool):
    dp = e2e_app_context.dispatcher
    async with sqlite_pool.get_session() as session:
        dp.callback_query.middleware(
            RouterTestMiddleware(e2e_app_context, session=session)
        )
        dp.include_router(add_wallet_router)
        yield dp


@pytest.mark.asyncio
async def test_free_wallet_is_created_in_db_and_on_testnet(
    mock_telegram,
    e2e_app_context,
    dispatcher,
    sqlite_pool,
    stellar_service,
    issuer_asset,
):
    user_id = 777001

    await dispatcher.feed_update(
        e2e_app_context.bot,
        create_callback_update(user_id, "AddWalletNewKey"),
    )

    async with sqlite_pool.get_session() as session:
        rows = (
            (
                await session.execute(
                    select(MyMtlWalletBot).where(MyMtlWalletBot.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1, "free wallet must be written to the database"
    wallet = rows[0]
    assert wallet.public_key
    assert wallet.free_wallet == 1
    assert wallet.default_wallet == 1
    assert wallet.wallet_crypto_v2, "wallet crypto container must be stored"

    details = await stellar_service.get_account_details(wallet.public_key)
    assert details is not None, "wallet account must exist on the testnet"
    trustlines = {
        (balance.get("asset_code"), balance.get("asset_issuer"))
        for balance in details.get("balances", [])
    }
    assert (issuer_asset.code, issuer_asset.issuer) in trustlines

    sent = get_telegram_request(mock_telegram, "sendMessage", last=False)
    assert sent, "the bot must answer the callback"

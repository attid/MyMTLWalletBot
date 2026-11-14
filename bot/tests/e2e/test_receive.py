"""Receive screen: the address and its QR are rendered from the wallet."""

import pytest
from routers.receive import router as receive_router
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
        dp.include_router(receive_router)
        yield dp


@pytest.mark.asyncio
async def test_receive_shows_wallet_address_and_qr(
    mock_telegram, e2e_app_context, dispatcher, funded_account, seed_wallet
):
    keypair = await funded_account()
    user_id = 777006
    await seed_wallet(user_id, keypair, pin="4321")

    await dispatcher.feed_update(
        e2e_app_context.bot, create_callback_update(user_id, "Receive")
    )

    photo = get_telegram_request(mock_telegram, "sendPhoto")
    assert photo is not None, "the address screen must render a QR photo"
    assert keypair.public_key in photo["data"]["caption"]

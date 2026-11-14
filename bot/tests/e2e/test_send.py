"""Send XLM end to end: the free-wallet guard and a real testnet payment."""

import pytest
from routers.send import SendAssetCallbackData
from routers.send import router as send_router
from routers.sign import router as sign_router
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
        dp.include_router(send_router)
        dp.include_router(sign_router)
        yield dp


async def drive_send(dp, bot, *, user_id: int, destination: str, amount: str) -> None:
    """Walk the /send wizard up to the confirmation screen."""
    await dp.feed_update(bot, create_message_update(user_id, "/send"))
    await dp.feed_update(bot, create_message_update(user_id, destination))
    await dp.feed_update(
        bot,
        create_callback_update(user_id, SendAssetCallbackData(answer="XLM").pack()),
    )
    await dp.feed_update(bot, create_message_update(user_id, amount))
    await dp.feed_update(bot, create_callback_update(user_id, "Yes_send_xdr"))


@pytest.mark.asyncio
async def test_imported_wallet_sends_xlm_on_testnet(
    mock_telegram,
    e2e_app_context,
    dispatcher,
    funded_account,
    seed_wallet,
    native_balance,
):
    sender_keypair = await funded_account()
    recipient_keypair = await funded_account()
    user_id = 777002
    await seed_wallet(user_id, sender_keypair, pin=PIN)

    before = await native_balance(recipient_keypair.public_key)

    await drive_send(
        dispatcher,
        e2e_app_context.bot,
        user_id=user_id,
        destination=recipient_keypair.public_key,
        amount="2",
    )
    await dispatcher.feed_update(
        e2e_app_context.bot, create_message_update(user_id, PIN)
    )

    after = await native_balance(recipient_keypair.public_key)
    assert round(after - before, 7) == pytest.approx(2.0, abs=1e-6)


@pytest.mark.asyncio
async def test_free_wallet_cannot_send_native_xlm(
    mock_telegram,
    e2e_app_context,
    dispatcher,
    funded_account,
    seed_wallet,
    native_balance,
):
    sender_keypair = await funded_account()
    recipient_keypair = await funded_account()
    user_id = 777003
    await seed_wallet(user_id, sender_keypair, pin=PIN, is_free=True)

    before = await native_balance(recipient_keypair.public_key)

    await drive_send(
        dispatcher,
        e2e_app_context.bot,
        user_id=user_id,
        destination=recipient_keypair.public_key,
        amount="2",
    )
    await dispatcher.feed_update(
        e2e_app_context.bot, create_message_update(user_id, PIN)
    )

    after = await native_balance(recipient_keypair.public_key)
    assert after == before, "free wallet must not move XLM"

    texts = [
        request["data"]["text"]
        for method in ("sendMessage", "editMessageText")
        for request in get_telegram_request(mock_telegram, method, last=False) or []
        if "text" in request["data"]
    ]
    assert any("free-wallet policy" in text for text in texts), texts[-3:]

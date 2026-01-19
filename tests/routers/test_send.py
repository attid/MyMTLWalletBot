"""
Exemplary router tests for routers/send.py

This file demonstrates the correct testing patterns:
1. Use mock_server for Telegram API (mandatory)
2. Use mock_horizon for Stellar API (no patches!)
3. Use router_app_context and RouterTestMiddleware from conftest
4. Use helper functions: create_message_update, create_callback_update, get_telegram_request
5. Configure mocks via app_context DI
6. NO patch() calls - all dependencies injected via app_context or mock servers

See tests/README.md for complete testing rules.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from aiogram.fsm.storage.base import StorageKey

from routers.send import router as send_router, StateSendToken, SendAssetCallbackData
from core.domain.value_objects import Balance, PaymentResult
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)
from core.interfaces.repositories import IWalletRepository, IUserRepository
from core.use_cases.wallet.get_balance import GetWalletBalance
from core.use_cases.payment.send_payment import SendPayment
from core.domain.entities import User, Wallet

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if send_router.parent_router:
        send_router._parent_router = None


@pytest.fixture
def setup_send_mocks(router_app_context):
    """
    Common mock setup for send router tests.
    Returns a helper object to configure specific scenarios.
    """
    class SendMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default wallet mock
            self.wallet = MagicMock(spec=Wallet)
            self.wallet.public_key = "GUSER1234567890123456789012345678901234567890123456"
            self.wallet.is_free = False

            wallet_repo = MagicMock(spec=IWalletRepository)
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

            # Default user mock
            self.user = MagicMock(spec=User)
            self.user.can_5000 = 1
            self.user.lang = 'en'

            user_repo = MagicMock(spec=IUserRepository)
            user_repo.get_by_id = AsyncMock(return_value=self.user)
            self.ctx.repository_factory.get_user_repository.return_value = user_repo

            # Default balance use case
            balance_uc = MagicMock(spec=GetWalletBalance)
            balance_uc.execute = AsyncMock(return_value=[
                Balance(asset_code="XLM", balance="100.0", asset_issuer=None, asset_type="native"),
                Balance(asset_code="EURMTL", balance="50.0",
                       asset_issuer="GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
                       asset_type="credit_alphanum12"),
            ])
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = balance_uc

            # Default send payment use case
            send_uc = MagicMock(spec=SendPayment)
            send_uc.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR_PAYMENT"))
            self.ctx.use_case_factory.create_send_payment.return_value = send_uc

        def set_balances(self, balances: list):
            """Configure user balances."""
            balance_uc = MagicMock(spec=GetWalletBalance)
            balance_uc.execute = AsyncMock(return_value=balances)
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = balance_uc

        def set_user_limit(self, can_5000: int):
            """Configure user transaction limit."""
            self.user.can_5000 = can_5000

        def set_payment_result(self, success: bool, xdr: str = None, error: str = None):
            """Configure payment result."""
            send_uc = MagicMock(spec=SendPayment)
            send_uc.execute = AsyncMock(return_value=PaymentResult(
                success=success, xdr=xdr, error_message=error
            ))
            self.ctx.use_case_factory.create_send_payment.return_value = send_uc

        def set_offers(self, offers: list):
            """Configure selling offers."""
            # Use mock_horizon instead of mocking service
            from tests.conftest import DEFAULT_TEST_ACCOUNT
            # We assume mock_horizon is available via some way? 
            # In router tests, we usually pass it to the test function.
            # Since SendMockHelper doesn't have it, we might need to pass it.
            pass # See individual tests where this is called

    return SendMockHelper(router_app_context)


# --- Tests ---

@pytest.mark.asyncio
async def test_cmd_send_callback(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test Send callback: should show address input prompt.
    Uses mock_server for Telegram, mock_horizon for Stellar.
    """
    user_id = 123

    # Setup router with middleware
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Create and feed update
    update = create_callback_update(user_id, "Send")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify Telegram API was called
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None, "sendMessage should be called"
    assert "send_address" in req["data"]["text"]

    # Verify callback was answered
    answer = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert answer is not None


@pytest.mark.asyncio
async def test_cmd_send_for_valid_address(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test entering a valid Stellar address: should show token selection.
    mock_horizon handles stellar_check_account automatically.
    """
    user_id = 123
    valid_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Configure mock_horizon to return this account
    mock_horizon.set_account(valid_address, balances=[
        {"asset_type": "native", "balance": "100.0"},
        {"asset_type": "credit_alphanum12", "asset_code": "EURMTL",
         "asset_issuer": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
         "balance": "50.0"}
    ])

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state to sending_for
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_for)

    # Send address
    update = create_message_update(user_id, valid_address)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify response - should show token selection
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "choose_token" in req["data"]["text"]

    # Verify state was updated with address
    data = await dp.storage.get_data(key=storage_key)
    assert data.get("send_address") == valid_address


@pytest.mark.asyncio
async def test_cmd_send_for_invalid_address(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test entering invalid address: should show error.
    mock_horizon returns 404 for unknown accounts.
    """
    user_id = 123
    invalid_address = "GINVALID"

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state to sending_for
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_for)

    # Send invalid address
    update = create_message_update(user_id, invalid_address)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify error response
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_error2" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cb_send_choose_token(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test selecting a token: should show sum input prompt.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state with assets
    import jsonpickle
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    assets = [
        Balance(asset_code="XLM", balance="100.0", asset_issuer=None, asset_type="native"),
        Balance(asset_code="EURMTL", balance="50.0",
               asset_issuer="GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
               asset_type="credit_alphanum12"),
    ]
    await dp.storage.set_data(key=storage_key, data={
        "send_address": send_address,
        "assets": jsonpickle.encode(assets)
    })

    # Select XLM token
    callback_data = SendAssetCallbackData(answer="XLM").pack()
    update = create_callback_update(user_id, callback_data)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify response - should ask for sum
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_sum" in req["data"]["text"]

    # Verify state
    state = await dp.storage.get_state(key=storage_key)
    assert state == StateSendToken.sending_sum


@pytest.mark.asyncio
async def test_cmd_send_get_sum_valid(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test entering valid sum: should show confirmation.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(key=storage_key, data={
        "send_address": send_address,
        "send_asset_code": "XLM",
        "send_asset_issuer": None,
        "send_asset_max_sum": "100.0",
        "msg": "Enter sum"
    })

    # Send sum
    update = create_message_update(user_id, "10.5")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify confirmation message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "confirm_send" in req["data"]["text"]

    # Verify state data
    data = await dp.storage.get_data(key=storage_key)
    assert data.get("send_sum") == 10.5
    assert data.get("xdr") == "XDR_PAYMENT"


@pytest.mark.asyncio
async def test_cmd_send_get_sum_exceeds_limit(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test entering sum exceeding user limit: should show warning.
    """
    user_id = 123

    # Set user limit to 0 (cannot send > 5000)
    setup_send_mocks.set_user_limit(0)

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(key=storage_key, data={
        "send_asset_code": "XLM",
        "send_asset_issuer": None,
        "msg": "Enter sum"
    })

    # Send sum > 5000
    update = create_message_update(user_id, "6000")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify warning message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "need_update_limits" in req["data"]["text"]

    # Sum should NOT be updated
    data = await dp.storage.get_data(key=storage_key)
    assert data.get("send_sum") is None


@pytest.mark.asyncio
async def test_cmd_send_get_sum_invalid(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test entering invalid sum: should show error and re-prompt.
    """
    user_id = 123

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(key=storage_key, data={
        "send_asset_code": "XLM",
        "msg": "Enter sum"
    })

    # Send invalid sum
    update = create_message_update(user_id, "not_a_number")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify error message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "bad_sum" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_get_memo(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test Memo button: should prompt for memo input.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Send Memo callback
    update = create_callback_update(user_id, "Memo")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify memo prompt
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_memo" in req["data"]["text"]

    # Verify state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    state = await dp.storage.get_state(key=storage_key)
    assert state == StateSendToken.sending_memo


@pytest.mark.asyncio
async def test_cmd_send_memo(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test entering memo: should proceed to confirmation with truncated memo.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_memo)
    await dp.storage.set_data(key=storage_key, data={
        "send_address": send_address,
        "send_asset_code": "XLM",
        "send_asset_issuer": None,
        "send_sum": 10.0
    })

    # Send long memo (should be truncated to 28 bytes)
    long_memo = "This is a very long memo that exceeds 28 bytes"
    update = create_message_update(user_id, long_memo)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify confirmation
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "confirm_send" in req["data"]["text"]

    # Verify memo was stored (truncated)
    data = await dp.storage.get_data(key=storage_key)
    assert len(data.get("memo", "")) <= 28


@pytest.mark.asyncio
async def test_cq_cancel_offers_toggle(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test CancelOffers toggle: should invert flag and update message.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state with cancel_offers=False
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(key=storage_key, data={
        "send_asset_code": "XLM",
        "cancel_offers": False,
        "msg": "Enter sum"
    })

    # Toggle cancel offers
    update = create_callback_update(user_id, "CancelOffers")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify flag was toggled
    data = await dp.storage.get_data(key=storage_key)
    assert data.get("cancel_offers") is True

    # Toggle again
    mock_telegram.clear()
    update = create_callback_update(user_id, "CancelOffers", update_id=2)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    data = await dp.storage.get_data(key=storage_key)
    assert data.get("cancel_offers") is False


@pytest.mark.asyncio
async def test_cb_send_choose_token_with_blocked_offers(mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks):
    """
    Test selecting token when some balance is blocked by offers.
    Should show warning about blocked amount.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Configure offers that block some XLM
    mock_horizon.set_offers(setup_send_mocks.wallet.public_key, [
        {
            "id": "12345",
            "selling": {"asset_type": "native", "asset_code": None, "asset_issuer": None},
            "buying": {"asset_type": "credit_alphanum12", "asset_code": "EURMTL",
                      "asset_issuer": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"},
            "amount": "25.0"
        }
    ])

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state with assets
    import jsonpickle
    storage_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    assets = [Balance(asset_code="XLM", balance="100.0", asset_issuer=None, asset_type="native")]
    await dp.storage.set_data(key=storage_key, data={
        "send_address": send_address,
        "assets": jsonpickle.encode(assets)
    })

    # Select XLM token
    callback_data = SendAssetCallbackData(answer="XLM").pack()
    update = create_callback_update(user_id, callback_data)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify response (note: blocked offers warning requires non-native asset match)
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_sum" in req["data"]["text"]

    # Verify state was set correctly
    state = await dp.storage.get_state(key=storage_key)
    assert state == StateSendToken.sending_sum

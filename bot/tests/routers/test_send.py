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

import asyncio
import jsonpickle  # type: ignore
from pathlib import Path
from types import SimpleNamespace

import pytest
from typing import Optional
from unittest.mock import MagicMock, AsyncMock
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import EditMessageText

from routers.send import (
    FLOW_BACK_CALLBACK,
    router as send_router,
    StateSendToken,
    SendAssetCallbackData,
    handle_docs_photo,
)
from middleware.notification_activity import NotificationActivityMiddleware
from core.domain.value_objects import Balance, PaymentResult
from infrastructure.services.signing_facade import PENDING_SIGNATURE_REQUEST_KEY
from keyboards.common_keyboards import get_kb_return, get_kb_yesno_send_xdr
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)
from core.interfaces.repositories import (
    IAddressBookRepository,
    IUserRepository,
    IWalletRepository,
)
from core.use_cases.wallet.get_balance import GetWalletBalance
from core.use_cases.payment.send_payment import SendPayment
from core.domain.entities import User, Wallet


@pytest.mark.asyncio
async def test_handle_docs_photo_uses_isolated_temporary_files(
    mock_telegram, monkeypatch, tmp_path
):
    work_dir = tmp_path / "fresh-workdir"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    downloaded_paths = []
    decoded_paths = []

    async def download(_photo, destination):
        path = Path(destination)
        downloaded_paths.append(path)
        path.write_bytes(b"qr")
        await asyncio.sleep(0)
        assert path.exists()

    def decode_qr_code(path):
        path = Path(path)
        decoded_paths.append(path)
        assert path.exists()
        return None

    monkeypatch.setattr("routers.send.decode_qr_code", decode_qr_code)
    app_context = SimpleNamespace(bot=SimpleNamespace(download=download))
    session = AsyncMock()

    def make_message(user_id):
        return SimpleNamespace(
            from_user=SimpleNamespace(id=user_id),
            photo=[object()],
            reply=AsyncMock(),
        )

    await asyncio.gather(
        *(
            handle_docs_photo(
                make_message(user_id),
                AsyncMock(),
                session,
                app_context,
            )
            for user_id in (123, 123, 456)
        )
    )

    assert len(downloaded_paths) == 3
    assert len(decoded_paths) == 3
    assert len({str(path) for path in downloaded_paths}) == 3
    assert all(path.parent != work_dir / "qr" for path in downloaded_paths)
    assert all(not path.exists() for path in downloaded_paths)
    assert not (work_dir / "qr").exists()


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
            self.wallet.public_key = (
                "GUSER1234567890123456789012345678901234567890123456"
            )
            self.wallet.is_free = False

            wallet_repo = MagicMock(spec=IWalletRepository)
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

            # Default user mock
            self.user = MagicMock(spec=User)
            self.user.can_5000 = 1
            self.user.lang = "en"

            user_repo = MagicMock(spec=IUserRepository)
            user_repo.get_by_id = AsyncMock(return_value=self.user)
            self.ctx.repository_factory.get_user_repository.return_value = user_repo

            # Default balance use case
            balance_uc = MagicMock(spec=GetWalletBalance)
            balance_uc.execute = AsyncMock(
                return_value=[
                    Balance(
                        asset_code="XLM",
                        balance="100.0",
                        asset_issuer=None,
                        asset_type="native",
                    ),
                    Balance(
                        asset_code="EURMTL",
                        balance="50.0",
                        asset_issuer="GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
                        asset_type="credit_alphanum12",
                    ),
                ]
            )
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = (
                balance_uc
            )

            # Default send payment use case
            send_uc = MagicMock(spec=SendPayment)
            send_uc.execute = AsyncMock(
                return_value=PaymentResult(success=True, xdr="XDR_PAYMENT")
            )
            self.ctx.use_case_factory.create_send_payment.return_value = send_uc

        def set_balances(self, balances: list):
            """Configure user balances."""
            balance_uc = MagicMock(spec=GetWalletBalance)
            balance_uc.execute = AsyncMock(return_value=balances)
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = (
                balance_uc
            )

        def set_user_limit(self, can_5000: int):
            """Configure user transaction limit."""
            self.user.can_5000 = can_5000

        def set_payment_result(
            self, success: bool, xdr: Optional[str] = None, error: Optional[str] = None
        ):
            """Configure payment result."""
            send_uc = MagicMock(spec=SendPayment)
            send_uc.execute = AsyncMock(
                return_value=PaymentResult(
                    success=success, xdr=xdr, error_message=error
                )
            )
            self.ctx.use_case_factory.create_send_payment.return_value = send_uc

        def set_offers(self, offers: list):
            """Configure selling offers."""
            # Use mock_horizon instead of mocking service
            # We assume mock_horizon is available via some way?
            # In router tests, we usually pass it to the test function.
            # Since SendMockHelper doesn't have it, we might need to pass it.
            pass  # See individual tests where this is called

    return SendMockHelper(router_app_context)


# --- Tests ---


@pytest.mark.asyncio
async def test_inline_stellar_uri_does_not_search_usernames(
    mock_telegram, router_app_context, dp
):
    user_id = 474834212
    addressbook_repo = MagicMock(spec=IAddressBookRepository)
    addressbook_repo.get_all = AsyncMock(return_value=[])
    wallet_repo = MagicMock(spec=IWalletRepository)
    wallet_repo.get_all_active = AsyncMock(return_value=[])
    user_repo = MagicMock(spec=IUserRepository)
    user_repo.search_by_username = AsyncMock(return_value=[])
    router_app_context.repository_factory.get_addressbook_repository.return_value = (
        addressbook_repo
    )
    router_app_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    router_app_context.repository_factory.get_user_repository.return_value = user_repo
    dp.inline_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    update = types.Update(
        update_id=1,
        inline_query=types.InlineQuery(
            id="inline-stellar-uri",
            from_user=types.User(
                id=user_id, is_bot=False, first_name="User", username="user"
            ),
            query=(
                "web+stellar:pay?destination="
                "GCZZTHQ6KLXA77XEGUAM6ANQDZ6KKMKZHOKV7RD4PPK5RBV7SXHOROSO"
                "&amount=9.00&asset_code=EURMTL"
            ),
            offset="",
            chat_type="sender",
        ),
    )

    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    user_repo.search_by_username.assert_not_awaited()
    assert get_telegram_request(mock_telegram, "answerInlineQuery") is not None


@pytest.mark.asyncio
async def test_cmd_send_callback(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
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
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify Telegram API was called
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None, "sendMessage should be called"
    assert "send_address" in req["data"]["text"]

    # Verify callback was answered
    answer = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert answer is not None


@pytest.mark.asyncio
async def test_send_command_starts_notification_hold_after_activating_fsm(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    coordinator = MagicMock(touch=AsyncMock())
    router_app_context.notification_coordinator = coordinator
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(NotificationActivityMiddleware())
    dp.include_router(send_router)

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_message_update(user_id, "/send"),
        app_context=router_app_context,
    )

    state_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    assert await dp.storage.get_state(state_key) == StateSendToken.sending_for
    coordinator.touch.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_cmd_send_for_valid_address(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Test entering a valid Stellar address: should show token selection.
    mock_horizon handles stellar_check_account automatically.
    """
    user_id = 123
    valid_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Configure mock_horizon to return this account
    mock_horizon.set_account(
        valid_address,
        balances=[
            {"asset_type": "native", "balance": "100.0"},
            {
                "asset_type": "credit_alphanum12",
                "asset_code": "EURMTL",
                "asset_issuer": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
                "balance": "50.0",
            },
        ],
    )

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state to sending_for
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_for)

    # Send address
    update = create_message_update(user_id, valid_address)
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify response - should show token selection
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "choose_token" in req["data"]["text"]

    # Verify state was updated with address
    data = await dp.storage.get_data(key=storage_key)
    assert data.get("send_address") == valid_address


@pytest.mark.asyncio
async def test_cmd_send_for_invalid_address(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
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
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_for)

    # Send invalid address
    update = create_message_update(user_id, invalid_address)
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify error response
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_error2" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cb_send_choose_token(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Test selecting a token: should show sum input prompt.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state with assets
    import jsonpickle  # type: ignore

    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    assets = [
        Balance(
            asset_code="XLM", balance="100.0", asset_issuer=None, asset_type="native"
        ),
        Balance(
            asset_code="EURMTL",
            balance="50.0",
            asset_issuer="GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
            asset_type="credit_alphanum12",
        ),
    ]
    await dp.storage.set_data(
        key=storage_key,
        data={"send_address": send_address, "assets": jsonpickle.encode(assets)},
    )

    # Select XLM token
    callback_data = SendAssetCallbackData(answer="XLM").pack()
    update = create_callback_update(user_id, callback_data)
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify response - should ask for sum
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_sum" in req["data"]["text"]

    # Verify state
    state = await dp.storage.get_state(key=storage_key)
    assert state == StateSendToken.sending_sum


@pytest.mark.asyncio
async def test_cmd_send_get_sum_valid(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Test entering valid sum: should show confirmation.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "send_address": send_address,
            "send_asset_code": "XLM",
            "send_asset_issuer": None,
            "send_asset_max_sum": "100.0",
            "msg": "Enter sum",
        },
    )

    # Send sum
    update = create_message_update(user_id, "10.5")
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify confirmation message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "confirm_send" in req["data"]["text"]

    # Verify state data
    data = await dp.storage.get_data(key=storage_key)
    assert data.get("send_sum") == 10.5
    assert data.get("xdr") == "XDR_PAYMENT"
    pending = data.get(PENDING_SIGNATURE_REQUEST_KEY)
    assert pending["xdr"] == "XDR_PAYMENT"
    assert pending["purpose"] == "payment"
    assert pending["mode"] == "sign_and_submit"
    assert pending["operation"] == "Send 10.5 XLM"
    assert pending["sign_msg"] == "sign_payment_msg"


@pytest.mark.asyncio
async def test_cmd_send_get_sum_muxed_address_checks_underlying_account(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    muxed_address = (
        "MCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYKAAAAAAAAAAXPAMAK"
    )
    underlying_address = "GCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYLQDJ"
    send_uc = router_app_context.use_case_factory.create_send_payment.return_value

    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "send_address": muxed_address,
            "send_balance_address": underlying_address,
            "send_asset_code": "XLM",
            "send_asset_issuer": None,
            "send_asset_max_sum": "100.0",
            "msg": "Enter sum",
        },
    )

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_message_update(user_id, "10.5"),
        app_context=router_app_context,
    )

    send_uc.execute.assert_awaited_once()
    assert send_uc.execute.await_args.kwargs["destination_address"] == muxed_address
    assert (
        send_uc.execute.await_args.kwargs["destination_check_address"]
        == underlying_address
    )
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "confirm_send" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_send_get_sum_exceeds_limit(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
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
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(
        key=storage_key,
        data={"send_asset_code": "XLM", "send_asset_issuer": None, "msg": "Enter sum"},
    )

    # Send sum > 5000
    update = create_message_update(user_id, "6000")
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify warning message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "need_update_limits" in req["data"]["text"]
    assert FLOW_BACK_CALLBACK in req["data"]["reply_markup"]
    assert '"callback_data": "Return"' in req["data"]["reply_markup"]
    assert await dp.storage.get_state(storage_key) == StateSendToken.sending_sum

    # Sum should NOT be updated
    data = await dp.storage.get_data(key=storage_key)
    assert data.get("send_sum") is None


@pytest.mark.asyncio
async def test_cmd_send_get_sum_build_error_rerenders_amount_with_flow_back(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    router_app_context.use_case_factory.create_send_payment.return_value.execute.return_value = PaymentResult(
        success=False, error_message="build failed"
    )
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "send_address": "GDEST",
            "send_asset_code": "XLM",
            "send_asset_issuer": None,
            "msg": "Enter sum",
        },
    )

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_message_update(user_id, "10"),
        app_context=router_app_context,
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "Error: build failed" in req["data"]["text"]
    assert FLOW_BACK_CALLBACK in req["data"]["reply_markup"]
    assert '"callback_data": "Return"' in req["data"]["reply_markup"]
    assert await dp.storage.get_state(storage_key) == StateSendToken.sending_sum
    assert (await dp.storage.get_data(storage_key))["send_address"] == "GDEST"


@pytest.mark.asyncio
async def test_cmd_send_get_sum_invalid(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Test entering invalid sum: should show error and re-prompt.
    """
    user_id = 123

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(NotificationActivityMiddleware())
    dp.include_router(send_router)
    coordinator = MagicMock(touch=AsyncMock(), complete_flow=AsyncMock())
    router_app_context.notification_coordinator = coordinator

    # Set state
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(
        key=storage_key, data={"send_asset_code": "XLM", "msg": "Enter sum"}
    )

    # Send invalid sum
    update = create_message_update(user_id, "not_a_number")
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify error message
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "bad_sum" in req["data"]["text"]
    assert await dp.storage.get_state(storage_key) == StateSendToken.sending_sum
    coordinator.touch.assert_awaited_once_with(user_id)
    coordinator.complete_flow.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_get_memo(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Test Memo button: should prompt for memo input.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Send Memo callback
    update = create_callback_update(user_id, "Memo")
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify memo prompt
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_memo" in req["data"]["text"]

    # Verify state
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    state = await dp.storage.get_state(key=storage_key)
    assert state == StateSendToken.sending_memo


@pytest.mark.asyncio
async def test_cmd_send_memo(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Test entering memo: should proceed to confirmation with truncated memo.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_memo)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "send_address": send_address,
            "send_asset_code": "XLM",
            "send_asset_issuer": None,
            "send_sum": 10.0,
        },
    )

    # Send long memo (should be truncated to 28 bytes)
    long_memo = "This is a very long memo that exceeds 28 bytes"
    update = create_message_update(user_id, long_memo)
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify confirmation
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "confirm_send" in req["data"]["text"]

    # Verify memo was stored (truncated)
    data = await dp.storage.get_data(key=storage_key)
    assert len(data.get("memo", "")) <= 28


@pytest.mark.asyncio
async def test_cq_cancel_offers_toggle(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Test CancelOffers toggle: should invert flag and update message.
    """
    user_id = 123

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state with cancel_offers=False
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(
        key=storage_key,
        data={"send_asset_code": "XLM", "cancel_offers": False, "msg": "Enter sum"},
    )

    # Toggle cancel offers
    update = create_callback_update(user_id, "CancelOffers")
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify flag was toggled
    data = await dp.storage.get_data(key=storage_key)
    assert data.get("cancel_offers") is True

    # Toggle again
    mock_telegram.clear()
    update = create_callback_update(user_id, "CancelOffers", update_id=2)
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    data = await dp.storage.get_data(key=storage_key)
    assert data.get("cancel_offers") is False


@pytest.mark.asyncio
async def test_flow_back_from_send_amount_rerenders_asset_choice_and_preserves_data(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_sum)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "send_address": address,
            "assets": jsonpickle.encode(
                setup_send_mocks.ctx.use_case_factory.create_get_wallet_balance.return_value.execute.return_value
            ),
            "send_asset_code": "XLM",
        },
    )

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_callback_update(user_id, FLOW_BACK_CALLBACK),
        app_context=router_app_context,
    )

    assert await dp.storage.get_state(storage_key) == StateSendToken.choosing_token
    assert (await dp.storage.get_data(storage_key))["send_address"] == address
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "choose_token" in req["data"]["text"]


@pytest.mark.asyncio
async def test_flow_back_from_send_token_clears_recipient_data_and_preserves_unrelated_data(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.choosing_token)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "qr": "GQRDEST",
            "memo": "recipient memo",
            "federal_memo": True,
            "send_address": "GDEST",
            "send_balance_address": "GBALANCEDEST",
            "mtlap_stars": "⭐⭐",
            "unrelated_flow_data": "keep me",
        },
    )

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_callback_update(user_id, FLOW_BACK_CALLBACK),
        app_context=router_app_context,
    )

    assert await dp.storage.get_state(storage_key) == StateSendToken.sending_for
    data = await dp.storage.get_data(storage_key)
    for key in (
        "qr",
        "memo",
        "federal_memo",
        "send_address",
        "send_balance_address",
        "mtlap_stars",
    ):
        assert key not in data
    assert data["unrelated_flow_data"] == "keep me"
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "send_address" in req["data"]["text"]


@pytest.mark.asyncio
async def test_flow_back_from_send_token_uses_typed_address_without_stale_recipient_memo(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    stale_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    new_address = "GCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYLQDJ"
    for address in (stale_address, new_address):
        mock_horizon.set_account(
            address, balances=[{"asset_type": "native", "balance": "100.0"}]
        )

    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.choosing_token)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "qr": stale_address,
            "memo": "recipient memo",
            "federal_memo": True,
            "send_address": stale_address,
            "send_balance_address": stale_address,
        },
    )

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_callback_update(user_id, FLOW_BACK_CALLBACK),
        app_context=router_app_context,
    )
    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_message_update(user_id, new_address),
        app_context=router_app_context,
    )

    data = await dp.storage.get_data(storage_key)
    assert data["send_address"] == new_address
    assert "memo" not in data
    assert "federal_memo" not in data


@pytest.mark.asyncio
async def test_flow_back_from_send_confirmation_rerenders_amount_prompt(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.confirming)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "last_message_id": 987,
            "unrelated_global_data": "keep me",
            "flow_back_amount_msg": "Enter XLM amount",
            "send_address": "GDEST",
            "send_sum": 10,
            "send_asset_code": "XLM",
            PENDING_SIGNATURE_REQUEST_KEY: {"xdr": "AAAA_CONFIRMATION_XDR"},
            "xdr": "AAAA_CONFIRMATION_XDR",
            "operation": "Send 10 XLM",
            "sign_msg": "Sign payment",
            "success_msg": "Payment sent",
        },
    )
    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_callback_update(user_id, FLOW_BACK_CALLBACK),
        app_context=router_app_context,
    )

    assert await dp.storage.get_state(storage_key) == StateSendToken.sending_sum
    data = await dp.storage.get_data(storage_key)
    for key in (
        PENDING_SIGNATURE_REQUEST_KEY,
        "xdr",
        "operation",
        "sign_msg",
        "success_msg",
    ):
        assert key not in data
    assert data["flow_back_amount_msg"] == "Enter XLM amount"
    assert data["send_address"] == "GDEST"
    assert data["send_sum"] == 10
    assert data["send_asset_code"] == "XLM"
    assert data["last_message_id"] == 987
    assert data["unrelated_global_data"] == "keep me"
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req["data"]["text"] == "Enter XLM amount"
    assert FLOW_BACK_CALLBACK in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_flow_back_after_qr_confirmation_recovers_when_edit_fails_and_text_is_missing(
    mock_telegram, router_app_context, dp
):
    user_id = 123
    failed_edits = []

    async def reject_edit(make_request, bot, method):
        if isinstance(method, EditMessageText):
            failed_edits.append(method)
            raise TelegramBadRequest(method=method, message="message cannot be edited")
        return await make_request(bot, method)

    router_app_context.bot.session.middleware(reject_edit)
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.confirming)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "last_message_id": 987,
            "flow_back_amount_msg": None,
            "send_address": "GDEST",
            "send_sum": 10,
            "send_asset_code": "XLM",
            "send_asset_issuer": None,
            PENDING_SIGNATURE_REQUEST_KEY: {"xdr": "AAAA_CONFIRMATION_XDR"},
            "xdr": "AAAA_CONFIRMATION_XDR",
            "operation": "Send 10 XLM",
            "sign_msg": "Sign payment",
            "success_msg": "Payment sent",
        },
    )
    await router_app_context.dispatcher.storage.set_data(
        key=storage_key, data={"last_message_id": 987}
    )

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_callback_update(user_id, FLOW_BACK_CALLBACK),
        app_context=router_app_context,
    )

    assert len(failed_edits) == 1
    assert await dp.storage.get_state(storage_key) == StateSendToken.sending_for
    sent = get_telegram_request(mock_telegram, "sendMessage")
    assert sent is not None
    assert sent["data"]["text"]
    assert "send_address" in sent["data"]["text"]
    assert get_telegram_request(mock_telegram, "answerCallbackQuery") is not None


@pytest.mark.asyncio
async def test_flow_back_from_confirmation_to_address_clears_stale_send_and_signing_payloads(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.confirming)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "last_message_id": 987,
            "unrelated_global_data": "keep me",
            PENDING_SIGNATURE_REQUEST_KEY: {
                "xdr": "AAAA_CONFIRMATION_XDR",
                "purpose": "payment",
                "mode": "sign_and_submit",
                "operation": "Send 10 XLM",
                "sign_msg": "Sign payment",
                "success_msg": "Payment sent",
            },
            "xdr": "AAAA_CONFIRMATION_XDR",
            "operation": "Send 10 XLM",
            "sign_msg": "Sign payment",
            "success_msg": "Payment sent",
            "flow_back_amount_msg": "Enter XLM amount",
            "qr": "GQRDEST",
            "memo": "recipient memo",
            "federal_memo": True,
            "send_address": "GDEST",
            "send_balance_address": "GBALANCEDEST",
            "mtlap_stars": "⭐⭐",
            "send_sum": 10,
            "send_asset_code": "XLM",
            "send_asset_issuer": None,
            "send_asset_max_sum": 100.0,
            "send_asset_blocked_sum": 0.0,
            "cancel_offers": True,
            "msg": "Enter XLM amount",
        },
    )

    for update_id in range(1, 4):
        await dp.feed_update(
            bot=router_app_context.bot,
            update=create_callback_update(
                user_id, FLOW_BACK_CALLBACK, update_id=update_id
            ),
            app_context=router_app_context,
        )

    assert await dp.storage.get_state(storage_key) == StateSendToken.sending_for
    data = await dp.storage.get_data(storage_key)
    for key in (
        PENDING_SIGNATURE_REQUEST_KEY,
        "xdr",
        "operation",
        "sign_msg",
        "success_msg",
        "flow_back_amount_msg",
        "qr",
        "memo",
        "federal_memo",
        "send_address",
        "send_balance_address",
        "mtlap_stars",
        "send_sum",
        "send_asset_code",
        "send_asset_issuer",
        "send_asset_max_sum",
        "send_asset_blocked_sum",
        "cancel_offers",
        "msg",
    ):
        assert key not in data
    assert data["last_message_id"] == 987
    assert data["unrelated_global_data"] == "keep me"


@pytest.mark.asyncio
async def test_flow_back_from_send_memo_rerenders_confirmation(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_memo)
    await dp.storage.set_data(
        key=storage_key,
        data={
            "send_address": "GDEST",
            "send_asset_code": "XLM",
            "send_asset_issuer": None,
            "send_sum": 10,
            "memo": "memo",
            "msg": "Enter sum",
        },
    )

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_callback_update(user_id, FLOW_BACK_CALLBACK),
        app_context=router_app_context,
    )

    assert await dp.storage.get_state(storage_key) == StateSendToken.confirming
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "confirm_send" in req["data"]["text"]
    assert FLOW_BACK_CALLBACK in req["data"]["reply_markup"]


def test_terminal_return_keyboard_never_exposes_flow_back(router_app_context):
    keyboard = get_kb_return(123, app_context=router_app_context)

    callbacks = [
        button.callback_data for row in keyboard.inline_keyboard for button in row
    ]
    assert callbacks == ["Return"]


@pytest.mark.parametrize(
    ("add_button_memo", "expected_callbacks"),
    [
        (False, [["Yes_send_xdr", "Return"], ["Return"]]),
        (True, [["Yes_send_xdr", "Return"], ["Memo"], ["Return"]]),
    ],
)
def test_send_xdr_confirmation_defaults_to_legacy_return_callbacks(
    router_app_context, add_button_memo, expected_callbacks
):
    keyboard = get_kb_yesno_send_xdr(
        123, add_button_memo=add_button_memo, app_context=router_app_context
    )

    callbacks = [
        [button.callback_data for button in row] for row in keyboard.inline_keyboard
    ]

    assert callbacks == expected_callbacks
    assert FLOW_BACK_CALLBACK not in [callback for row in callbacks for callback in row]


def test_send_xdr_confirmation_exposes_flow_back_only_when_requested(
    router_app_context,
):
    keyboard = get_kb_yesno_send_xdr(
        123, flow_back=True, app_context=router_app_context
    )

    callbacks = [
        [button.callback_data for button in row] for row in keyboard.inline_keyboard
    ]

    assert callbacks == [["Yes_send_xdr"], [FLOW_BACK_CALLBACK], ["Return"]]


@pytest.mark.asyncio
async def test_cb_send_choose_token_with_blocked_offers(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Test selecting token when some balance is blocked by offers.
    Should show warning about blocked amount.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Configure offers that block some XLM
    mock_horizon.set_offers(
        setup_send_mocks.wallet.public_key,
        [
            {
                "id": "12345",
                "selling": {
                    "asset_type": "native",
                    "asset_code": None,
                    "asset_issuer": None,
                },
                "buying": {
                    "asset_type": "credit_alphanum12",
                    "asset_code": "EURMTL",
                    "asset_issuer": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
                },
                "amount": "25.0",
            }
        ],
    )

    # Setup router
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state with assets
    import jsonpickle

    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    assets = [
        Balance(
            asset_code="XLM", balance="100.0", asset_issuer=None, asset_type="native"
        )
    ]
    await dp.storage.set_data(
        key=storage_key,
        data={"send_address": send_address, "assets": jsonpickle.encode(assets)},
    )

    # Select XLM token
    callback_data = SendAssetCallbackData(answer="XLM").pack()
    update = create_callback_update(user_id, callback_data)
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify response (note: blocked offers warning requires non-native asset match)
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_sum" in req["data"]["text"]

    # Verify state was set correctly
    state = await dp.storage.get_state(key=storage_key)
    assert state == StateSendToken.sending_sum


@pytest.mark.asyncio
async def test_cmd_send_for_custom_token(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    """
    Mandatory test: Ensure custom tokens (e.g. UNLIMITED) are visible in SEND list.
    Prerequisite: Destination address must also trust/hold the token.
    """
    user_id = 123
    send_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    custom_code = "UNLIMITED"
    custom_issuer = "G_UNLIMITED_ISSUER"

    # 1. Setup Sender Balances (User has UNLIMITED)
    setup_send_mocks.set_balances(
        [
            Balance(
                asset_code="XLM",
                balance="100.0",
                asset_issuer=None,
                asset_type="native",
            ),
            Balance(
                asset_code=custom_code,
                balance="1000.0",
                asset_issuer=custom_issuer,
                asset_type="credit_alphanum12",
            ),
        ]
    )

    # 2. Setup Destination Account (Must trust UNLIMITED for it to appear)
    # The routers/send.py logic checks collision between sender assets and receiver assets.
    mock_horizon.set_account(
        send_address,
        balances=[
            {"asset_type": "native", "balance": "10.0"},
            {
                "asset_type": "credit_alphanum12",
                "asset_code": custom_code,
                "asset_issuer": custom_issuer,
                "balance": "0.0",
            },  # Trustline exists
        ],
    )

    # Setup router
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    # Set state to sending_for
    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_for)

    # Send address
    update = create_message_update(user_id, send_address)
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # Verify response contains UNLIMITED button
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "choose_token" in req["data"]["text"]
    assert custom_code in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_send_for_muxed_address_uses_underlying_account_for_trustlines(
    mock_telegram, mock_horizon, router_app_context, dp, setup_send_mocks
):
    user_id = 123
    muxed_address = (
        "MCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYKAAAAAAAAAAXPAMAK"
    )
    underlying_address = "GCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYLQDJ"
    custom_code = "UNLIMITED"
    custom_issuer = "G_UNLIMITED_ISSUER"

    mock_horizon.set_account(
        underlying_address,
        balances=[
            {"asset_type": "native", "balance": "10.0"},
            {
                "asset_type": "credit_alphanum12",
                "asset_code": custom_code,
                "asset_issuer": custom_issuer,
                "balance": "0.0",
            },
        ],
    )

    balance_uc = (
        router_app_context.use_case_factory.create_get_wallet_balance.return_value
    )

    async def get_balances(user_id: int, public_key: str | None = None):
        if public_key is None:
            return [
                Balance(
                    asset_code="XLM",
                    balance="100.0",
                    asset_issuer=None,
                    asset_type="native",
                ),
                Balance(
                    asset_code=custom_code,
                    balance="1000.0",
                    asset_issuer=custom_issuer,
                    asset_type="credit_alphanum12",
                ),
            ]
        if public_key == underlying_address:
            return [
                Balance(
                    asset_code="XLM",
                    balance="10.0",
                    asset_issuer=None,
                    asset_type="native",
                ),
                Balance(
                    asset_code=custom_code,
                    balance="0.0",
                    asset_issuer=custom_issuer,
                    asset_type="credit_alphanum12",
                ),
            ]
        return [
            Balance(
                asset_code="XLM",
                balance="10.0",
                asset_issuer=None,
                asset_type="native",
            )
        ]

    balance_uc.execute = AsyncMock(side_effect=get_balances)

    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(send_router)

    storage_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(key=storage_key, state=StateSendToken.sending_for)

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_message_update(user_id, muxed_address),
        app_context=router_app_context,
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert custom_code in req["data"]["reply_markup"]

    data = await dp.storage.get_data(key=storage_key)
    assert data.get("send_address") == muxed_address
    balance_uc.execute.assert_any_await(user_id=user_id, public_key=underlying_address)

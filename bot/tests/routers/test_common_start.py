import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.storage.base import StorageKey

from routers.common_start import (
    router as start_router,
    SettingState,
)
from core.use_cases.user.update_profile import UpdateUserProfile
from middleware.notification_activity import NotificationActivityMiddleware
from core.domain.value_objects import Balance
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
)


@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if start_router.parent_router:
        start_router._parent_router = None


@pytest.fixture
def setup_common_start_mocks(router_app_context):
    """
    Common mock setup for common_start router tests.
    """

    class CommonStartMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _persist_user_update(self, user):
            """Emulate repository update(): the next get_by_id() must see it."""
            self.user_repo.update.return_value = user
            return user

        def _setup_defaults(self):
            # User Repo
            self.user = MagicMock()
            self.user.user_id = 123
            self.user.lang = "en"
            self.user.can_5000 = 0
            self.user.default_address = None
            self.user_repo = MagicMock()
            self.user_repo.get_by_id = AsyncMock(return_value=self.user)
            self.user_repo.update = AsyncMock(side_effect=self._persist_user_update)

            # Wallet Repo
            self.wallet = MagicMock()
            self.wallet.public_key = (
                "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            )
            self.wallet.is_free = False
            self.wallet.assets_visibility = "{}"
            self.wallet_repo = MagicMock()
            self.wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.wallet_repo.get_info = AsyncMock(return_value="[Info]")
            self.wallet_repo.reset_balance_cache = AsyncMock()
            self.wallet_repo.normalize_default_wallets = AsyncMock(return_value=False)

            # Capture session to verify commit
            self.captured_session = None

            def get_wallet_repo(session):
                self.captured_session = session
                return self.wallet_repo

            self.ctx.repository_factory.get_wallet_repository.side_effect = (
                get_wallet_repo
            )

            def get_user_repo(session):
                return self.user_repo

            self.ctx.repository_factory.get_user_repository.side_effect = get_user_repo

            # Secret Service
            self.secret_service = AsyncMock()
            self.secret_service.is_ton_wallet.return_value = False
            self.ctx.use_case_factory.create_wallet_secret_service.return_value = (
                self.secret_service
            )

            # Balance Use Case
            self.balances = [
                Balance(
                    asset_code="EURMTL",
                    balance="100.0",
                    asset_issuer="GISS",
                    asset_type="credit_alphanum12",
                ),
            ]
            self.balance_uc = MagicMock()
            self.balance_uc.execute = AsyncMock(return_value=self.balances)
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = (
                self.balance_uc
            )

            # Update Profile Use Case
            self.update_profile_uc = MagicMock()
            self.update_profile_uc.execute = AsyncMock()
            self.ctx.use_case_factory.create_update_user_profile.return_value = (
                self.update_profile_uc
            )

            # Register User Use Case
            self.register_uc = MagicMock()
            self.register_uc.execute = AsyncMock()
            self.ctx.use_case_factory.create_register_user.return_value = (
                self.register_uc
            )

            # Encryption Service
            self.ctx.encryption_service.encrypt = MagicMock(return_value="ENCRYPTED")

    return CommonStartMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [
        r for r in mock_telegram if r["method"] in ("sendMessage", "editMessageText")
    ]
    return msgs[-1] if msgs else None


def get_all_texts(mock_telegram):
    """Helper to get all texts from mock_telegram."""
    return " ".join(
        [
            m["data"].get("text", "")
            for m in mock_telegram
            if m["method"] in ("sendMessage", "editMessageText")
        ]
    )


@pytest.mark.asyncio
async def test_cmd_start_existing_user(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Test /start for existing user: should show balance."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123

    with patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")):
        await dp.feed_update(
            router_app_context.bot, create_message_update(user_id, "/start")
        )

    texts = get_all_texts(mock_telegram)
    assert "your_balance" in texts
    assert "EURMTL" in texts


@pytest.mark.asyncio
async def test_cmd_start_new_user(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Test /start for new user: should register and show language selection."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123

    with (
        patch("routers.common_start.check_user_lang", AsyncMock(return_value=None)),
        patch("routers.common_start.cmd_language", AsyncMock()) as mock_lang,
        patch("routers.common_start.ensure_provisioned", AsyncMock()) as mock_provision,
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(user_id, "/start")
        )

    # Verify registration called
    setup_common_start_mocks.register_uc.execute.assert_called_once()
    # Verify encryption called (once for secret, once for seed)
    assert setup_common_start_mocks.ctx.encryption_service.encrypt.call_count == 2
    # Verify the freshly registered wallet was provisioned on-chain
    mock_provision.assert_awaited_once()
    provision_kwargs = mock_provision.await_args.kwargs
    assert provision_kwargs["user_id"] == user_id
    assert provision_kwargs["public_key"].startswith("G")
    assert provision_kwargs["secret_key"].startswith("S")
    # Freshly generated key cannot exist on-chain: no existence probe under lock.
    assert provision_kwargs["account_exists"] is False
    # Verify language selection triggered
    mock_lang.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_start_new_user_warns_when_provisioning_fails(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """/start must report a failed activation but keep the registered wallet."""
    from infrastructure.services.free_wallet_provisioning import (
        WalletProvisioningError,
    )

    # Real cmd_language runs below: the error must be a separate message, not a
    # tracked UI message that the language screen immediately overwrites.
    fake_l10n = MagicMock()
    fake_l10n.lang_dict = {"en": {"1_lang": "English"}}
    fake_l10n.get_text.side_effect = lambda user_id, key, params=(): key
    setup_common_start_mocks.ctx.localization_service = fake_l10n

    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123

    with (
        patch("routers.common_start.check_user_lang", AsyncMock(return_value=None)),
        patch(
            "routers.common_start.ensure_provisioned",
            AsyncMock(
                side_effect=WalletProvisioningError(
                    "submit_create_account", RuntimeError("tx_bad_seq")
                )
            ),
        ),
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(user_id, "/start")
        )

    # Registration is committed before provisioning, wallet must not be dropped
    setup_common_start_mocks.register_uc.execute.assert_called_once()
    setup_common_start_mocks.captured_session.commit.assert_awaited()

    all_texts = get_all_texts(mock_telegram)
    assert "wallet_create_error" in all_texts
    assert "Choose language" in all_texts

    # The warning must survive as its own sent message, not as an edited screen.
    error_messages = [
        record
        for record in mock_telegram
        if "wallet_create_error" in record["data"].get("text", "")
    ]
    assert error_messages, "wallet_create_error was never sent"
    assert all(record["method"] == "sendMessage" for record in error_messages)

    # Operator is alerted with the failing step
    admin_messages = [
        record
        for record in mock_telegram
        if record["method"] == "sendMessage"
        and str(record["data"].get("chat_id")) == str(router_app_context.admin_id)
    ]
    assert admin_messages, "admin was not alerted"
    assert "submit_create_account" in admin_messages[0]["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_start_existing_free_wallet_retries_missing_account(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Existing free wallet without on-chain account is provisioned on /start."""
    setup_common_start_mocks.wallet.is_free = True
    setup_common_start_mocks.wallet.use_pin = 0
    setup_common_start_mocks.wallet.secret_key = "ENC_SECRET"
    setup_common_start_mocks.ctx.encryption_service.decrypt = MagicMock(
        return_value="SECRET"
    )
    setup_common_start_mocks.ctx.stellar_service.get_account_details = AsyncMock(
        return_value=None
    )

    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    with (
        patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")),
        patch("routers.common_start.cmd_show_balance", AsyncMock()),
        patch("routers.common_start.ensure_provisioned", AsyncMock()) as mock_provision,
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(123, "/start")
        )

    mock_provision.assert_awaited_once()
    assert (
        mock_provision.await_args.kwargs["public_key"]
        == "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    )
    assert mock_provision.await_args.kwargs["secret_key"] == "SECRET"


@pytest.mark.asyncio
async def test_cmd_start_existing_free_wallet_retries_missing_trustlines(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Account exists but trustline creation failed earlier: provision again."""
    from core.constants import MTL_ASSET

    setup_common_start_mocks.wallet.is_free = True
    setup_common_start_mocks.wallet.use_pin = 0
    setup_common_start_mocks.wallet.secret_key = "ENC_SECRET"
    setup_common_start_mocks.ctx.encryption_service.decrypt = MagicMock(
        return_value="SECRET"
    )
    setup_common_start_mocks.ctx.stellar_service.get_account_details = AsyncMock(
        return_value={
            "account_id": "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI",
            "balances": [
                {"asset_type": "native", "balance": "5.0"},
                {
                    "asset_type": "credit_alphanum4",
                    "asset_code": MTL_ASSET.code,
                    "asset_issuer": MTL_ASSET.issuer,
                    "balance": "0.0",
                },
            ],
        }
    )

    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    with (
        patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")),
        patch("routers.common_start.cmd_show_balance", AsyncMock()),
        patch("routers.common_start.ensure_provisioned", AsyncMock()) as mock_provision,
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(123, "/start")
        )

    mock_provision.assert_awaited_once()
    kwargs = mock_provision.await_args.kwargs
    assert kwargs["account_exists"] is True
    passed_codes = [asset.code for asset in kwargs["assets"]]
    # MTL trustline is already present and must not be resubmitted.
    assert "MTL" not in passed_codes
    assert len(passed_codes) == 3


@pytest.mark.asyncio
async def test_cmd_start_retry_skips_provisioning_when_secret_decrypt_fails(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Undecryptable wallet must never be funded with the master wallet."""
    setup_common_start_mocks.wallet.is_free = True
    setup_common_start_mocks.wallet.use_pin = 0
    setup_common_start_mocks.wallet.secret_key = "ENC_SECRET"
    setup_common_start_mocks.ctx.encryption_service.decrypt = MagicMock(
        return_value=None
    )
    setup_common_start_mocks.ctx.stellar_service.get_account_details = AsyncMock(
        return_value=None
    )

    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    with (
        patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")),
        patch("routers.common_start.cmd_show_balance", AsyncMock()) as mock_balance,
        patch("routers.common_start.ensure_provisioned", AsyncMock()) as mock_provision,
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(123, "/start")
        )

    mock_provision.assert_not_awaited()
    mock_balance.assert_awaited_once()


@pytest.mark.asyncio
async def test_notify_admin_swallows_telegram_errors(router_app_context):
    """Broken Telegram delivery must not raise from the alert helper."""
    from routers.common_start import _notify_admin_provisioning_failed
    from infrastructure.services.free_wallet_provisioning import (
        WalletProvisioningError,
    )

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock(side_effect=RuntimeError("chat not found"))
    router_app_context.bot = fake_bot

    await _notify_admin_provisioning_failed(
        123,
        "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI",
        WalletProvisioningError("submit_create_account", RuntimeError("tx_bad_seq")),
        router_app_context,
    )

    fake_bot.send_message.assert_awaited_once()
    assert fake_bot.send_message.await_args.kwargs["parse_mode"] is None


@pytest.mark.asyncio
async def test_notify_admin_truncates_huge_error(router_app_context):
    from routers.common_start import _notify_admin_provisioning_failed
    from infrastructure.services.free_wallet_provisioning import (
        WalletProvisioningError,
    )

    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock()
    router_app_context.bot = fake_bot

    await _notify_admin_provisioning_failed(
        123,
        "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI",
        WalletProvisioningError("submit_create_account", RuntimeError("x" * 20000)),
        router_app_context,
    )

    sent_text = fake_bot.send_message.await_args.args[1]
    assert len(sent_text) < 4096


@pytest.mark.asyncio
async def test_cmd_start_existing_free_wallet_with_trustlines_is_not_reprovisioned(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Fully provisioned free wallet must not be touched on /start."""
    from core.constants import EURMTL_ASSET, MTL_ASSET, SATSMTL_ASSET, USDM_ASSET

    setup_common_start_mocks.wallet.is_free = True
    setup_common_start_mocks.wallet.use_pin = 0
    setup_common_start_mocks.wallet.secret_key = "ENC_SECRET"
    balances = [{"asset_type": "native", "balance": "5.0"}]
    for asset in (MTL_ASSET, EURMTL_ASSET, SATSMTL_ASSET, USDM_ASSET):
        balances.append(
            {
                "asset_type": "credit_alphanum12",
                "asset_code": asset.code,
                "asset_issuer": asset.issuer,
                "balance": "0.0",
            }
        )
    setup_common_start_mocks.ctx.stellar_service.get_account_details = AsyncMock(
        return_value={"account_id": "G", "balances": balances}
    )

    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    with (
        patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")),
        patch("routers.common_start.cmd_show_balance", AsyncMock()),
        patch("routers.common_start.ensure_provisioned", AsyncMock()) as mock_provision,
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(123, "/start")
        )

    mock_provision.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "secret_key, use_pin",
    [("TON", 0), ("ENC_SECRET", 1), ("ENC_SECRET", 2), ("ENC_SECRET", 10)],
)
async def test_cmd_start_skips_provisioning_for_non_free_wallets(
    mock_telegram,
    router_app_context,
    setup_common_start_mocks,
    secret_key,
    use_pin,
):
    """TON, PIN, password and read-only wallets must never be reprovisioned."""
    setup_common_start_mocks.wallet.is_free = True
    setup_common_start_mocks.wallet.use_pin = use_pin
    setup_common_start_mocks.wallet.secret_key = secret_key

    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    with (
        patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")),
        patch("routers.common_start.cmd_show_balance", AsyncMock()),
        patch("routers.common_start.ensure_provisioned", AsyncMock()) as mock_provision,
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(123, "/start")
        )

    mock_provision.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_start_retry_failure_does_not_block_balance_screen(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """A failed repair attempt must not break the main screen."""
    from infrastructure.services.free_wallet_provisioning import (
        WalletProvisioningError,
    )

    setup_common_start_mocks.wallet.is_free = True
    setup_common_start_mocks.wallet.use_pin = 0
    setup_common_start_mocks.wallet.secret_key = "ENC_SECRET"
    setup_common_start_mocks.ctx.encryption_service.decrypt = MagicMock(
        return_value="SECRET"
    )
    setup_common_start_mocks.ctx.stellar_service.get_account_details = AsyncMock(
        return_value=None
    )

    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    with (
        patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")),
        patch("routers.common_start.cmd_show_balance", AsyncMock()) as mock_balance,
        patch(
            "routers.common_start.ensure_provisioned",
            AsyncMock(
                side_effect=WalletProvisioningError(
                    "trustline_MTL", RuntimeError("timeout")
                )
            ),
        ),
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(123, "/start")
        )

    mock_balance.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_start_sign_flow(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Test /start sign_... flow: should transition to signing."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123

    with (
        patch("routers.common_start.check_user_id", AsyncMock(return_value=True)),
        patch("routers.common_start.cmd_check_xdr", AsyncMock()) as mock_check,
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(user_id, "/start sign_12345")
        )

    mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_start_sign_command_starts_notification_hold_after_activating_fsm(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    dp = router_app_context.dispatcher
    coordinator = MagicMock(touch=AsyncMock(), complete_flow=AsyncMock())
    router_app_context.notification_coordinator = coordinator
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(NotificationActivityMiddleware())
    dp.include_router(start_router)
    user_id = 123

    async def activate_signing_flow(_session, _url, _user_id, state, *, app_context):
        await state.set_state("Signing:awaiting_confirmation")

    with (
        patch("routers.common_start.check_user_id", AsyncMock(return_value=True)),
        patch("routers.common_start.cmd_check_xdr", side_effect=activate_signing_flow),
    ):
        await dp.feed_update(
            router_app_context.bot, create_message_update(user_id, "/start sign_12345")
        )

    state_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    assert await dp.storage.get_state(state_key) == "Signing:awaiting_confirmation"
    coordinator.touch.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_plain_start_completes_notification_flow_without_touching_hold(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    dp = router_app_context.dispatcher
    coordinator = MagicMock(touch=AsyncMock(), complete_flow=AsyncMock())
    router_app_context.notification_coordinator = coordinator
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(NotificationActivityMiddleware())
    dp.include_router(start_router)

    with patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")):
        await dp.feed_update(
            router_app_context.bot, create_message_update(123, "/start")
        )

    coordinator.touch.assert_not_awaited()
    coordinator.complete_flow.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_cb_return_to_main(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Test clicking 'Return' button: should show balance."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "Return"))

    req = get_latest_msg(mock_telegram)
    assert "your_balance" in req["data"]["text"]


@pytest.mark.asyncio
async def test_start_and_return_complete_notification_flow(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Terminal navigation releases queued blockchain notifications immediately."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)
    coordinator = MagicMock(complete_flow=AsyncMock())
    router_app_context.notification_coordinator = coordinator

    with patch("routers.common_start.check_user_lang", AsyncMock(return_value="en")):
        await dp.feed_update(
            router_app_context.bot, create_message_update(123, "/start")
        )
    await dp.feed_update(router_app_context.bot, create_callback_update(123, "Return"))

    assert coordinator.complete_flow.await_count == 2


@pytest.mark.asyncio
async def test_delete_return_renders_main_menu_before_flushing_notifications(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)
    coordinator = MagicMock(complete_flow=AsyncMock())
    router_app_context.notification_coordinator = coordinator

    async def deliver_queued_notification(user_id):
        await router_app_context.bot.send_message(
            user_id, "queued blockchain notification"
        )

    coordinator.complete_flow.side_effect = deliver_queued_notification
    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, "DeleteReturn")
    )

    terminal_texts = [
        request["data"]["text"]
        for request in mock_telegram
        if request["method"] in ("sendMessage", "editMessageText")
    ]
    assert "your_balance" in terminal_texts[-2]
    assert terminal_texts[-1] == "queued blockchain notification"


@pytest.mark.asyncio
async def test_cmd_donate_start(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Test /donate command."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123
    await dp.feed_update(
        router_app_context.bot, create_message_update(user_id, "/donate")
    )

    req = get_latest_msg(mock_telegram)
    assert "Choose how much you want to send" in req["data"]["text"]

    state_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    assert await dp.storage.get_state(state_key) == SettingState.send_donate_sum


@pytest.mark.asyncio
async def test_cb_set_limit_toggle(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """OffLimits callback must persist can_5000 through UpdateUserProfile.

    The mock repo keeps the state on the helper object: update() applies and
    get_by_id() re-reads it, mimicking a second DB read after the toggle.
    """
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    mocks = setup_common_start_mocks
    user_id = 123
    mocks.user.can_5000 = 0

    mocks.update_profile_uc.execute = AsyncMock(
        side_effect=UpdateUserProfile(mocks.user_repo).execute
    )

    # 1. Toggle ON: use case writes through the repo
    await dp.feed_update(
        router_app_context.bot, create_callback_update(user_id, "OffLimits")
    )
    assert mocks.user.can_5000 == 1
    sent = get_latest_msg(mock_telegram)["data"]["reply_markup"]
    assert '"callback_data": "OffLimits"' in sent
    assert '"callback_data": "Return"' in sent

    # 2. Fresh read still shows the persisted value (limit disabled)
    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(user_id, "SetLimit", update_id=2),
    )
    assert get_latest_msg(mock_telegram)["data"]["text"] == "limits"

    # 3. Toggle OFF
    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(user_id, "OffLimits", update_id=3),
    )
    assert mocks.user.can_5000 == 0
    sent = get_latest_msg(mock_telegram)["data"]["reply_markup"]
    assert '"callback_data": "OffLimits"' in sent

    # 4. Use case wrote through the repository exactly once per toggle
    assert mocks.user_repo.update.await_count == 2


@pytest.mark.asyncio
async def test_cmd_refresh_balances(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """
    Test Refresh button: should reset cache, show balance, AND COMMIT.
    Commit is crucial to persist the cache reset and any balance updates.

    Note: May call commit twice:
    1. Once in cmd_refresh (always)
    2. Once in check_update_username (if username changed)
    """
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "Refresh"))

    setup_common_start_mocks.wallet_repo.reset_balance_cache.assert_not_called()
    setup_common_start_mocks.balance_uc.execute.assert_awaited_once_with(
        user_id=123, force_refresh=True
    )

    # Verify session.commit() was called at least once (may be twice if username updated)
    assert setup_common_start_mocks.captured_session is not None
    assert setup_common_start_mocks.captured_session.commit.call_count >= 1, (
        "commit should be called at least once"
    )

    texts = get_all_texts(mock_telegram)
    assert "your_balance" in texts


@pytest.mark.asyncio
async def test_cq_show_more_toggle(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Test ShowMoreToggle callback."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    user_id = 123
    state_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )

    # Initial: False
    await dp.storage.update_data(state_key, {"show_more": False})

    await dp.feed_update(
        router_app_context.bot, create_callback_update(user_id, "ShowMoreToggle")
    )

    data = await dp.storage.get_data(state_key)
    assert data["show_more"] is True

    # Verify message was edited (editMessageText)
    req = get_latest_msg(mock_telegram)
    assert req["method"] == "editMessageText"


@pytest.mark.asyncio
async def test_delete_all_does_not_pretend_to_delete(
    mock_telegram, router_app_context, setup_common_start_mocks
):
    """Legacy /delete_all must be honest: it deletes nothing."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(start_router)

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_message_update(123, "/delete_all"),
        app_context=router_app_context,
    )

    texts = get_all_texts(mock_telegram)
    assert "Nothing was deleted" in texts
    assert "/start" in texts
    # No registration/wallet side effects.
    setup_common_start_mocks.register_uc.execute.assert_not_called()

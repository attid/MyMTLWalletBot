from unittest.mock import ANY, AsyncMock, MagicMock

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
from core.models.sep24 import InteractiveSession
from infrastructure.services.signing_facade import SignatureMode, SignaturePurpose
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


def make_localization(router_app_context):
    """Render keys with their params so tests can assert real values."""

    def _get_text(user_id, key, params=()):
        parts = [key, *[str(param) for param in params]]
        return " ".join(parts)

    router_app_context.localization_service.get_text.side_effect = _get_text


@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if assets_router.parent_router:
        assets_router._parent_router = None


def final_assets_message(mock_telegram):
    """`/assets` now renders progress first and edits it into the final list."""
    return get_telegram_request(
        mock_telegram, "editMessageText"
    ) or get_telegram_request(mock_telegram, "sendMessage")


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

    req = final_assets_message(mock_telegram)
    assert "sep_assets_title" in req["data"]["text"]
    assert "sep_assets_disclaimer" in req["data"]["text"]
    assert "BTCLN" in req["data"]["reply_markup"]
    assert "NOS" not in req["data"]["reply_markup"]
    router_app_context.anchor_discovery_service.discover_assets.assert_awaited_once_with(
        [Asset("BTCLN", ISSUER), Asset("NOS", "GNOSEPISSUER")],
        on_progress=ANY,
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
    req = final_assets_message(mock_telegram)
    assert "sep_assets_title" in req["data"]["text"]
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
    assert "sep_asset_deposit_line" in req["data"]["text"]
    assert "sep_asset_withdraw_line" in req["data"]["text"]
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
async def test_asset_requests_read_only_wallet_uses_webapp_sep10_auth(
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
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=make_support()
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.get_sep10_challenge_xdr = AsyncMock(
        return_value="SEP10_CHALLENGE_XDR"
    )
    router_app_context.signing_facade = MagicMock()
    router_app_context.signing_facade.request_signature = AsyncMock()

    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(
            user_id,
            AssetAction(action="requests", key="a0").pack(),
            message_id=99,
        ),
    )

    router_app_context.signing_facade.request_signature.assert_awaited_once()
    request = router_app_context.signing_facade.request_signature.await_args.kwargs[
        "request"
    ]
    assert request.purpose is SignaturePurpose.SEP10_AUTH
    assert request.mode is SignatureMode.SIGN_ONLY
    assert request.xdr == "SEP10_CHALLENGE_XDR"
    assert request.fsm_func is not None
    router_app_context.anchor_transaction_service.get_sep10_challenge_xdr.assert_awaited_once_with(
        make_support(),
        "GPUBLIC",
    )


@pytest.mark.asyncio
async def test_asset_requests_uses_signing_facade_for_sep10_auth(
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
        {"anchor_assets": {"a0": make_support().asset.to_string()}},
    )
    wallet_repo = MagicMock()
    wallet_repo.get_default_wallet = AsyncMock(
        return_value=Wallet(
            id=1,
            user_id=user_id,
            public_key="GPUBLIC",
            is_default=True,
            is_free=False,
            use_pin=1,
        )
    )
    router_app_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    router_app_context.signing_facade = MagicMock()
    router_app_context.signing_facade.request_signature = AsyncMock()

    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(
            user_id,
            AssetAction(action="requests", key="a0").pack(),
            message_id=99,
        ),
    )

    router_app_context.signing_facade.request_signature.assert_awaited_once()
    request = router_app_context.signing_facade.request_signature.await_args.kwargs[
        "request"
    ]
    assert request.purpose is SignaturePurpose.SEP10_AUTH
    assert request.mode is SignatureMode.SIGN_ONLY
    assert request.fsm_func is not None
    assert request.sign_msg == "sign_sep10_msg"


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
    make_localization(router_app_context)
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
    assert "sep_requests_title" in req["data"]["text"]
    assert "SEP-24 / deposit / sep24_status_completed" in req["data"]["text"]
    router_app_context.anchor_transaction_service.fetch_transactions.assert_awaited_once_with(
        make_support(),
        ANY,
        user_id=user_id,
    )
    assert "tx-1" in req["data"]["text"]
    assert "100" in req["data"]["text"]


@pytest.mark.asyncio
async def test_show_asset_requests_after_webapp_sep10_sends_transactions(
    mock_telegram, router_app_context
):
    user_id = 123
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={
            "sep10_signed_xdr": "SIGNED_SEP10_XDR",
            "anchor_request_asset": make_support().asset.to_string(),
            "anchor_request_key": "a0",
        }
    )
    session = MagicMock()
    support = make_support()
    make_localization(router_app_context)
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
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=support
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.exchange_sep10_token = AsyncMock(
        return_value="ANCHOR_TOKEN"
    )
    router_app_context.anchor_transaction_service.remember_sep10_token = AsyncMock()
    router_app_context.anchor_transaction_service.fetch_transactions_with_token = (
        AsyncMock(
            return_value=[
                AnchorTransaction(
                    protocol=AnchorTransactionProtocol.SEP24,
                    id="tx-webapp",
                    kind="deposit",
                    status="completed",
                    amount_in="100",
                    updated_at="2026-05-23T10:00:00Z",
                    more_info_url="https://anchor.test/tx-webapp",
                )
            ]
        )
    )

    from routers.assets import _show_asset_requests_after_webapp_sep10

    await _show_asset_requests_after_webapp_sep10(
        session,
        user_id,
        state,
        app_context=router_app_context,
    )

    router_app_context.anchor_transaction_service.exchange_sep10_token.assert_awaited_once_with(
        "https://kbtrading.org/auth",
        "SIGNED_SEP10_XDR",
    )
    router_app_context.anchor_transaction_service.fetch_transactions_with_token.assert_awaited_once_with(
        support,
        "ANCHOR_TOKEN",
    )
    router_app_context.anchor_transaction_service.remember_sep10_token.assert_awaited_once_with(
        support,
        "ANCHOR_TOKEN",
        user_id=user_id,
        public_key="GPUBLIC",
    )
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "sep_requests_title" in req["data"]["text"]
    assert "tx-webapp" in req["data"]["text"]


@pytest.mark.asyncio
async def test_asset_deposit_read_only_wallet_uses_webapp_sep10_auth(
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
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=make_support(sep24=True)
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.get_sep10_challenge_xdr = AsyncMock(
        return_value="SEP10_CHALLENGE_XDR"
    )
    router_app_context.signing_facade = MagicMock()
    router_app_context.signing_facade.request_signature = AsyncMock()

    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(
            user_id,
            AssetAction(action="deposit", key="a0").pack(),
            message_id=99,
        ),
    )

    router_app_context.signing_facade.request_signature.assert_awaited_once()
    request = router_app_context.signing_facade.request_signature.await_args.kwargs[
        "request"
    ]
    assert request.purpose is SignaturePurpose.SEP10_AUTH
    assert request.mode is SignatureMode.SIGN_ONLY
    assert request.xdr == "SEP10_CHALLENGE_XDR"
    assert request.operation == "SEP-24 deposit for BTCLN"
    router_app_context.anchor_transaction_service.get_sep10_challenge_xdr.assert_awaited_once_with(
        make_support(sep24=True),
        "GPUBLIC",
    )


@pytest.mark.asyncio
async def test_asset_deposit_uses_signing_facade_for_sep10_auth(
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
        {"anchor_assets": {"a0": make_support(sep24=True).asset.to_string()}},
    )
    wallet_repo = MagicMock()
    wallet_repo.get_default_wallet = AsyncMock(
        return_value=Wallet(
            id=1,
            user_id=user_id,
            public_key="GPUBLIC",
            is_default=True,
            is_free=False,
            use_pin=1,
        )
    )
    router_app_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    router_app_context.signing_facade = MagicMock()
    router_app_context.signing_facade.request_signature = AsyncMock()

    await dp.feed_update(
        router_app_context.bot,
        create_callback_update(
            user_id,
            AssetAction(action="deposit", key="a0").pack(),
            message_id=99,
        ),
    )

    router_app_context.signing_facade.request_signature.assert_awaited_once()
    request = router_app_context.signing_facade.request_signature.await_args.kwargs[
        "request"
    ]
    assert request.purpose is SignaturePurpose.SEP10_AUTH
    assert request.mode is SignatureMode.SIGN_ONLY
    assert request.fsm_func is not None
    assert request.operation == "SEP-24 deposit for BTCLN"


@pytest.mark.asyncio
async def test_show_sep24_interactive_after_pin_sends_url_button(
    mock_telegram, router_app_context
):
    user_id = 123
    state = MagicMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "pin": "1234",
            "anchor_transfer_asset": make_support().asset.to_string(),
            "anchor_transfer_operation": "deposit",
        }
    )
    session = MagicMock()
    support = make_support(sep24=True)
    make_localization(router_app_context)
    wallet_repo = MagicMock()
    wallet_repo.get_default_wallet = AsyncMock(
        return_value=Wallet(
            id=1,
            user_id=user_id,
            public_key="GPUBLIC",
            is_default=True,
            is_free=False,
            use_pin=1,
        )
    )
    router_app_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=support
    )
    router_app_context.stellar_service.get_user_keypair = AsyncMock(
        return_value=MagicMock(public_key="GPUBLIC")
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.start_sep24_interactive = AsyncMock(
        return_value=InteractiveSession(
            url="https://anchor.test/interactive/deposit/1",
            transaction_id="tx-1",
            kind="interactive_customer_info_needed",
        )
    )

    await _show_sep24_interactive_after_pin(
        session,
        user_id,
        state,
        app_context=router_app_context,
    )

    session_result = router_app_context.anchor_transaction_service.start_sep24_interactive.await_args.kwargs
    assert session_result["account"] == "GPUBLIC"
    assert session_result["operation"] == "deposit"
    assert session_result["user_id"] == user_id
    state.update_data.assert_awaited()
    stored = state.update_data.await_args_list[-1].kwargs
    assert stored["anchor_transfer_id"] == "tx-1"
    assert stored["anchor_transfer_url"] == "https://anchor.test/interactive/deposit/1"
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "sep24_ready" in req["data"]["text"]
    assert "sep_assets_disclaimer" in req["data"]["text"]
    assert "https://anchor.test/interactive/deposit/1" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_show_sep24_interactive_after_webapp_sep10_sends_url_button(
    mock_telegram, router_app_context
):
    user_id = 123
    state = MagicMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "sep10_signed_xdr": "SIGNED_SEP10_XDR",
            "anchor_transfer_asset": make_support().asset.to_string(),
            "anchor_transfer_operation": "deposit",
        }
    )
    session = MagicMock()
    support = make_support(sep24=True)
    make_localization(router_app_context)
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
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=support
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.exchange_sep10_token = AsyncMock(
        return_value="ANCHOR_TOKEN"
    )
    router_app_context.anchor_transaction_service.remember_sep10_token = AsyncMock()
    router_app_context.anchor_transaction_service.start_sep24_interactive_with_token = (
        AsyncMock(
            return_value=InteractiveSession(
                url="https://anchor.test/interactive/deposit/2",
                transaction_id="tx-2",
            )
        )
    )

    from routers.assets import _show_sep24_interactive_after_webapp_sep10

    await _show_sep24_interactive_after_webapp_sep10(
        session,
        user_id,
        state,
        app_context=router_app_context,
    )

    router_app_context.anchor_transaction_service.exchange_sep10_token.assert_awaited_once_with(
        "https://kbtrading.org/auth",
        "SIGNED_SEP10_XDR",
    )
    router_app_context.anchor_transaction_service.start_sep24_interactive_with_token.assert_awaited_once_with(
        support,
        "ANCHOR_TOKEN",
        operation="deposit",
        account="GPUBLIC",
        lang=None,
    )
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "sep24_ready" in req["data"]["text"]
    assert "sep_assets_disclaimer" in req["data"]["text"]
    assert "https://anchor.test/interactive/deposit/2" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_sep24_start_error_maps_anchor_error_code(
    mock_telegram, router_app_context
):
    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionRequestError,
    )

    user_id = 123
    state = MagicMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "pin": "1234",
            "anchor_transfer_asset": make_support().asset.to_string(),
            "anchor_transfer_operation": "deposit",
        }
    )
    session = MagicMock()
    make_localization(router_app_context)
    wallet_repo = MagicMock()
    wallet_repo.get_default_wallet = AsyncMock(
        return_value=Wallet(
            id=1,
            user_id=user_id,
            public_key="GPUBLIC",
            is_default=True,
            is_free=False,
            use_pin=1,
        )
    )
    router_app_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=make_support(sep24=True)
    )
    router_app_context.stellar_service.get_user_keypair = AsyncMock(
        return_value=MagicMock(public_key="GPUBLIC")
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.start_sep24_interactive = AsyncMock(
        side_effect=AnchorTransactionRequestError(
            url="https://kbtrading.org/sep24/transactions/deposit/interactive",
            status=401,
            body={"error": "authentication_required"},
        )
    )

    await _show_sep24_interactive_after_pin(
        session,
        user_id,
        state,
        app_context=router_app_context,
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "sep24_error_authentication" in req["data"]["text"]
    state.update_data.assert_not_awaited()


def make_status_setup(router_app_context, *, user_id=123, transaction_id="tx-1"):
    """Common arrange for the SEP-24 status screen tests."""
    support = make_support(sep24=True)
    make_localization(router_app_context)
    wallet_repo = MagicMock()
    wallet_repo.get_default_wallet = AsyncMock(
        return_value=Wallet(
            id=1,
            user_id=user_id,
            public_key="GPUBLIC",
            is_default=True,
            is_free=False,
            use_pin=1,
        )
    )
    router_app_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    router_app_context.anchor_discovery_service = MagicMock()
    router_app_context.anchor_discovery_service.discover_asset = AsyncMock(
        return_value=support
    )
    router_app_context.stellar_service.get_account_details = AsyncMock(
        return_value={
            "balances": [
                {
                    "asset_code": "BTCLN",
                    "asset_issuer": ISSUER,
                    "balance": "5",
                }
            ]
        }
    )
    return support, {
        "anchor_transfer_asset": support.asset.to_string(),
        "anchor_transfer_operation": "withdraw",
        "anchor_transfer_key": "a0",
        "anchor_transfer_id": transaction_id,
        "anchor_transfer_url": "https://anchor.test/interactive/1",
    }


async def seed_state(router_app_context, data, *, user_id: int = 123) -> None:
    await router_app_context.dispatcher.storage.set_data(
        StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id),
        data,
    )


@pytest.mark.asyncio
async def test_sep24_status_shows_instruction_with_muxed_destination(
    mock_telegram, router_app_context
):
    from core.models.sep24 import Sep24TransactionView
    from keyboards.assets import SEP24_STATUS_CALLBACK
    from infrastructure.services.sep24.instructions import PaymentInstructions

    muxed = "MCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYKAAAAAAAAAA73IMRS"
    support, data = make_status_setup(router_app_context)
    await seed_state(router_app_context, data)
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.fetch_sep24_transaction_cached = (
        AsyncMock(
            return_value=Sep24TransactionView(
                id="tx-1",
                kind="withdrawal",
                status="pending_user_transfer_start",
                amount_in="20",
                instructions=PaymentInstructions(
                    destination=muxed,
                    asset_code="BTCLN",
                    amount="20",
                    source="instructions",
                ),
                more_info_url="https://anchor.test/more/tx-1",
            )
        )
    )

    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, SEP24_STATUS_CALLBACK)
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    text = req["data"]["text"]
    assert "sep24_status_line" in text
    assert "sep24_status_pending_user_transfer" in text
    assert muxed in text
    assert "sep24_status_muxed_hint" in text
    assert "sep24_status_more_info" in text
    assert "https://anchor.test/interactive/1" in req["data"]["reply_markup"]
    router_app_context.anchor_transaction_service.fetch_sep24_transaction_cached.assert_awaited_once()


@pytest.mark.asyncio
async def test_sep24_status_asks_to_reauthorize_when_token_is_gone(
    mock_telegram, router_app_context
):
    from infrastructure.services.anchor_transaction_service import Sep24ReauthRequired
    from keyboards.assets import SEP24_STATUS_CALLBACK

    support, data = make_status_setup(router_app_context)
    await seed_state(router_app_context, data)
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.fetch_sep24_transaction_cached = (
        AsyncMock(side_effect=Sep24ReauthRequired("no token"))
    )

    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, SEP24_STATUS_CALLBACK)
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "sep24_status_reauth" in req["data"]["text"]
    assert "kb_sep24_reauth" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_sep24_status_warns_about_missing_trustline_for_deposit(
    mock_telegram, router_app_context
):
    from core.models.sep24 import Sep24TransactionView
    from keyboards.assets import SEP24_STATUS_CALLBACK

    support, data = make_status_setup(router_app_context)
    data["anchor_transfer_operation"] = "deposit"
    await seed_state(router_app_context, data)
    router_app_context.stellar_service.get_account_details = AsyncMock(
        return_value={"balances": [{"asset_type": "native", "balance": "10"}]}
    )
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.fetch_sep24_transaction_cached = (
        AsyncMock(
            return_value=Sep24TransactionView(
                id="tx-1",
                kind="deposit",
                status="pending_anchor",
            )
        )
    )

    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, SEP24_STATUS_CALLBACK)
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "sep24_status_trustline_missing" in req["data"]["text"]


@pytest.mark.asyncio
async def test_sep24_status_without_transaction_id_asks_to_restart(
    mock_telegram, router_app_context
):
    from keyboards.assets import SEP24_STATUS_CALLBACK

    make_localization(router_app_context)
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"anchor_transfer_operation": "deposit"})

    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)
    await dp.storage.set_data(
        StorageKey(bot_id=router_app_context.bot.id, chat_id=123, user_id=123),
        {"anchor_transfer_operation": "deposit"},
    )

    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, SEP24_STATUS_CALLBACK)
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "sep24_status_unavailable" in req["data"]["text"]


@pytest.mark.asyncio
async def test_sep24_status_hides_instructions_on_terminal_status(
    mock_telegram, router_app_context
):
    from core.models.sep24 import Sep24TransactionView
    from infrastructure.services.sep24.instructions import PaymentInstructions
    from keyboards.assets import SEP24_STATUS_CALLBACK

    support, data = make_status_setup(router_app_context)
    await seed_state(router_app_context, data)
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.fetch_sep24_transaction_cached = (
        AsyncMock(
            return_value=Sep24TransactionView(
                id="tx-1",
                kind="withdrawal",
                status="completed",
                instructions=PaymentInstructions(
                    destination="GANCHORACCOUNT",
                    memo="3289",
                    memo_type="id",
                    asset_code="BTCLN",
                    amount="20",
                ),
            )
        )
    )

    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, SEP24_STATUS_CALLBACK)
    )

    text = get_telegram_request(mock_telegram, "sendMessage")["data"]["text"]
    assert "sep24_status_completed" in text
    assert "GANCHORACCOUNT" not in text
    assert "sep24_status_pay_to" not in text


@pytest.mark.asyncio
async def test_sep24_status_shows_raw_anchor_error_text(
    mock_telegram, router_app_context
):
    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionRequestError,
    )
    from keyboards.assets import SEP24_STATUS_CALLBACK

    support, data = make_status_setup(router_app_context)
    await seed_state(router_app_context, data)
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.fetch_sep24_transaction_cached = (
        AsyncMock(
            side_effect=AnchorTransactionRequestError(
                url="https://anchor.test/sep24/transaction",
                status=400,
                body={"error": "KYC required for Germany"},
            )
        )
    )

    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, SEP24_STATUS_CALLBACK)
    )

    text = get_telegram_request(mock_telegram, "sendMessage")["data"]["text"]
    assert "sep24_status_fetch_error" in text
    assert "KYC required for Germany" in text


@pytest.mark.asyncio
async def test_sep24_status_without_id_offers_no_refresh(
    mock_telegram, router_app_context
):
    from keyboards.assets import SEP24_STATUS_CALLBACK

    make_localization(router_app_context)
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)
    await dp.storage.set_data(
        StorageKey(bot_id=router_app_context.bot.id, chat_id=123, user_id=123),
        {"anchor_transfer_operation": "deposit"},
    )

    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, SEP24_STATUS_CALLBACK)
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "Sep24StatusRefresh" not in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_sep24_status_reauth_button_replays_the_original_action(
    mock_telegram, router_app_context
):
    from infrastructure.services.anchor_transaction_service import Sep24ReauthRequired
    from keyboards.assets import SEP24_STATUS_CALLBACK

    support, data = make_status_setup(router_app_context)
    data["anchor_transfer_operation"] = "deposit"
    await seed_state(router_app_context, data)
    router_app_context.anchor_transaction_service = MagicMock()
    router_app_context.anchor_transaction_service.fetch_sep24_transaction_cached = (
        AsyncMock(side_effect=Sep24ReauthRequired("expired"))
    )

    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    await dp.feed_update(
        router_app_context.bot, create_callback_update(123, SEP24_STATUS_CALLBACK)
    )

    markup = get_telegram_request(mock_telegram, "sendMessage")["data"]["reply_markup"]
    assert AssetAction(action="deposit", key="a0").pack() in markup


@pytest.mark.asyncio
async def test_missing_trustline_is_false_for_native_xlm(router_app_context):
    from routers.assets import _missing_trustline

    router_app_context.stellar_service.get_account_details = AsyncMock(
        return_value={"balances": [{"asset_type": "native", "balance": "10"}]}
    )

    assert (
        await _missing_trustline(router_app_context, "GPUBLIC", Asset("XLM", None))
        is False
    )
    assert (
        await _missing_trustline(router_app_context, "GPUBLIC", Asset("BTCLN", ISSUER))
        is True
    )


@pytest.mark.asyncio
async def test_assets_command_warns_when_discovery_hit_the_budget(
    mock_telegram, router_app_context
):
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    get_balance = MagicMock()
    get_balance.execute = AsyncMock(
        return_value=[Balance("BTCLN", ISSUER, "credit_alphanum12", "12000")]
    )
    router_app_context.use_case_factory.create_get_wallet_balance.return_value = (
        get_balance
    )
    make_localization(router_app_context)
    discovery = MagicMock()
    discovery.discover_assets = AsyncMock(return_value=[make_support()])
    discovery.last_call_truncated = True
    router_app_context.anchor_discovery_service = discovery

    await dp.feed_update(router_app_context.bot, create_message_update(123, "/assets"))

    text = final_assets_message(mock_telegram)["data"]["text"]
    assert "sep_assets_partial" in text


@pytest.mark.asyncio
async def test_assets_command_shows_discovery_progress(
    mock_telegram, router_app_context
):
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(assets_router)

    get_balance = MagicMock()
    get_balance.execute = AsyncMock(
        return_value=[Balance("BTCLN", ISSUER, "credit_alphanum12", "12000")]
    )
    router_app_context.use_case_factory.create_get_wallet_balance.return_value = (
        get_balance
    )
    make_localization(router_app_context)
    discovery = MagicMock()
    discovery.discover_assets = AsyncMock(return_value=[make_support()])
    router_app_context.anchor_discovery_service = discovery

    await dp.feed_update(router_app_context.bot, create_message_update(123, "/assets"))

    first = get_telegram_request(mock_telegram, "sendMessage", last=False)[0]
    assert "sep_assets_progress" in first["data"]["text"]
    assert "0" in first["data"]["text"] and "1" in first["data"]["text"]
    final = final_assets_message(mock_telegram)
    assert "sep_assets_title" in final["data"]["text"]

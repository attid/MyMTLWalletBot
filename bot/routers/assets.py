import asyncio

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from html import escape
import jsonpickle  # type: ignore
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.value_objects import Asset
from core.models.anchor_asset import (
    AnchorAssetSupport,
    SepOperationSupport,
    SepProtocolSupport,
)
from core.models.anchor_transaction import AnchorTransaction
from core.models.sep24 import (
    Sep24TransactionView,
    awaits_user_transfer,
    sep24_lang_hint,
    sep24_known_error_i18n_key,
    sep24_status_i18n_key,
)
from infrastructure.services.anchor_discovery_service import AnchorDiscoveryService
from infrastructure.services.anchor_transaction_service import (
    AnchorTransactionService,
    Sep24ReauthRequired,
)
from infrastructure.services.app_context import AppContext
from infrastructure.services.signing_facade import (
    SignatureMode,
    SignaturePurpose,
    SignatureRequest,
    SigningFacade,
)
from infrastructure.utils.telegram_utils import (
    clear_last_message_id,
    clear_state,
    my_gettext,
    send_message,
)
from keyboards.assets import (
    SEP24_STATUS_CALLBACK,
    SEP24_STATUS_REFRESH_CALLBACK,
    AssetAction,
    asset_actions_keyboard,
    assets_list_keyboard,
    sep24_interactive_keyboard,
    sep24_status_keyboard,
)

router = Router()
router.message.filter(F.chat.type == "private")

_anchor_discovery_service = AnchorDiscoveryService()
_anchor_transaction_service = AnchorTransactionService()


def _t(user_id, key: str, app_context: AppContext, params: tuple = ()) -> str:
    """Localized text for the SEP flow."""
    return my_gettext(user_id, key, params, app_context=app_context)


def _operation_label(operation: str, app_context: AppContext, user_id) -> str:
    key = (
        "sep_operation_deposit" if operation == "deposit" else "sep_operation_withdraw"
    )
    return _t(user_id, key, app_context)


async def _lang_hint(user_id: int, app_context: AppContext) -> str | None:
    """SEP-24 `lang` hint for the user's bot language."""
    service = app_context.localization_service
    if service is None:
        return None
    try:
        language = await service.get_user_language_async(user_id)
    except Exception:  # noqa: BLE001 - lang is only a hint
        return None
    if not isinstance(language, str):
        return None
    return sep24_lang_hint(language)


class _AssetsProgress:
    """Live "checking anchors" message for `/assets`.

    Discovery is network-bound and can take several seconds, so the initial
    message is rewritten in place at most once per second (Telegram limit) with
    the number of already checked assets.
    """

    def __init__(
        self,
        session: AsyncSession,
        user_id: int,
        total: int,
        *,
        app_context: AppContext,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._total = total
        self._app_context = app_context
        self._done = 0
        self._rendered = -1
        self._task: asyncio.Task | None = None

    def update(self, done: int, total: int) -> None:
        self._done = done
        self._total = total

    async def start(self) -> None:
        if self._total <= 0:
            return
        await self._render()
        self._task = asyncio.create_task(self._tick())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            await self._render()

    async def _render(self) -> None:
        if self._total <= 0 or self._done == self._rendered:
            return
        self._rendered = self._done
        await send_message(
            self._session,
            self._user_id,
            _t(
                self._user_id,
                "sep_assets_progress",
                self._app_context,
                (self._done, self._total),
            ),
            app_context=self._app_context,
        )


@router.message(Command(commands=["assets"]))
async def cmd_assets(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None:
        return

    await clear_state(state)
    await clear_last_message_id(message.from_user.id, app_context=app_context)

    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    balances = await balance_use_case.execute(message.from_user.id)
    assets = [
        Asset(balance.asset_code, balance.asset_issuer)
        for balance in balances
        if balance.asset_issuer
    ]

    discovery = _get_anchor_discovery_service(app_context)
    progress = _AssetsProgress(
        session, message.from_user.id, len(assets), app_context=app_context
    )
    await progress.start()
    try:
        supported_assets = await discovery.discover_assets(
            assets, on_progress=progress.update
        )
    finally:
        await progress.stop()
    await state.update_data(
        anchor_assets={
            f"a{idx}": support.asset.to_string()
            for idx, support in enumerate(supported_assets)
        }
    )

    if not supported_assets:
        await send_message(
            session,
            message,
            _t(message.from_user.id, "sep_assets_empty", app_context),
            app_context=app_context,
        )
        return

    blocks = [
        _t(message.from_user.id, "sep_assets_disclaimer", app_context),
        _t(message.from_user.id, "sep_assets_title", app_context),
    ]
    if getattr(discovery, "last_call_truncated", False):
        blocks.append(_t(message.from_user.id, "sep_assets_partial", app_context))
    await send_message(
        session,
        message,
        "\n\n".join(blocks),
        reply_markup=assets_list_keyboard(
            supported_assets,
            message.from_user.id,
            app_context=app_context,
        ),
        app_context=app_context,
    )


@router.callback_query(AssetAction.filter(F.action == "view"))
async def cmd_asset_view(
    callback: types.CallbackQuery,
    callback_data: AssetAction,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if callback.from_user is None:
        return
    asset = await _asset_from_state(state, callback_data.key)
    if asset is None:
        await callback.answer(
            _t(callback.from_user.id, "sep_assets_expired", app_context),
            show_alert=True,
        )
        return

    support = await _get_anchor_discovery_service(app_context).discover_asset(asset)
    if support is None:
        await callback.answer(
            _t(callback.from_user.id, "sep_support_unavailable", app_context),
            show_alert=True,
        )
        return

    await send_message(
        session,
        callback,
        _format_asset_support(
            support, user_id=callback.from_user.id, app_context=app_context
        ),
        reply_markup=asset_actions_keyboard(
            callback_data.key,
            callback.from_user.id,
            app_context=app_context,
        ),
        app_context=app_context,
    )
    await callback.answer()


@router.callback_query(AssetAction.filter(F.action == "requests"))
async def cmd_asset_requests(
    callback: types.CallbackQuery,
    callback_data: AssetAction,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if callback.from_user is None:
        return

    asset = await _asset_from_state(state, callback_data.key)
    if asset is None:
        await callback.answer(
            _t(callback.from_user.id, "sep_assets_expired", app_context),
            show_alert=True,
        )
        return

    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    fsm_func = _show_asset_requests_after_pin
    request_xdr = ""
    if wallet and wallet.use_pin == 10:
        support = await _get_anchor_discovery_service(app_context).discover_asset(asset)
        if support is None or support.web_auth_endpoint is None:
            await send_message(
                session,
                callback,
                _t(callback.from_user.id, "sep10_unavailable", app_context),
                app_context=app_context,
            )
            await callback.answer()
            return
        try:
            request_xdr = await _get_anchor_transaction_service(
                app_context
            ).get_sep10_challenge_xdr(support, wallet.public_key)
        except Exception as exc:  # noqa: BLE001 - never leave the spinner hanging
            logger.warning(f"SEP-10 challenge fetch failed: {exc}")
            await send_message(
                session,
                callback,
                _t(callback.from_user.id, "sep10_challenge_error", app_context),
                app_context=app_context,
            )
            await callback.answer()
            return
        fsm_func = _show_asset_requests_after_webapp_sep10

    prompt = _t(
        callback.from_user.id,
        "sep_requests_sign_prompt",
        app_context,
        (asset.code,),
    )
    await state.update_data(
        anchor_request_asset=asset.to_string(),
        anchor_request_key=callback_data.key,
        fsm_func=jsonpickle.dumps(fsm_func),
        operation=f"SEP requests for {asset.code}",
        sign_msg=my_gettext(
            callback,
            "sign_sep10_msg",
            (asset.code,),
            app_context=app_context,
        ),
        msg=prompt,
    )

    signing_facade = getattr(app_context, "signing_facade", None) or SigningFacade()
    await signing_facade.request_signature(
        session=session,
        state=state,
        request=SignatureRequest(
            user_id=callback.from_user.id,
            wallet_address=wallet.public_key if wallet else "",
            xdr=request_xdr,
            purpose=SignaturePurpose.SEP10_AUTH,
            mode=SignatureMode.SIGN_ONLY,
            operation=f"SEP requests for {asset.code}",
            sign_msg=my_gettext(
                callback,
                "sign_sep10_msg",
                (asset.code,),
                app_context=app_context,
            ),
            prompt_msg=prompt,
            fsm_func=jsonpickle.dumps(fsm_func),
            metadata={"asset": asset.to_string(), "action": "requests"},
        ),
        app_context=app_context,
    )
    await callback.answer()


@router.callback_query(AssetAction.filter(F.action.in_({"deposit", "withdraw"})))
async def cmd_asset_transfer(
    callback: types.CallbackQuery,
    callback_data: AssetAction,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if callback.from_user is None:
        return

    asset = await _asset_from_state(state, callback_data.key)
    if asset is None:
        await callback.answer(
            _t(callback.from_user.id, "sep_assets_expired", app_context),
            show_alert=True,
        )
        return

    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    fsm_func = _show_sep24_interactive_after_pin
    request_xdr = ""
    if wallet and wallet.use_pin == 10:
        support = await _get_anchor_discovery_service(app_context).discover_asset(asset)
        if (
            support is None
            or support.sep24 is None
            or support.web_auth_endpoint is None
        ):
            await send_message(
                session,
                callback,
                _t(callback.from_user.id, "sep24_unavailable", app_context),
                app_context=app_context,
            )
            await callback.answer()
            return
        try:
            request_xdr = await _get_anchor_transaction_service(
                app_context
            ).get_sep10_challenge_xdr(support, wallet.public_key)
        except Exception as exc:  # noqa: BLE001 - never leave the spinner hanging
            logger.warning(f"SEP-10 challenge fetch failed: {exc}")
            await send_message(
                session,
                callback,
                _t(callback.from_user.id, "sep10_challenge_error", app_context),
                app_context=app_context,
            )
            await callback.answer()
            return
        fsm_func = _show_sep24_interactive_after_webapp_sep10

    prompt = _t(
        callback.from_user.id,
        "sep24_sign_prompt",
        app_context,
        (
            asset.code,
            _operation_label(callback_data.action, app_context, callback.from_user.id),
        ),
    )
    await state.update_data(
        anchor_transfer_asset=asset.to_string(),
        anchor_transfer_key=callback_data.key,
        anchor_transfer_operation=callback_data.action,
        fsm_func=jsonpickle.dumps(fsm_func),
        operation=f"SEP-24 {callback_data.action} for {asset.code}",
        sign_msg=my_gettext(
            callback,
            "sign_sep10_msg",
            (asset.code,),
            app_context=app_context,
        ),
        msg=prompt,
    )

    signing_facade = getattr(app_context, "signing_facade", None) or SigningFacade()
    await signing_facade.request_signature(
        session=session,
        state=state,
        request=SignatureRequest(
            user_id=callback.from_user.id,
            wallet_address=wallet.public_key if wallet else "",
            xdr=request_xdr,
            purpose=SignaturePurpose.SEP10_AUTH,
            mode=SignatureMode.SIGN_ONLY,
            operation=f"SEP-24 {callback_data.action} for {asset.code}",
            sign_msg=my_gettext(
                callback,
                "sign_sep10_msg",
                (asset.code,),
                app_context=app_context,
            ),
            prompt_msg=prompt,
            fsm_func=jsonpickle.dumps(fsm_func),
            metadata={"asset": asset.to_string(), "action": callback_data.action},
        ),
        app_context=app_context,
    )
    await callback.answer()


async def _missing_trustline(
    app_context: AppContext, public_key: str, asset: Asset
) -> bool:
    """True when the wallet cannot receive `asset` (deposit would fail)."""
    if asset.issuer is None:
        # Native XLM needs no trustline; the SEP flow only lists issued assets.
        return False
    try:
        details = await app_context.stellar_service.get_account_details(public_key)
    except Exception:  # noqa: BLE001 - a warning is best effort
        return False
    if not details:
        return False
    for balance in details.get("balances", []):
        if (
            balance.get("asset_code") == asset.code
            and balance.get("asset_issuer") == asset.issuer
        ):
            return False
    return True


def _format_sep24_status(
    view: Sep24TransactionView,
    support: AnchorAssetSupport,
    *,
    user_id: int,
    app_context: AppContext,
    trustline_missing: bool = False,
) -> str:
    lines = [
        f"<b>{escape(support.asset.code)}</b>",
        _t(
            user_id,
            "sep24_status_line",
            app_context,
            (_t(user_id, view.status_i18n_key, app_context),),
        ),
    ]
    if view.kind:
        lines.append(
            _t(user_id, "sep24_status_kind", app_context, (escape(view.kind),))
        )
    if view.id:
        lines.append(_t(user_id, "sep24_status_id", app_context, (escape(view.id),)))
    if view.amount_in:
        lines.append(
            _t(
                user_id,
                "sep24_status_amount_in",
                app_context,
                (escape(view.amount_in),),
            )
        )
    if view.amount_out:
        lines.append(
            _t(
                user_id,
                "sep24_status_amount_out",
                app_context,
                (escape(view.amount_out),),
            )
        )
    if view.amount_fee:
        lines.append(
            _t(user_id, "sep24_status_fee", app_context, (escape(view.amount_fee),))
        )
    if trustline_missing:
        lines.append(
            _t(
                user_id,
                "sep24_status_trustline_missing",
                app_context,
                (escape(support.asset.code),),
            )
        )
    if view.message:
        lines.append(escape(view.message))
    instructions = view.instructions
    # Only ask for a payment while the anchor actually waits for one: anchors
    # keep the addresses in the payload after the transaction is closed.
    if (
        instructions is not None
        and instructions.destination
        and awaits_user_transfer(view.status)
    ):
        amount = instructions.amount or view.amount_in or ""
        asset_label = instructions.asset_code or support.asset.code
        if amount:
            lines.append(
                _t(
                    user_id,
                    "sep24_status_pay_to",
                    app_context,
                    (
                        escape(amount),
                        escape(asset_label),
                        escape(instructions.destination),
                    ),
                )
            )
        else:
            lines.append(
                _t(
                    user_id,
                    "sep24_status_pay_to_no_amount",
                    app_context,
                    (escape(asset_label), escape(instructions.destination)),
                )
            )
        if instructions.memo:
            lines.append(
                _t(
                    user_id,
                    "sep24_status_pay_memo",
                    app_context,
                    (
                        escape(instructions.memo_type or "text"),
                        escape(instructions.memo),
                    ),
                )
            )
        if instructions.is_muxed:
            lines.append(_t(user_id, "sep24_status_muxed_hint", app_context))
    if view.more_info_url:
        lines.append(
            _t(
                user_id,
                "sep24_status_more_info",
                app_context,
                (escape(view.more_info_url, quote=True),),
            )
        )
    return "\n".join(lines).strip()


@router.callback_query(
    F.data.in_({SEP24_STATUS_CALLBACK, SEP24_STATUS_REFRESH_CALLBACK})
)
async def cmd_sep24_status(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    """Show the anchor status and payment instructions for the stored transfer."""
    if callback.from_user is None:
        return
    user_id = callback.from_user.id
    data = await state.get_data()
    asset_ref = data.get("anchor_transfer_asset")
    operation = data.get("anchor_transfer_operation")
    asset_key = data.get("anchor_transfer_key")
    transaction_id = data.get("anchor_transfer_id")
    anchor_url = data.get("anchor_transfer_url")

    if (
        not isinstance(asset_ref, str)
        or ":" not in asset_ref
        or not isinstance(transaction_id, str)
        or not transaction_id
    ):
        await send_message(
            session,
            callback,
            _t(user_id, "sep24_status_unavailable", app_context),
            reply_markup=sep24_status_keyboard(
                user_id, refresh=False, app_context=app_context
            ),
            app_context=app_context,
        )
        await callback.answer()
        return

    code, issuer = asset_ref.split(":", 1)
    asset = Asset(code, issuer)
    support = await _get_anchor_discovery_service(app_context).discover_asset(asset)
    if support is None or support.sep24 is None:
        await send_message(
            session,
            callback,
            _t(user_id, "sep24_status_unavailable", app_context),
            reply_markup=sep24_status_keyboard(
                user_id, refresh=False, app_context=app_context
            ),
            app_context=app_context,
        )
        await callback.answer()
        return

    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(user_id)
    reauth_callback = (
        AssetAction(action=str(operation), key=str(asset_key)).pack()
        if operation in {"deposit", "withdraw"} and asset_key
        else None
    )

    try:
        view = await _get_anchor_transaction_service(
            app_context
        ).fetch_sep24_transaction_cached(
            support,
            transaction_id=transaction_id,
            user_id=user_id,
            public_key=wallet.public_key if wallet else "",
            lang=await _lang_hint(user_id, app_context),
        )
    except Sep24ReauthRequired:
        await send_message(
            session,
            callback,
            _t(user_id, "sep24_status_reauth", app_context),
            reply_markup=sep24_status_keyboard(
                user_id,
                url=anchor_url if isinstance(anchor_url, str) else None,
                reauth_callback=reauth_callback,
                app_context=app_context,
            ),
            app_context=app_context,
        )
        await callback.answer()
        return
    except Exception as exc:  # noqa: BLE001 - surface anchor errors
        await send_message(
            session,
            callback,
            _t(
                user_id,
                "sep24_status_fetch_error",
                app_context,
                (escape(str(exc)),),
            ),
            reply_markup=sep24_status_keyboard(
                user_id,
                url=anchor_url if isinstance(anchor_url, str) else None,
                app_context=app_context,
            ),
            app_context=app_context,
        )
        await callback.answer()
        return

    trustline_missing = False
    if operation == "deposit" and wallet is not None:
        trustline_missing = await _missing_trustline(
            app_context, wallet.public_key, asset
        )

    await send_message(
        session,
        callback,
        _format_sep24_status(
            view,
            support,
            user_id=user_id,
            app_context=app_context,
            trustline_missing=trustline_missing,
        ),
        reply_markup=sep24_status_keyboard(
            user_id,
            url=anchor_url if isinstance(anchor_url, str) else None,
            app_context=app_context,
        ),
        app_context=app_context,
    )
    await callback.answer()


def _get_anchor_discovery_service(app_context: AppContext) -> AnchorDiscoveryService:
    service = getattr(app_context, "anchor_discovery_service", None)
    if service is not None:
        return service
    return _anchor_discovery_service


def _get_anchor_transaction_service(
    app_context: AppContext,
) -> AnchorTransactionService:
    service = getattr(app_context, "anchor_transaction_service", None)
    if service is not None:
        return service
    return _anchor_transaction_service


async def _asset_from_state(state: FSMContext, key: str) -> Asset | None:
    data = await state.get_data()
    asset_map = data.get("anchor_assets", {})
    asset_ref = asset_map.get(key)
    if not isinstance(asset_ref, str):
        return None
    if ":" not in asset_ref:
        return None
    code, issuer = asset_ref.split(":", 1)
    if not code or not issuer:
        return None
    return Asset(code, issuer)


async def _show_asset_requests_after_pin(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    *,
    app_context: AppContext,
):
    data = await state.get_data()
    asset_ref = data.get("anchor_request_asset")
    asset_key = data.get("anchor_request_key", "a0")
    pin = data.get("pin", "")
    if not isinstance(asset_ref, str) or ":" not in asset_ref:
        await send_message(
            session,
            user_id,
            _t(user_id, "sep_assets_expired", app_context),
            app_context=app_context,
        )
        return

    code, issuer = asset_ref.split(":", 1)
    asset = Asset(code, issuer)
    support = await _get_anchor_discovery_service(app_context).discover_asset(asset)
    if support is None:
        await send_message(
            session,
            user_id,
            _t(user_id, "sep_support_unavailable", app_context),
            app_context=app_context,
        )
        return

    keypair = await app_context.stellar_service.get_user_keypair(session, user_id, pin)
    try:
        transactions = await _get_anchor_transaction_service(
            app_context
        ).fetch_transactions(support, keypair, user_id=user_id)
    except Exception as exc:
        await send_message(
            session,
            user_id,
            _t(user_id, "sep_requests_error", app_context, (escape(str(exc)),)),
            app_context=app_context,
        )
        return

    await send_message(
        session,
        user_id,
        _format_asset_transactions(
            support.asset.code, transactions, user_id=user_id, app_context=app_context
        ),
        reply_markup=asset_actions_keyboard(
            str(asset_key),
            user_id,
            app_context=app_context,
        ),
        app_context=app_context,
    )


async def _show_sep24_interactive_after_pin(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    *,
    app_context: AppContext,
):
    data = await state.get_data()
    asset_ref = data.get("anchor_transfer_asset")
    operation = data.get("anchor_transfer_operation")
    pin = data.get("pin", "")
    if (
        not isinstance(asset_ref, str)
        or ":" not in asset_ref
        or operation not in {"deposit", "withdraw"}
    ):
        await send_message(
            session,
            user_id,
            _t(user_id, "sep_assets_expired", app_context),
            app_context=app_context,
        )
        return

    code, issuer = asset_ref.split(":", 1)
    asset = Asset(code, issuer)
    support = await _get_anchor_discovery_service(app_context).discover_asset(asset)
    if support is None or support.sep24 is None:
        await send_message(
            session,
            user_id,
            _t(user_id, "sep24_unavailable", app_context),
            app_context=app_context,
        )
        return

    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(user_id)
    keypair = await app_context.stellar_service.get_user_keypair(session, user_id, pin)
    operation_label = _operation_label(operation, app_context, user_id)
    try:
        session_result = await _get_anchor_transaction_service(
            app_context
        ).start_sep24_interactive(
            support,
            keypair,
            operation=operation,
            account=wallet.public_key if wallet else keypair.public_key,
            lang=await _lang_hint(user_id, app_context),
            user_id=user_id,
        )
    except Exception as exc:
        await send_message(
            session,
            user_id,
            _anchor_error_text(exc, user_id, operation_label, app_context),
            app_context=app_context,
        )
        return

    await _render_sep24_ready(
        session,
        user_id,
        state,
        support=support,
        session_result=session_result,
        operation_label=operation_label,
        app_context=app_context,
    )


async def _get_sep10_webapp_token(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    asset_ref: str,
    *,
    app_context: AppContext,
) -> tuple[AnchorAssetSupport, str] | None:
    data = await state.get_data()
    signed_xdr = data.get("sep10_signed_xdr")
    if not isinstance(signed_xdr, str) or not signed_xdr:
        await send_message(
            session,
            user_id,
            _t(user_id, "sep10_sig_missing", app_context),
            app_context=app_context,
        )
        return None

    code, issuer = asset_ref.split(":", 1)
    asset = Asset(code, issuer)
    support = await _get_anchor_discovery_service(app_context).discover_asset(asset)
    if support is None or support.web_auth_endpoint is None:
        await send_message(
            session,
            user_id,
            _t(user_id, "sep10_unavailable", app_context),
            app_context=app_context,
        )
        return None

    service = _get_anchor_transaction_service(app_context)
    token = await service.exchange_sep10_token(
        support.web_auth_endpoint,
        signed_xdr,
    )
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(user_id)
    if wallet is not None:
        await service.remember_sep10_token(
            support,
            token,
            user_id=user_id,
            public_key=wallet.public_key,
        )
    return support, token


async def _show_asset_requests_after_webapp_sep10(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    *,
    app_context: AppContext,
):
    data = await state.get_data()
    asset_ref = data.get("anchor_request_asset")
    asset_key = data.get("anchor_request_key", "a0")
    if not isinstance(asset_ref, str) or ":" not in asset_ref:
        await send_message(
            session,
            user_id,
            _t(user_id, "sep_assets_expired", app_context),
            app_context=app_context,
        )
        return

    try:
        auth = await _get_sep10_webapp_token(
            session,
            user_id,
            state,
            asset_ref,
            app_context=app_context,
        )
        if auth is None:
            return
        support, token = auth
        transactions = await _get_anchor_transaction_service(
            app_context
        ).fetch_transactions_with_token(support, token)
    except Exception as exc:
        await send_message(
            session,
            user_id,
            _t(user_id, "sep_requests_error", app_context, (escape(str(exc)),)),
            app_context=app_context,
        )
        return

    await send_message(
        session,
        user_id,
        _format_asset_transactions(
            support.asset.code, transactions, user_id=user_id, app_context=app_context
        ),
        reply_markup=asset_actions_keyboard(
            str(asset_key),
            user_id,
            app_context=app_context,
        ),
        app_context=app_context,
    )


async def _show_sep24_interactive_after_webapp_sep10(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    *,
    app_context: AppContext,
):
    data = await state.get_data()
    asset_ref = data.get("anchor_transfer_asset")
    operation = data.get("anchor_transfer_operation")
    if (
        not isinstance(asset_ref, str)
        or ":" not in asset_ref
        or operation not in {"deposit", "withdraw"}
    ):
        await send_message(
            session,
            user_id,
            _t(user_id, "sep_assets_expired", app_context),
            app_context=app_context,
        )
        return

    operation_label = _operation_label(operation, app_context, user_id)
    try:
        auth = await _get_sep10_webapp_token(
            session,
            user_id,
            state,
            asset_ref,
            app_context=app_context,
        )
        if auth is None:
            return
        support, token = auth
        if support.sep24 is None:
            await send_message(
                session,
                user_id,
                _t(user_id, "sep24_unavailable", app_context),
                app_context=app_context,
            )
            return
        wallet_repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await wallet_repo.get_default_wallet(user_id)
        session_result = await _get_anchor_transaction_service(
            app_context
        ).start_sep24_interactive_with_token(
            support,
            token,
            operation=operation,
            account=wallet.public_key if wallet else "",
            lang=await _lang_hint(user_id, app_context),
        )
    except Exception as exc:
        await send_message(
            session,
            user_id,
            _anchor_error_text(exc, user_id, operation_label, app_context),
            app_context=app_context,
        )
        return

    await _render_sep24_ready(
        session,
        user_id,
        state,
        support=support,
        session_result=session_result,
        operation_label=operation_label,
        app_context=app_context,
    )


def _anchor_error_text(
    exc: Exception, user_id, operation_label: str, app_context: AppContext
) -> str:
    """Localized anchor error: known codes get their own wording."""
    body = getattr(exc, "body", None)
    error_code = body.get("error") if isinstance(body, dict) else None
    known_key = sep24_known_error_i18n_key(error_code)
    if known_key:
        detail = _t(user_id, known_key, app_context)
    elif error_code:
        # Anchors put the human-readable reason into `error`; show it verbatim.
        detail = escape(str(error_code))
    else:
        detail = escape(str(exc))
    return _t(
        user_id,
        "sep24_start_error",
        app_context,
        (operation_label, detail),
    )


async def _render_sep24_ready(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    *,
    support: AnchorAssetSupport,
    session_result,
    operation_label: str,
    app_context: AppContext,
) -> None:
    """Show the interactive link, keeping the transaction id for later reads."""
    await state.update_data(
        anchor_transfer_url=session_result.url,
        anchor_transfer_id=session_result.transaction_id,
        anchor_transfer_type=session_result.kind,
    )
    text = "\n\n".join(
        (
            _t(
                user_id,
                "sep24_ready",
                app_context,
                (escape(support.asset.code), escape(operation_label)),
            ),
            _t(user_id, "sep_assets_disclaimer", app_context),
        )
    )
    await send_message(
        session,
        user_id,
        text,
        reply_markup=sep24_interactive_keyboard(
            user_id,
            session_result.url,
            app_context=app_context,
        ),
        app_context=app_context,
    )


def _format_asset_support(
    support: AnchorAssetSupport,
    *,
    user_id: int,
    app_context: AppContext,
) -> str:
    lines = [
        f"<b>{support.asset.code}</b>",
        _t(user_id, "sep_asset_anchor", app_context, (support.anchor_domain,)),
        "",
    ]
    if support.sep6:
        lines.extend(_format_protocol("SEP-6", support.sep6, user_id, app_context))
    if support.sep24:
        lines.extend(_format_protocol("SEP-24", support.sep24, user_id, app_context))
    return "\n".join(lines).strip()


def _format_asset_transactions(
    asset_code: str,
    transactions: list[AnchorTransaction],
    *,
    user_id: int,
    app_context: AppContext,
) -> str:
    if not transactions:
        return "\n".join(
            (
                f"<b>{asset_code}</b>",
                _t(user_id, "sep_requests_empty", app_context),
            )
        )

    lines = [
        f"<b>{asset_code}</b>",
        _t(user_id, "sep_requests_title", app_context),
        "",
    ]
    for tx in transactions[:10]:
        parts = [tx.protocol.value]
        if tx.kind:
            parts.append(escape(tx.kind))
        if tx.status:
            parts.append(_t(user_id, sep24_status_i18n_key(tx.status), app_context))
        lines.append(" / ".join(parts))
        lines.append(_t(user_id, "sep_tx_id", app_context, (escape(tx.id),)))
        amount = tx.amount_in or tx.amount_out
        if amount:
            lines.append(_t(user_id, "sep_tx_amount", app_context, (escape(amount),)))
        date_value = tx.updated_at or tx.completed_at or tx.started_at
        if date_value:
            lines.append(_t(user_id, "sep_tx_date", app_context, (escape(date_value),)))
        if tx.more_info_url:
            lines.append(
                _t(
                    user_id,
                    "sep_tx_more_info",
                    app_context,
                    (escape(tx.more_info_url, quote=True),),
                )
            )
        lines.append("")
    return "\n".join(lines).strip()


def _format_protocol(
    title: str,
    protocol: SepProtocolSupport,
    user_id: int,
    app_context: AppContext,
) -> list[str]:
    lines = [title]
    if protocol.deposit:
        lines.append(
            _t(
                user_id,
                "sep_asset_deposit_line",
                app_context,
                (_format_operation(protocol.deposit),),
            )
        )
    if protocol.withdraw:
        lines.append(
            _t(
                user_id,
                "sep_asset_withdraw_line",
                app_context,
                (_format_operation(protocol.withdraw),),
            )
        )
    if protocol.transactions_enabled:
        lines.append(_t(user_id, "sep_asset_requests_available", app_context))
    lines.append("")
    return lines


def _format_operation(operation: SepOperationSupport) -> str:
    parts = []
    if operation.min_amount is not None:
        parts.append(f"min {operation.min_amount:g}")
    if operation.max_amount is not None:
        parts.append(f"max {operation.max_amount:g}")
    if operation.fee_fixed is not None:
        parts.append(f"fee {operation.fee_fixed:g}")
    if operation.fee_percent is not None:
        parts.append(f"fee {operation.fee_percent:g}%")
    return ", ".join(parts) if parts else "available"

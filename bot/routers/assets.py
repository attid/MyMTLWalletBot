from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from html import escape
import jsonpickle  # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.value_objects import Asset
from core.models.anchor_asset import (
    AnchorAssetSupport,
    SepOperationSupport,
    SepProtocolSupport,
)
from core.models.anchor_transaction import AnchorTransaction
from infrastructure.services.anchor_discovery_service import AnchorDiscoveryService
from infrastructure.services.anchor_transaction_service import AnchorTransactionService
from infrastructure.services.app_context import AppContext
from infrastructure.utils.telegram_utils import (
    clear_last_message_id,
    clear_state,
    send_message,
)
from keyboards.assets import (
    AssetAction,
    asset_actions_keyboard,
    assets_list_keyboard,
    sep24_interactive_keyboard,
)

router = Router()
router.message.filter(F.chat.type == "private")

_anchor_discovery_service = AnchorDiscoveryService()
_anchor_transaction_service = AnchorTransactionService()


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
    supported_assets = await discovery.discover_assets(assets)
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
            "SEP assets were not found for this wallet.",
            app_context=app_context,
        )
        return

    await send_message(
        session,
        message,
        "SEP assets",
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
        await callback.answer("Asset selection expired", show_alert=True)
        return

    support = await _get_anchor_discovery_service(app_context).discover_asset(asset)
    if support is None:
        await callback.answer("SEP support is not available", show_alert=True)
        return

    await send_message(
        session,
        callback,
        _format_asset_support(support),
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
        await callback.answer("Asset selection expired", show_alert=True)
        return

    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    if wallet and wallet.use_pin == 10:
        await send_message(
            session,
            callback,
            "Requests require SEP-10 signing. WebApp signing is not enabled for this flow yet.",
            app_context=app_context,
        )
        await callback.answer()
        return

    await state.update_data(
        anchor_request_asset=asset.to_string(),
        anchor_request_key=callback_data.key,
        fsm_func=jsonpickle.dumps(_show_asset_requests_after_pin),
        operation=f"SEP requests for {asset.code}",
        msg=f"Sign SEP-10 challenge to show {asset.code} requests.",
    )

    from routers.sign import PinState, cmd_ask_pin

    await state.set_state(PinState.sign)
    await cmd_ask_pin(session, callback.from_user.id, state, app_context=app_context)
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
        await callback.answer("Asset selection expired", show_alert=True)
        return

    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    if wallet and wallet.use_pin == 10:
        await send_message(
            session,
            callback,
            "SEP-24 transfer requires SEP-10 signing. WebApp signing is not enabled for this flow yet.",
            app_context=app_context,
        )
        await callback.answer()
        return

    await state.update_data(
        anchor_transfer_asset=asset.to_string(),
        anchor_transfer_key=callback_data.key,
        anchor_transfer_operation=callback_data.action,
        fsm_func=jsonpickle.dumps(_show_sep24_interactive_after_pin),
        operation=f"SEP-24 {callback_data.action} for {asset.code}",
        msg=f"Sign SEP-10 challenge to start {asset.code} {callback_data.action}.",
    )

    from routers.sign import PinState, cmd_ask_pin

    await state.set_state(PinState.sign)
    await cmd_ask_pin(session, callback.from_user.id, state, app_context=app_context)
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
            "Asset selection expired.",
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
            "SEP support is not available.",
            app_context=app_context,
        )
        return

    keypair = await app_context.stellar_service.get_user_keypair(session, user_id, pin)
    try:
        transactions = await _get_anchor_transaction_service(
            app_context
        ).fetch_transactions(support, keypair)
    except Exception as exc:
        await send_message(
            session,
            user_id,
            f"Could not load requests.\n{escape(str(exc))}",
            app_context=app_context,
        )
        return

    await send_message(
        session,
        user_id,
        _format_asset_transactions(support.asset.code, transactions),
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
            "Asset selection expired.",
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
            "SEP-24 is not available for this asset.",
            app_context=app_context,
        )
        return

    keypair = await app_context.stellar_service.get_user_keypair(session, user_id, pin)
    try:
        url = await _get_anchor_transaction_service(
            app_context
        ).start_sep24_interactive(support, keypair, operation=operation)
    except Exception as exc:
        await send_message(
            session,
            user_id,
            f"Could not start SEP-24 {operation}.\n{escape(str(exc))}",
            app_context=app_context,
        )
        return

    await send_message(
        session,
        user_id,
        f"<b>{support.asset.code}</b>\nSEP-24 {escape(str(operation))} is ready.",
        reply_markup=sep24_interactive_keyboard(
            user_id,
            url,
            app_context=app_context,
        ),
        app_context=app_context,
    )


def _format_asset_support(support: AnchorAssetSupport) -> str:
    lines = [
        f"<b>{support.asset.code}</b>",
        f"Anchor: {support.anchor_domain}",
        "",
    ]
    if support.sep6:
        lines.extend(_format_protocol("SEP-6", support.sep6))
    if support.sep24:
        lines.extend(_format_protocol("SEP-24", support.sep24))
    return "\n".join(lines).strip()


def _format_asset_transactions(
    asset_code: str,
    transactions: list[AnchorTransaction],
) -> str:
    if not transactions:
        return f"<b>{asset_code}</b>\nRequests were not found."

    lines = [f"<b>{asset_code}</b>", "Requests", ""]
    for tx in transactions[:10]:
        parts = [tx.protocol.value]
        if tx.kind:
            parts.append(escape(tx.kind))
        if tx.status:
            parts.append(escape(tx.status))
        lines.append(" / ".join(parts))
        lines.append(f"ID: <code>{escape(tx.id)}</code>")
        amount = tx.amount_in or tx.amount_out
        if amount:
            lines.append(f"Amount: {escape(amount)}")
        date_value = tx.updated_at or tx.completed_at or tx.started_at
        if date_value:
            lines.append(f"Date: {escape(date_value)}")
        if tx.more_info_url:
            lines.append(
                f'<a href="{escape(tx.more_info_url, quote=True)}">More info</a>'
            )
        lines.append("")
    return "\n".join(lines).strip()


def _format_protocol(title: str, protocol: SepProtocolSupport) -> list[str]:
    lines = [title]
    if protocol.deposit:
        lines.append("Deposit: " + _format_operation(protocol.deposit))
    if protocol.withdraw:
        lines.append("Withdraw: " + _format_operation(protocol.withdraw))
    if protocol.transactions_enabled:
        lines.append("Requests: available")
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

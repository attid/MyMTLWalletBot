from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.value_objects import Asset
from core.models.anchor_asset import (
    AnchorAssetSupport,
    SepOperationSupport,
    SepProtocolSupport,
)
from infrastructure.services.anchor_discovery_service import AnchorDiscoveryService
from infrastructure.services.app_context import AppContext
from infrastructure.utils.telegram_utils import send_message
from keyboards.assets import AssetAction, asset_actions_keyboard, assets_list_keyboard

router = Router()
router.message.filter(F.chat.type == "private")

_anchor_discovery_service = AnchorDiscoveryService()


@router.message(Command(commands=["assets"]))
async def cmd_assets(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None:
        return

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


@router.callback_query(
    AssetAction.filter(F.action.in_({"requests", "deposit", "withdraw"}))
)
async def cmd_asset_action_placeholder(
    callback: types.CallbackQuery,
    callback_data: AssetAction,
    session: AsyncSession,
    app_context: AppContext,
):
    if callback.from_user is None:
        return
    action_title = {
        "requests": "Requests",
        "deposit": "Deposit",
        "withdraw": "Withdraw",
    }[callback_data.action]
    await send_message(
        session,
        callback,
        f"{action_title} flow is not enabled yet.",
        app_context=app_context,
    )
    await callback.answer()


def _get_anchor_discovery_service(app_context: AppContext) -> AnchorDiscoveryService:
    service = getattr(app_context, "anchor_discovery_service", None)
    if service is not None:
        return service
    return _anchor_discovery_service


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

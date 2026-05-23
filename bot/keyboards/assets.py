from aiogram import types
from aiogram.filters.callback_data import CallbackData

from core.models.anchor_asset import AnchorAssetSupport
from infrastructure.services.app_context import AppContext
from keyboards.common_keyboards import get_return_button


class AssetAction(CallbackData, prefix="asset"):
    action: str
    key: str


def assets_list_keyboard(
    assets: list[AnchorAssetSupport],
    user_id: int,
    *,
    app_context: AppContext,
) -> types.InlineKeyboardMarkup:
    buttons = [
        [
            types.InlineKeyboardButton(
                text=f"{support.asset.code} ({support.anchor_domain})",
                callback_data=AssetAction(action="view", key=f"a{idx}").pack(),
            )
        ]
        for idx, support in enumerate(assets)
    ]
    buttons.append(get_return_button(user_id, app_context=app_context))
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def asset_actions_keyboard(
    key: str,
    user_id: int,
    *,
    app_context: AppContext,
) -> types.InlineKeyboardMarkup:
    buttons = [
        [
            types.InlineKeyboardButton(
                text="Requests",
                callback_data=AssetAction(action="requests", key=key).pack(),
            ),
            types.InlineKeyboardButton(
                text="Deposit",
                callback_data=AssetAction(action="deposit", key=key).pack(),
            ),
            types.InlineKeyboardButton(
                text="Withdraw",
                callback_data=AssetAction(action="withdraw", key=key).pack(),
            ),
        ],
        get_return_button(user_id, app_context=app_context),
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def sep24_interactive_keyboard(
    user_id: int,
    url: str,
    *,
    app_context: AppContext,
) -> types.InlineKeyboardMarkup:
    buttons = [
        [types.InlineKeyboardButton(text="Open", url=url)],
        get_return_button(user_id, app_context=app_context),
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

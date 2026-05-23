from aiogram import types
from aiogram.filters.callback_data import CallbackData

from core.models.anchor_asset import AnchorAssetSupport
from keyboards.common_keyboards import get_return_button


class AssetAction(CallbackData, prefix="asset"):
    action: str
    key: str


def assets_list_keyboard(
    assets: list[AnchorAssetSupport],
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
    buttons.append(get_return_button(0))
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def asset_actions_keyboard(key: str) -> types.InlineKeyboardMarkup:
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
        get_return_button(0),
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

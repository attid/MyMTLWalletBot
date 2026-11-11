from aiogram import types
from aiogram.filters.callback_data import CallbackData

from core.models.anchor_asset import AnchorAssetSupport
from infrastructure.services.app_context import AppContext
from keyboards.common_keyboards import get_return_button
from other.lang_tools import my_gettext

SEP24_STATUS_CALLBACK = "Sep24Status"
SEP24_STATUS_REFRESH_CALLBACK = "Sep24StatusRefresh"


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
        [
            types.InlineKeyboardButton(
                text=my_gettext(user_id, "kb_sep24_open", app_context=app_context),
                url=url,
            )
        ],
        [
            types.InlineKeyboardButton(
                text=my_gettext(user_id, "kb_sep24_status", app_context=app_context),
                callback_data=SEP24_STATUS_CALLBACK,
            )
        ],
        get_return_button(user_id, app_context=app_context),
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def sep24_status_keyboard(
    user_id: int,
    *,
    url: str | None = None,
    reauth_callback: str | None = None,
    refresh: bool = True,
    app_context: AppContext,
) -> types.InlineKeyboardMarkup:
    """Status screen actions: anchor page, refresh, optional re-authorization."""
    buttons: list[list[types.InlineKeyboardButton]] = []
    if url:
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text=my_gettext(user_id, "kb_sep24_open", app_context=app_context),
                    url=url,
                )
            ]
        )
    if refresh:
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text=my_gettext(
                        user_id, "kb_sep24_refresh", app_context=app_context
                    ),
                    callback_data=SEP24_STATUS_REFRESH_CALLBACK,
                )
            ]
        )
    if reauth_callback:
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text=my_gettext(
                        user_id, "kb_sep24_reauth", app_context=app_context
                    ),
                    callback_data=reauth_callback,
                )
            ]
        )
    buttons.append(get_return_button(user_id, app_context=app_context))
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

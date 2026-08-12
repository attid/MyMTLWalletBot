"""Classify interactive Telegram events for delayed notification holds."""

from collections.abc import Awaitable, Callable
import inspect
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject


FLOW_ENTRY_CALLBACKS = frozenset(
    {
        "Send",
        "Yes_send_xdr",
        "Market",
        "NewOrder",
        "ShowOrders",
        "WalletSetting",
        "ManageAssetsMenu",
        "AssetVisibilityMenu",
        "DeleteAsset",
        "AddAsset",
        "AddAssetExpert",
        "AddressBook",
        "ManageData",
        "ChangeWallet",
        "ChangeLang",
        "NotificationSettings",
        "add_filter_menu",
        "toggle_token_notify",
        "change_amount",
        "toggle_wallets_notify",
        "SealedBoxMenu",
        "SealedBoxEncrypt",
        "SealedBoxDecrypt",
    }
)
"""Menu controls that begin a user-operated flow even without FSM state."""

FLOW_CALLBACK_PREFIXES = (
    "send_asset_:",
    "SaleAssetCallbackData:",
    "BuyAssetCallbackData:",
    "EditOrderCallbackData:",
    "AssetVisibilityCallbackData:",
    "DelAssetCallbackData:",
    "AddAssetCallbackData:",
    "AddressBookCallbackData:",
    "MDCallbackData:",
    "lang_:",
    "notif_menu:",
    "notif_filter:",
    "create_filter_from:",
    "AVD_:",
    "SealedBoxRecipient:",
)
"""CallbackData namespaces that advance an interactive flow."""

EXCLUDED_CALLBACKS = frozenset(
    {
        "notification_pending:flush",
        "Return",
        "DeleteReturn",
        "ReSend",
        "Refresh",
        "ShowMoreToggle",
        "SendTr",
        "SendTools",
        "cancel_import_key",
    }
)
"""Navigation, terminal, service, and non-flow controls that never extend a hold."""

EXCLUDED_CALLBACK_PREFIXES = ("cancel_biometric_sign:", "show_xdr_webapp:")

START_COMMAND = "/start"


def should_touch_callback(
    callback_data: str | None, *, fsm_active: bool = False
) -> bool:
    """Return whether a callback represents continued interactive activity."""
    if not callback_data:
        return False
    if callback_data in EXCLUDED_CALLBACKS or callback_data.startswith(
        EXCLUDED_CALLBACK_PREFIXES
    ):
        return False
    return (
        fsm_active
        or callback_data in FLOW_ENTRY_CALLBACKS
        or callback_data.startswith(FLOW_CALLBACK_PREFIXES)
    )


class NotificationActivityMiddleware(BaseMiddleware):
    """Extend notification holds only for user interaction that continues a flow."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        coordinator = _notification_coordinator(data.get("app_context"))
        user = getattr(event, "from_user", None)
        fsm_active = False
        if coordinator is not None and user is not None:
            fsm_active = await _has_active_state(data.get("state"))
            if (
                isinstance(event, Message)
                and fsm_active
                and not _is_start_command(event)
            ):
                await coordinator.touch(user.id)
            elif isinstance(event, CallbackQuery) and should_touch_callback(
                event.data, fsm_active=fsm_active
            ):
                await coordinator.touch(user.id)
        result = await handler(event, data)
        if (
            coordinator is not None
            and user is not None
            and isinstance(event, Message)
            and not fsm_active
            and not _is_plain_start_command(event)
            and await _has_active_state(data.get("state"))
        ):
            await coordinator.touch(user.id)
        return result


async def _has_active_state(state: FSMContext | None) -> bool:
    return state is not None and await state.get_state() is not None


def _is_start_command(message: Message) -> bool:
    """Keep a fresh `/start` flow from extending an abandoned FSM hold."""
    if not message.text:
        return False
    command = message.text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
    return command.lower() == START_COMMAND


def _is_plain_start_command(message: Message) -> bool:
    """Keep the terminal `/start` route completion-only after its handler runs."""
    return _is_start_command(message) and len(message.text.split()) == 1


async def complete_notification_flow(app_context: Any, user_id: int) -> None:
    """Best-effort terminal hook that keeps optional coordinator DI backwards-safe."""
    coordinator = _notification_coordinator(app_context)
    if coordinator is None:
        return
    completion = coordinator.complete_flow(user_id)
    if inspect.isawaitable(completion):
        await completion


def _notification_coordinator(app_context: Any) -> Any | None:
    """Read the explicitly configured optional dependency without mock magic."""
    return vars(app_context).get("notification_coordinator")

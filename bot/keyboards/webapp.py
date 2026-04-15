"""Keyboards for Web App integration (biometric signing)."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from other.config_reader import config
from keyboards.common_keyboards import get_return_button
from infrastructure.services.app_context import AppContext

_SUPPORTED_WEBAPP_LANGS = ("ru", "en")


def _resolve_webapp_lang(user_id: int | None, app_context: AppContext | None) -> str:
    if user_id is None or app_context is None:
        return "en"
    service = getattr(app_context, "localization_service", None)
    if service is None:
        return "en"
    try:
        lang = service.get_user_language(user_id)
    except Exception:
        return "en"
    return lang if lang in _SUPPORTED_WEBAPP_LANGS else "en"


def webapp_sign_keyboard(
    tx_id: str, user_id: int = None, app_context: AppContext = None
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопкой Web App для подписания транзакции.

    Args:
        tx_id: ID транзакции для подписания
        user_id: ID пользователя для локализации
        app_context: Контекст приложения

    Returns:
        InlineKeyboardMarkup с кнопкой Web App и кнопкой назад
    """
    webapp_url = getattr(config, "webapp_url", "https://webapp.example.com")
    lang = _resolve_webapp_lang(user_id, app_context)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Подписать",
                    web_app=WebAppInfo(
                        url=f"{webapp_url}/sign?tx={tx_id}&lang={lang}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 Показать XDR", callback_data=f"show_xdr_webapp:{tx_id}"
                )
            ],
            get_return_button(user_id, app_context=app_context),
        ]
    )


def webapp_import_key_keyboard(
    wallet_address: str, user_id: int = None, app_context: AppContext = None
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопкой Web App для импорта ключа.

    Args:
        wallet_address: Публичный адрес кошелька (GXXX...)
        user_id: ID пользователя для локализации
        app_context: Контекст приложения

    Returns:
        InlineKeyboardMarkup с кнопкой Web App и кнопкой назад
    """
    webapp_url = getattr(config, "webapp_url", "https://webapp.example.com")
    lang = _resolve_webapp_lang(user_id, app_context)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔑 Настроить подписание",
                    web_app=WebAppInfo(
                        url=f"{webapp_url}/import?address={wallet_address}&lang={lang}"
                    ),
                )
            ],
            get_return_button(user_id, app_context=app_context),
        ]
    )

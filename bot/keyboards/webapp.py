"""Keyboards for Web App integration (biometric signing)."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from other.config_reader import config


def webapp_sign_keyboard(tx_id: str) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопкой Web App для подписания транзакции.

    Args:
        tx_id: ID транзакции для подписания

    Returns:
        InlineKeyboardMarkup с кнопкой Web App и кнопкой отмены
    """
    webapp_url = getattr(config, 'webapp_url', 'https://webapp.example.com')

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✍️ Подписать",
            web_app=WebAppInfo(url=f"{webapp_url}/sign?tx={tx_id}")
        )],
        [InlineKeyboardButton(
            text="Отмена",
            callback_data=f"cancel_biometric_sign:{tx_id}"
        )]
    ])


def webapp_import_key_keyboard(wallet_address: str) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопкой Web App для импорта ключа.

    Args:
        wallet_address: Публичный адрес кошелька (GXXX...)

    Returns:
        InlineKeyboardMarkup с кнопкой Web App
    """
    webapp_url = getattr(config, 'webapp_url', 'https://webapp.example.com')

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔑 Настроить подписание",
            web_app=WebAppInfo(url=f"{webapp_url}/import?address={wallet_address}")
        )],
        [InlineKeyboardButton(
            text="Отмена",
            callback_data="cancel_import_key"
        )]
    ])

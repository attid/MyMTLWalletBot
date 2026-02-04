"""Helpers for transaction signing with support for biometric signing mode."""

from typing import Optional, Any
from aiogram.types import Message
from loguru import logger
from stellar_sdk import Transaction, TransactionEnvelope

from core.domain.entities import User, Wallet
from infrastructure.services.app_context import AppContext
from other.faststream_tools import publish_pending_tx
from keyboards.webapp import webapp_sign_keyboard
from other.config_reader import config


async def request_signature(
    user: User,
    wallet: Wallet,
    transaction: TransactionEnvelope,
    memo: str,
    app_context: AppContext,
    message: Message,
    sign_and_submit_callback: Any,
) -> Optional[dict]:
    """
    Универсальный метод запроса подписи транзакции.

    В зависимости от signing_mode кошелька:
    - 'server': Подписываем на сервере и отправляем (текущая логика)
    - 'local': Публикуем TX для подписания через Web App

    Args:
        user: Пользователь
        wallet: Кошелёк с signing_mode
        transaction: TransactionEnvelope для подписания
        memo: Описание транзакции для отображения пользователю
        app_context: Контекст приложения
        message: Telegram сообщение для ответа
        sign_and_submit_callback: Async функция для подписания на сервере
            Сигнатура: async def callback() -> dict

    Returns:
        - Для server mode: результат отправки транзакции
        - Для local mode: None (результат придёт через FastStream)
    """
    signing_mode = wallet.signing_mode

    if signing_mode == "server":
        # Текущая логика — подписываем на сервере
        logger.info(f"User {user.id}: signing TX on server")
        return await sign_and_submit_callback()

    elif signing_mode == "local":
        # Новая логика — Web App
        logger.info(f"User {user.id}: requesting local signing via Web App")

        # Получаем unsigned XDR
        unsigned_xdr = transaction.to_xdr()

        # Публикуем TX для подписания
        tx_id = await publish_pending_tx(
            user_id=user.id,
            wallet_address=wallet.public_key,
            unsigned_xdr=unsigned_xdr,
            memo=memo,
        )

        # Отправляем кнопку Web App
        from other.lang_tools import my_gettext
        text = my_gettext(user.id, 'biometric_sign_prompt', app_context=app_context)
        if text == 'biometric_sign_prompt':
            # Fallback if translation not found
            text = f"Подтвердите транзакцию:\n\n{memo}"

        await message.answer(
            text,
            reply_markup=webapp_sign_keyboard(tx_id),
        )

        # Результат придёт через FastStream
        return None

    else:
        logger.error(f"Unknown signing_mode: {signing_mode}")
        raise ValueError(f"Unknown signing_mode: {signing_mode}")


def is_local_signing(wallet: Wallet) -> bool:
    """Проверяет, использует ли кошелёк локальное подписание."""
    return wallet.signing_mode == "local"


def is_server_signing(wallet: Wallet) -> bool:
    """Проверяет, использует ли кошелёк серверное подписание."""
    return wallet.signing_mode == "server"

"""Helpers for transaction signing with support for biometric signing mode.

NOTE: signing_mode field is not yet in DB. These functions are prepared
for future integration when the field is added. Currently all signing
goes through server mode.
"""

from typing import Optional, Any
from aiogram.types import Message
from loguru import logger
from stellar_sdk import TransactionEnvelope

from core.domain.entities import User, Wallet
from infrastructure.services.app_context import AppContext
from other.faststream_tools import publish_pending_tx
from keyboards.webapp import webapp_sign_keyboard


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

    NOTE: В данный момент всегда использует server mode.
    Когда signing_mode будет добавлено в БД, функция будет поддерживать:
    - 'server': Подписываем на сервере и отправляем (текущая логика)
    - 'local': Публикуем TX для подписания через Web App

    Args:
        user: Пользователь
        wallet: Кошелёк
        transaction: TransactionEnvelope для подписания
        memo: Описание транзакции для отображения пользователю
        app_context: Контекст приложения
        message: Telegram сообщение для ответа
        sign_and_submit_callback: Async функция для подписания на сервере
            Сигнатура: async def callback() -> dict

    Returns:
        Результат отправки транзакции
    """
    # TODO: когда signing_mode будет в БД, добавить проверку:
    # signing_mode = getattr(wallet, 'signing_mode', 'server')
    # if signing_mode == "local": ... (WebApp flow)

    # Сейчас всегда server mode
    logger.info(f"User {user.id}: signing TX on server")
    return await sign_and_submit_callback()


async def request_local_signature(
    user_id: int,
    wallet_address: str,
    unsigned_xdr: str,
    memo: str,
    app_context: AppContext,
    message: Message,
    fsm_after_send: Optional[str] = None,
    success_msg: Optional[str] = None,
) -> str:
    """
    Запрашивает подпись через Web App (биометрия/пароль).

    Args:
        user_id: ID пользователя Telegram
        wallet_address: Публичный адрес кошелька
        unsigned_xdr: XDR транзакции без подписи
        memo: Описание транзакции
        app_context: Контекст приложения
        message: Telegram сообщение для ответа
        fsm_after_send: jsonpickle-сериализованный callback для вызова после успешной отправки
        success_msg: Сообщение об успехе для пользователя

    Returns:
        tx_id для отслеживания подписания
    """
    tx_id = await publish_pending_tx(
        user_id=user_id,
        wallet_address=wallet_address,
        unsigned_xdr=unsigned_xdr,
        memo=memo,
        fsm_after_send=fsm_after_send,
        success_msg=success_msg,
    )

    from other.lang_tools import my_gettext
    text = my_gettext(user_id, 'biometric_sign_prompt', app_context=app_context)
    if text == 'biometric_sign_prompt':
        text = f"Подтвердите транзакцию:\n\n{memo}"

    await message.answer(
        text,
        reply_markup=webapp_sign_keyboard(tx_id, user_id, app_context),
    )

    return tx_id


def is_local_signing(wallet: Wallet) -> bool:
    """Проверяет, использует ли кошелёк локальное подписание.

    NOTE: Всегда False пока signing_mode не добавлено в БД.
    """
    # TODO: return getattr(wallet, 'signing_mode', 'server') == 'local'
    return False


def is_server_signing(wallet: Wallet) -> bool:
    """Проверяет, использует ли кошелёк серверное подписание.

    NOTE: Всегда True пока signing_mode не добавлено в БД.
    """
    # TODO: return getattr(wallet, 'signing_mode', 'server') == 'server'
    return True

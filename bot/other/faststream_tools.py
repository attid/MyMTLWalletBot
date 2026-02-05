import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import jsonpickle  # type: ignore
import redis.asyncio as aioredis
from aiogram.fsm.context import FSMContext
from faststream.redis import RedisBroker, BinaryMessageFormatV1
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.common_keyboards import get_kb_return
from infrastructure.utils.telegram_utils import send_message, clear_last_message_id
from other.config_reader import config

from other.lang_tools import my_gettext

from infrastructure.services.app_context import AppContext

from shared.constants import (
    REDIS_TX_PREFIX,
    REDIS_TX_TTL,
    FIELD_USER_ID,
    FIELD_WALLET_ADDRESS,
    FIELD_UNSIGNED_XDR,
    FIELD_MEMO,
    FIELD_STATUS,
    FIELD_CREATED_AT,
    FIELD_FSM_AFTER_SEND,
    FIELD_SUCCESS_MSG,
    STATUS_PENDING,
)

APP_CONTEXT: Optional[AppContext] = None
REDIS_CLIENT: Optional[aioredis.Redis] = None

# --- Глобальные переменные и объекты брокера ---

PENDING_SIGN_REQUESTS: Dict[str, Dict[str, Any]] = {}

broker = RedisBroker(url=config.redis_url, message_format=BinaryMessageFormatV1)
broker_task = None


# --- Управление жизненным циклом брокера ---

async def start_broker(app_context: AppContext):
    global APP_CONTEXT, REDIS_CLIENT
    APP_CONTEXT = app_context
    REDIS_CLIENT = aioredis.from_url(config.redis_url)
    await broker.start()


async def stop_broker():
    """Останавливает брокер FastStream и Redis клиент."""
    global REDIS_CLIENT
    if REDIS_CLIENT:
        await REDIS_CLIENT.aclose()
        REDIS_CLIENT = None
    await broker.stop()


# --- Логика для биометрического подписания ---

async def publish_pending_tx(
    user_id: int,
    wallet_address: str,
    unsigned_xdr: str,
    memo: str,
    *,
    fsm_after_send: Optional[str] = None,
    success_msg: Optional[str] = None,
    redis_client: Optional[aioredis.Redis] = None,
) -> str:
    """
    Сохраняет транзакцию в Redis для подписания через Web App.

    Args:
        user_id: Telegram user ID
        wallet_address: Public key of the wallet (GXXX...)
        unsigned_xdr: XDR транзакции без подписи
        memo: Описание для пользователя ("Отправка 100 XLM на GXXX...")
        fsm_after_send: jsonpickle-сериализованный callback для вызова после успешной отправки
        success_msg: Сообщение об успехе для пользователя
        redis_client: Optional Redis client for dependency injection (uses global by default)

    Returns:
        tx_id: Уникальный ID транзакции
    """
    _redis = redis_client or REDIS_CLIENT

    if _redis is None:
        raise RuntimeError("REDIS_CLIENT is not initialized. Call start_broker() first.")

    # Генерируем уникальный tx_id
    tx_id = f"{user_id}_{uuid.uuid4().hex[:8]}"

    # Сохраняем в Redis Hash
    tx_key = f"{REDIS_TX_PREFIX}{tx_id}"
    mapping = {
        FIELD_USER_ID: str(user_id),
        FIELD_WALLET_ADDRESS: wallet_address,
        FIELD_UNSIGNED_XDR: unsigned_xdr,
        FIELD_MEMO: memo,
        FIELD_STATUS: STATUS_PENDING,
        FIELD_CREATED_AT: datetime.now(timezone.utc).isoformat(),
    }

    # Добавляем опциональные поля только если они заданы
    if fsm_after_send:
        mapping[FIELD_FSM_AFTER_SEND] = fsm_after_send
    if success_msg:
        mapping[FIELD_SUCCESS_MSG] = success_msg

    await _redis.hset(tx_key, mapping=mapping)
    await _redis.expire(tx_key, REDIS_TX_TTL)

    logger.info(f"Stored pending TX {tx_id} for user {user_id}")
    return tx_id


# --- Логика для WalletConnect ---

async def do_wc_sign_and_respond(session: AsyncSession, user_id: int, state: FSMContext):
    """
    Callback, который выполняется вместо стандартной логики подписи.
    """
    logger.info(f"do_wc_sign_and_respond: {user_id}")

    data = await state.get_data()
    internal_request_id = data.get("internal_request_id")
    original_request_id = data.get("original_request_id")  # <--- Получаем ID
    xdr = data.get("xdr")
    method = data.get("method")

    # Готовим основу для ответа
    response_msg = {"request_id": original_request_id}

    try:
        # 1. Подписываем транзакцию
        logger.info(f"method: {method} signed_xdr: {xdr}")
        # Формируем успешный ответ

        if method == "stellar_signAndSubmitXDR":
            # Нужна функция для отправки XDR в Horizon
            # Возьмите ее из signer_client_fs.py или напишите аналогичную
            assert xdr is not None, "xdr must not be None for stellar_signAndSubmitXDR"
            from other.stellar_tools import async_stellar_send
            submit_result = await async_stellar_send(xdr)
            status = "success" if submit_result.get("successful") else "pending"
            response_msg["result"] = {"status": status}
            logger.info(f"XDR for request {original_request_id} signed and submitted with status: {status}")
        else:  # По умолчанию или для stellar_signXDR
            response_msg["result"] = {"signedXDR": xdr}
            logger.info(f"XDR for request {original_request_id} signed.")

        # 2. Находим "замороженный" запрос и отправляем ему результат
        assert internal_request_id is not None, "internal_request_id must not be None"
        pending_req = PENDING_SIGN_REQUESTS.get(internal_request_id)
        if pending_req:
            pending_req['result'] = response_msg
            pending_req['event'].set()
        logger.info(f"pending_req: {pending_req}")

        # 3. Сообщаем пользователю об успехе
        assert APP_CONTEXT is not None, "APP_CONTEXT must be initialized"
        await send_message(session, user_id, my_gettext(user_id, 'wc_sign_success', app_context=APP_CONTEXT),
                           reply_markup=get_kb_return(user_id, app_context=APP_CONTEXT), app_context=APP_CONTEXT)
        logger.info(f"pending_req: {pending_req}")

    except Exception as e:
        logger.error(f"Error during WC signing for user {user_id}: {e}")
        # Формируем ответ с ошибкой
        response_msg["error"] = str(e)
        # В случае ошибки также уведомляем "замороженный" запрос
        assert internal_request_id is not None, "internal_request_id must not be None"
        pending_req = PENDING_SIGN_REQUESTS.get(internal_request_id)
        if pending_req:
            pending_req['result'] = response_msg
            pending_req['event'].set()
        assert APP_CONTEXT is not None, "APP_CONTEXT must be initialized"
        await send_message(session, user_id, my_gettext(user_id, 'bad_password', app_context=APP_CONTEXT),
                           reply_markup=get_kb_return(user_id, app_context=APP_CONTEXT), app_context=APP_CONTEXT)  # Общее сообщение об ошибке

    finally:
        await state.set_state(None)  # Очищаем состояние в любом случае


async def request_wc_signature(user_id: int, xdr: str, internal_request_id: str, original_request_id: str,
                               method: str, dapp_info: dict[str, Any]):
    """
    Функция-"мост", инициирующая процесс подписи у пользователя через FSM.
    """
    logger.info(f"request_wc_signature: {user_id}")
    # from other.global_data import global_data
    from routers.sign import cmd_check_xdr

    if APP_CONTEXT is None:
        logger.error("APP_CONTEXT is not initialized")
        return

    assert APP_CONTEXT.dispatcher is not None, "Dispatcher must be initialized in app_context"
    bot = APP_CONTEXT.bot
    state = APP_CONTEXT.dispatcher.fsm.get_context(bot, user_id, user_id)
    dapp_name = dapp_info.get("name", "Unknown App")
    dapp_url = dapp_info.get("url", "Unknown URL")

    # Запаковываем колбэк и сохраняем все в состояние
    wallet_connect_func = jsonpickle.dumps(do_wc_sign_and_respond)
    logger.info(f"wallet_connect_func: {wallet_connect_func}")
    await state.update_data(
        internal_request_id=internal_request_id,
        original_request_id=original_request_id,
        wallet_connect=wallet_connect_func,
        wallet_connect_info=f"{dapp_name} {dapp_url}",
        source='wallet_connect',
        method=method,
        tools='wallet_connect'
    )

    db_pool = APP_CONTEXT.db_pool
    async with db_pool.get_session() as session:
        await clear_last_message_id(user_id, app_context=APP_CONTEXT)
        await cmd_check_xdr(session, xdr, user_id, state, app_context=APP_CONTEXT)
        logger.info(f"cmd_check_xdr: {xdr}")


async def publish_pairing_request(wc_uri: str, address: str, user_info: dict):
    """
    Публикует запрос на создание сессии WalletConnect.
    """
    msg = {
        "wc_uri": wc_uri,
        "address": address,
        "user_info": user_info
    }
    await broker.publish(msg, list="wc-pairing-request")
    logger.info(
        f"Опубликовано сообщение для создания сессии для адреса {address} от пользователя {user_info.get('user_id')}")


async def publish_pairing_event(event: Dict[str, Any]):
    try:
        await broker.publish(event, list="wc-pairing-events")
    except Exception as e:
        logger.exception(f"Failed to publish pairing event: {e}")


@broker.subscriber(list="wc-sign-request-queue", max_workers=10)
async def handle_sign_request(msg: dict):
    """
    Получает запрос на подпись, инициирует диалог с пользователем и ждет результата.
    """
    internal_request_id = str(uuid.uuid4())
    event = asyncio.Event()

    user_info = msg.get("user_info", {})
    user_id = user_info.get("user_id")
    xdr = msg.get("xdr")
    original_request_id = msg.get("request_id")  # <--- Получаем ID изначального запроса
    method = msg.get("method")
    dapp_info = msg.get("dapp_info")

    if dapp_info:
        dapp_name = dapp_info.get("name", "Unknown App")
        dapp_url = dapp_info.get("url", "Unknown URL")
        logger.info(f"Получен запрос на подпись от dApp: '{dapp_name}' ({dapp_url}) для пользователя {user_id}")
    else:
        logger.info(f"Получен запрос на подпись для пользователя {user_id} (dApp info not provided)")

    if not all([user_id, xdr, original_request_id]):
        error_msg = f"Request is missing user_id, xdr, or request_id: {msg}"
        logger.error(error_msg)
        return {"error": error_msg}

    PENDING_SIGN_REQUESTS[internal_request_id] = {
        "event": event,
        "result": None
    }

    try:
        # Передаем ID дальше
        assert user_id is not None, "user_id must not be None"
        assert xdr is not None, "xdr must not be None"
        assert original_request_id is not None, "original_request_id must not be None"
        assert method is not None, "method must not be None"
        assert dapp_info is not None, "dapp_info must not be None"
        await request_wc_signature(user_id=user_id, xdr=xdr, internal_request_id=internal_request_id,
                                   original_request_id=original_request_id, method=method, dapp_info=dapp_info)

        await asyncio.wait_for(event.wait(), timeout=300)  # 5 минут на подпись
        logger.info(f"event waited: {event}")
        response = PENDING_SIGN_REQUESTS[internal_request_id].get("result")
        logger.info(f"response: {response}")
        return response

    except asyncio.TimeoutError:
        logger.error(f"Request {internal_request_id} timed out.")
        # Возвращаем ID и в случае ошибки таймаута
        return {"error": "User did not respond in time", "request_id": original_request_id}
    finally:
        PENDING_SIGN_REQUESTS.pop(internal_request_id, None)


@broker.subscriber(list="wc-pairing-events", max_workers=10)
async def handle_pairing_events(msg: dict):
    """
    Обрабатывает события о статусе WalletConnect пейринга и уведомляет пользователя.
    """
    try:
        # from other.global_data import global_data
        logger.info(msg)

        user_info = msg.get("user_info", {})
        user_id = user_info.get("user_id")
        if not user_id:
            logger.warning(f"No user_id in pairing event: {msg}")
            return

        status = msg.get("status")
        dapp_info = msg.get("dapp_info", {})
        dapp_name = dapp_info.get("name", "dApp")
        dapp_url = dapp_info.get("url", "")

        message = ""
        if status == "approved":
            message = f"✅ Установлено соединение с {dapp_name} ({dapp_url})"
        elif status == "failed":
            error = msg.get("error", "Неизвестная ошибка")
            message = f"❌ Ошибка подключения к {dapp_name}: {error}"
        elif status == "queued":
            message = f"⏳ Запрос на подключение к {dapp_name}..."
        else:
            logger.warning(f"Неизвестный статус события пейринга: {status}")
            return

        if APP_CONTEXT is None:
            logger.error("APP_CONTEXT is not initialized")
            return

        db_pool = APP_CONTEXT.db_pool
        async with db_pool.get_session() as session:
            await send_message(session, user_id, message, reply_markup=get_kb_return(user_id, app_context=APP_CONTEXT), app_context=APP_CONTEXT)

    except Exception as e:
        logger.exception(f"Ошибка в обработчике событий пейринга: {e}")

import asyncio
import uuid
from typing import Dict, Any

import jsonpickle
from aiogram.fsm.context import FSMContext
from faststream.redis import RedisBroker, BinaryMessageFormatV1
from loguru import logger
from sqlalchemy.orm import Session

from other.aiogram_tools import send_message
from other.config_reader import config
from faststream import FastStream

# --- Глобальные переменные и объекты брокера ---

PENDING_SIGN_REQUESTS: Dict[str, Dict[str, Any]] = {}

broker = RedisBroker(url=config.redis_url, message_format=BinaryMessageFormatV1)
broker_task = None


# --- Управление жизненным циклом брокера ---

async def start_broker():
    await broker.start()


async def stop_broker():
    """Останавливает брокер FastStream."""
    await broker.stop()


# --- Логика для WalletConnect ---

async def do_wc_sign_and_respond(session: Session, user_id: int, state: FSMContext):
    """
    Callback, который выполняется вместо стандартной логики подписи.
    """
    logger.info(f"do_wc_sign_and_respond: {user_id}")
    from other.aiogram_tools import send_message, my_gettext
    from other.stellar_tools import stellar_user_sign

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
            from other.stellar_tools import async_stellar_send
            submit_result = await async_stellar_send(xdr)
            status = "success" if submit_result.get("successful") else "pending"
            response_msg["result"] = {"status": status}
            logger.info(f"XDR for request {original_request_id} signed and submitted with status: {status}")
        else: # По умолчанию или для stellar_signXDR
            response_msg["result"] = {"signedXDR": xdr}
            logger.info(f"XDR for request {original_request_id} signed.")

        # 2. Находим "замороженный" запрос и отправляем ему результат
        pending_req = PENDING_SIGN_REQUESTS.get(internal_request_id)
        if pending_req:
            pending_req['result'] = response_msg
            pending_req['event'].set()
        logger.info(f"pending_req: {pending_req}")

        # 3. Сообщаем пользователю об успехе
        await send_message(session, user_id, my_gettext(user_id, 'wc_sign_success'))
        logger.info(f"pending_req: {pending_req}")

    except Exception as e:
        logger.error(f"Error during WC signing for user {user_id}: {e}")
        # Формируем ответ с ошибкой
        response_msg["error"] = str(e)
        # В случае ошибки также уведомляем "замороженный" запрос
        pending_req = PENDING_SIGN_REQUESTS.get(internal_request_id)
        if pending_req:
            pending_req['result'] = response_msg
            pending_req['event'].set()
        await send_message(session, user_id, my_gettext(user_id, 'bad_password'))  # Общее сообщение об ошибке

    finally:
        await state.set_state(None)  # Очищаем состояние в любом случае


async def request_wc_signature(user_id: int, xdr: str, internal_request_id: str, original_request_id: str,
                               method:str, dapp_info:dict[str,Any]):
    """
    Функция-"мост", инициирующая процесс подписи у пользователя через FSM.
    """
    logger.info(f"request_wc_signature: {user_id}")
    from other.global_data import global_data
    from routers.sign import cmd_check_xdr

    bot = global_data.bot
    state = global_data.dispatcher.fsm.get_context(bot, user_id, user_id)
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

    db_pool = global_data.db_pool
    with db_pool.get_session() as session:
        await cmd_check_xdr(session, xdr, user_id, state)
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
        from other.global_data import global_data
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

        db_pool = global_data.db_pool
        with db_pool.get_session() as session:
            await send_message(session, user_id, message)

    except Exception as e:
        logger.exception(f"Ошибка в обработчике событий пейринга: {e}")
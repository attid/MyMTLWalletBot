import json
from faststream.redis import RedisBroker
from loguru import logger

from other.config_reader import config

# 1. Инициализация брокера
broker = RedisBroker(url=config.redis_url)

async def start_broker():
    """Инициализирует соединение с брокером."""
    await broker.start()
    logger.info("FastStream broker connection started.")

async def stop_broker():
    """Закрывает соединение с брокером."""
    await broker.close()
    logger.info("FastStream broker connection stopped.")

async def publish_pairing_request(wc_uri: str, address: str):
    """
    Публикует запрос на создание сессии WalletConnect.
    """
    msg = {
        "wc_uri": wc_uri,
        "address": address,
    }
    # Передаем словарь напрямую, FastStream сам его сериализует
    await broker.publish(msg, channel="wc-pairing-request")
    logger.info(f"Опубликовано сообщение для создания сессии для адреса {address}")

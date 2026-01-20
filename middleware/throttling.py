from __future__ import annotations
from typing import *
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, CallbackQuery
import redis.asyncio.client
import time
from loguru import logger


def rate_limit(limit: int, key=None):
    """
    Decorator for configuring rate limit and key in different functions.

    :param limit: The rate limit in requests per minute
    :param key: Optional key for the rate limit
    :return: Decorated function
    """

    def decorator(func):
        setattr(func, 'throttling_rate_limit', limit)
        if key:
            setattr(func, 'throttling_key', key)
        return func

    return decorator


def chat_rate_limit(limit: int, key=None):
    """
    Decorator for configuring rate limit per chat in different functions.

    :param limit:
    :param key:
    :return:
    """

    def decorator(func):
        setattr(func, 'chat_throttling_rate_limit', limit)
        if key:
            setattr(func, 'chat_throttling_key', key)
        return func

    return decorator


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, redis: redis.asyncio.client.Redis, limit=.5, key_prefix='antiflood_'):
        self.rate_limit = limit
        self.prefix = key_prefix
        self.throttle_manager = ThrottleManager(redis=redis)

        super(ThrottlingMiddleware, self).__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:

        try:
            await self.on_process_event(event, data)
        except CancelHandler:
            # Cancel current handler
            return

        return await handler(event, data)

    async def on_process_event(
            self,
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)):
            return

        user = event.from_user
        if not user:
            return

        chat_id = None
        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery) and event.message:
            chat_id = event.message.chat.id

        if chat_id is None:
            return

        # User level throttling
        user_limit = getattr(data["handler"].callback, "throttling_rate_limit", None)
        user_key = getattr(data["handler"].callback, "throttling_key", f"{self.prefix}_message")

        # Chat level throttling
        chat_limit = getattr(data["handler"].callback, "chat_throttling_rate_limit", None)
        chat_key = getattr(data["handler"].callback, "chat_throttling_key", f"{self.prefix}_chat_message")

        # Use ThrottleManager.throttle method.
        try:
            if chat_limit is not None:
                await self.throttle_manager.throttle(chat_key, rate=chat_limit, user_id=None, chat_id=chat_id)
            if user_limit is not None:
                await self.throttle_manager.throttle(user_key, rate=user_limit, user_id=user.id,
                                                     chat_id=chat_id)
        except Throttled as t:
            # Execute action
            await self.event_throttled(event, t)

            # Cancel current handler
            raise CancelHandler()

    @staticmethod
    async def event_throttled(event: TelegramObject, throttled: Throttled):
        if not isinstance(event, (Message, CallbackQuery)):
            return
        # Calculate how many times is left till the block ends
        delta = throttled.rate - throttled.delta

        # Prevent flooding
        # if throttled.exceeded_count <= 2:
        if isinstance(event, Message):
            await event.answer(f'Too many events.\nTry again in {delta:.2f} seconds.')
        elif isinstance(event, CallbackQuery):
            await event.answer(f'Too many events.\nTry again in {delta:.2f} seconds.', show_alert=True)


class ThrottleManager:
    bucket_keys = [
        "RATE_LIMIT", "DELTA",
        "LAST_CALL", "EXCEEDED_COUNT"
    ]

    def __init__(self, redis: redis.asyncio.client.Redis):
        self.redis = redis

    async def throttle(self, key: str, rate: float, user_id: Optional[int] = None, chat_id: Optional[int] = None):
        if rate == 0:
            return True  # No throttling applied

        now = time.time()
        if user_id is not None:
            bucket_name = f'throttle_{key}_{user_id}_{chat_id}'
        else:
            bucket_name = f'throttle_{key}_{chat_id}'

        raw_data = await self.redis.hmget(bucket_name, self.bucket_keys)
        data: Dict[str, Any] = {
            k: float(v.decode())
            if isinstance(v, bytes)
            else v
            for k, v in zip(self.bucket_keys, raw_data)
            if v is not None
        }

        # Calculate
        called = data.get("LAST_CALL", now)
        delta = now - called
        result = delta >= rate or delta <= 0

        # Save result
        data["RATE_LIMIT"] = rate
        data["LAST_CALL"] = now
        data["DELTA"] = delta
        if not result:
            data["EXCEEDED_COUNT"] = data.get("EXCEEDED_COUNT", 0) + 1
        else:
            data["EXCEEDED_COUNT"] = 1

        await self.redis.hset(bucket_name, mapping=cast(Dict[str, Union[bytes, float, int, str]], data))  # type: ignore[arg-type]

        if not result:
            raise Throttled(key=key, chat=chat_id, user=user_id, **data)

        return result


class Throttled(Exception):
    def __init__(self, **kwargs):
        self.key = kwargs.pop("key", '<None>')
        self.called_at = kwargs.pop("LAST_CALL", time.time())
        self.rate = kwargs.pop("RATE_LIMIT", None)
        self.exceeded_count = kwargs.pop("EXCEEDED_COUNT", 0)
        self.delta = kwargs.pop("DELTA", 0)
        self.user = kwargs.pop('user', None)
        self.chat = kwargs.pop('chat', None)

    def __str__(self):
        return f"Rate limit exceeded! (Limit: {self.rate} s, " \
               f"exceeded: {self.exceeded_count}, " \
               f"time delta: {round(self.delta, 3)} s)"


class CancelHandler(Exception):
    pass

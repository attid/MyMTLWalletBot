import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Final

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.dispatcher.dispatcher import DEFAULT_BACKOFF_CONFIG
from aiogram.exceptions import (
    RestartingTelegram,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import AnswerCallbackQuery, Response, TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.utils.backoff import Backoff, BackoffConfig

logger: logging.Logger = logging.getLogger(__name__)
DEFAULT_MAX_RETRIES: Final[int] = 7


INLINE_RETRY_DISABLED: ContextVar[bool] = ContextVar(
    "telegram_inline_retry_disabled", default=False
)


class ChatRateLimitedError(Exception):
    """Telegram asked one chat to slow down; the caller owns the waiting policy.

    Raising instead of sleeping keeps the wait outside any per-chat delivery
    lock and lets the caller persist a cooldown that survives retries.
    """

    def __init__(self, *, retry_after: float, chat_id: int | None) -> None:
        super().__init__(
            f"Telegram rate limit for chat {chat_id}: retry after {retry_after:g}s"
        )
        self.retry_after = retry_after
        self.chat_id = chat_id


@contextmanager
def no_inline_rate_limit_sleep() -> Iterator[None]:
    """Turn Telegram rate limits into :class:`ChatRateLimitedError` for the caller."""
    token = INLINE_RETRY_DISABLED.set(True)
    try:
        yield
    finally:
        INLINE_RETRY_DISABLED.reset(token)


def request_chat_id(method: TelegramMethod[TelegramType]) -> int | None:
    """Best-effort chat id of an outgoing request, when the method has one."""
    chat_id = getattr(method, "chat_id", None)
    return chat_id if isinstance(chat_id, int) else None


class RetryRequestMiddleware(BaseRequestMiddleware):
    backoff_config: BackoffConfig
    max_retries: int

    __slots__ = ("backoff_config", "max_retries")

    def __init__(
        self,
        backoff_config: BackoffConfig = DEFAULT_BACKOFF_CONFIG,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.backoff_config = backoff_config
        self.max_retries = max_retries

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        backoff: Backoff = Backoff(config=self.backoff_config)
        retries: int = 0

        while True:
            retries += 1
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as e:
                if isinstance(method, AnswerCallbackQuery):
                    raise
                if INLINE_RETRY_DISABLED.get():
                    raise ChatRateLimitedError(
                        retry_after=float(e.retry_after),
                        chat_id=request_chat_id(method),
                    ) from e
                if retries == self.max_retries:
                    raise
                logger.error(
                    "Request '%s' failed due to rate limit. Sleeping %s seconds.",
                    type(method).__name__,
                    e.retry_after,
                )
                backoff.reset()
                await asyncio.sleep(e.retry_after)

            except (TelegramServerError, RestartingTelegram, TelegramNetworkError) as e:
                if retries == self.max_retries:
                    raise
                logger.error(
                    "Request '%s' failed due to %s - %s. Sleeping %s seconds.",
                    type(method).__name__,
                    type(e).__name__,
                    e,
                    backoff.next_delay,
                )
                await backoff.asleep()

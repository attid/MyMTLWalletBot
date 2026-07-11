"""Best-effort pending-notification badge rendering for tracked UI screens."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
import time
from typing import Awaitable, Callable, TypeVar
import uuid

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import ResponseError, WatchError

from infrastructure.services.notification_redis_store import NotificationRedisStore


BADGE_CALLBACK_DATA = "notification_pending:flush"
BASE_MARKUP_KEY_PREFIX = "notification:base_markup:"
UI_MARKUP_LOCK_KEY_PREFIX = "notification:ui_markup_lock:"
UI_MARKUP_LOCK_TTL_SECONDS = 15
UI_MARKUP_LOCK_WAIT_SECONDS = 5
UI_MARKUP_LOCK_RETRY_SECONDS = 0.05

_RELEASE_UI_MARKUP_LOCK = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('DEL', KEYS[1])
return 1
"""

_RENEW_UI_MARKUP_LOCK = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('PEXPIRE', KEYS[1], ARGV[2])
return 1
"""


class UiMarkupLockUnavailable(RuntimeError):
    """Raised when a per-user UI lease remains unavailable beyond its bound."""


class UiMarkupLeaseLost(RuntimeError):
    """Raised when a UI mutation loses ownership before it completes."""


T = TypeVar("T")


def ensure_ui_markup_lease(
    lease_lost: asyncio.Event | None, *, user_id: int, operation: str
) -> None:
    """Abort a UI mutation before it can run under an expired lease."""
    if lease_lost is None or not lease_lost.is_set():
        return
    logger.bind(
        event="notification_ui_markup_lease_lost",
        user_id=user_id,
        operation=operation,
    ).warning("notification UI markup lease lost; skipping operation")
    raise UiMarkupLeaseLost(operation)


async def await_ui_markup_lease_operation(
    lease_lost: asyncio.Event | None,
    *,
    user_id: int,
    operation: str,
    awaitable_factory: Callable[[], Awaitable[T]],
) -> T:
    """Await a UI operation, cancelling it if ownership is lost meanwhile."""
    ensure_ui_markup_lease(lease_lost, user_id=user_id, operation=operation)
    if lease_lost is None:
        return await awaitable_factory()

    operation_task = asyncio.create_task(awaitable_factory())
    lease_lost_task = asyncio.create_task(lease_lost.wait())
    try:
        done, _ = await asyncio.wait(
            {operation_task, lease_lost_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if lease_lost_task in done:
            if not operation_task.done():
                operation_task.cancel()
                try:
                    await operation_task
                except asyncio.CancelledError:
                    pass
            elif not operation_task.cancelled():
                try:
                    operation_task.result()
                except Exception:
                    pass
            ensure_ui_markup_lease(lease_lost, user_id=user_id, operation=operation)
        return await operation_task
    finally:
        if not lease_lost_task.done():
            lease_lost_task.cancel()
            try:
                await lease_lost_task
            except asyncio.CancelledError:
                pass
        if not operation_task.done():
            operation_task.cancel()
            try:
                await operation_task
            except asyncio.CancelledError:
                pass


@dataclass(frozen=True)
class BaseMarkup:
    """A serializable base keyboard associated with the tracked UI message."""

    message_id: int
    reply_markup: InlineKeyboardMarkup


class NotificationBadgeService:
    """Store base keyboards and derive a pending count badge when refreshing."""

    def __init__(
        self, *, bot: Bot, redis: Redis, store: NotificationRedisStore
    ) -> None:
        self._bot = bot
        self._redis = redis
        self._store = store

    @asynccontextmanager
    async def ui_markup_lock(self, user_id: int):
        """Serialize a user's UI markup mutations across all bot instances."""
        token = uuid.uuid4().hex
        key = self._ui_lock_key(user_id)
        deadline = time.monotonic() + UI_MARKUP_LOCK_WAIT_SECONDS
        while not await self._redis.set(
            key, token, nx=True, px=UI_MARKUP_LOCK_TTL_SECONDS * 1000
        ):
            if time.monotonic() >= deadline:
                raise UiMarkupLockUnavailable(
                    f"timed out waiting for UI markup lock for user {user_id}"
                )
            await asyncio.sleep(UI_MARKUP_LOCK_RETRY_SECONDS)

        lease_lost = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat_ui_markup_lock(key, token, lease_lost),
            name=f"notification-ui-markup-lock-heartbeat-{user_id}",
        )
        try:
            yield lease_lost
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            await self._release_ui_markup_lock(key, token)

    async def capture_base_markup(
        self, user_id: int, message_id: int, reply_markup: object | None
    ) -> None:
        """Record a successful inline UI render, or clear stale base markup."""
        async with self.ui_markup_lock(user_id) as lease_lost:
            await self.capture_base_markup_locked(
                user_id, message_id, reply_markup, lease_lost=lease_lost
            )

    async def capture_base_markup_locked(
        self,
        user_id: int,
        message_id: int,
        reply_markup: object | None,
        *,
        lease_lost: asyncio.Event | None = None,
    ) -> None:
        """Capture a base keyboard while the caller owns the UI markup lock."""
        key = self._key(user_id)
        ensure_ui_markup_lease(
            lease_lost, user_id=user_id, operation="capture_base_markup"
        )
        if not isinstance(reply_markup, InlineKeyboardMarkup):
            await await_ui_markup_lease_operation(
                lease_lost,
                user_id=user_id,
                operation="capture_base_markup",
                awaitable_factory=lambda: self._redis.delete(key),
            )
            return
        base_markup = append_notification_badge(reply_markup, pending_count=0)
        payload = {
            "message_id": message_id,
            "reply_markup": base_markup.model_dump(mode="json", exclude_none=True),
        }
        await await_ui_markup_lease_operation(
            lease_lost,
            user_id=user_id,
            operation="capture_base_markup",
            awaitable_factory=lambda: self._redis.set(
                key, json.dumps(payload, separators=(",", ":"))
            ),
        )

    async def get_base_markup(self, user_id: int) -> BaseMarkup | None:
        """Return the last confirmed base keyboard for a user's tracked screen."""
        value = await self._redis.get(self._key(user_id))
        if value is None:
            return None
        raw = value.decode() if isinstance(value, bytes) else value
        try:
            payload = json.loads(raw)
            return BaseMarkup(
                message_id=int(payload["message_id"]),
                reply_markup=InlineKeyboardMarkup.model_validate(
                    payload["reply_markup"]
                ),
            )
        except (KeyError, TypeError, ValueError):
            logger.bind(
                event="notification_badge_base_markup_invalid", user_id=user_id
            ).warning("discarding invalid notification badge base markup")
            await self._redis.delete(self._key(user_id))
            return None

    async def refresh(self, user_id: int) -> None:
        """Edit only the tracked reply markup; failures never interrupt delivery."""
        async with self.ui_markup_lock(user_id) as lease_lost:
            await self.refresh_locked(user_id, lease_lost=lease_lost)

    async def refresh_locked(
        self, user_id: int, *, lease_lost: asyncio.Event | None = None
    ) -> None:
        """Refresh a badge while the caller owns the UI markup lock."""
        base = await self.get_base_markup(user_id)
        if base is None:
            return
        count = await self._store.pending_count(user_id)
        markup = append_notification_badge(base.reply_markup, count)
        try:
            await await_ui_markup_lease_operation(
                lease_lost,
                user_id=user_id,
                operation="refresh_badge_markup",
                awaitable_factory=lambda: self._bot.edit_message_reply_markup(
                    chat_id=user_id, message_id=base.message_id, reply_markup=markup
                ),
            )
        except UiMarkupLeaseLost:
            return
        except Exception:
            logger.bind(
                event="notification_badge_edit_failed", user_id=user_id
            ).exception("notification badge refresh failed")

    async def decorate_markup(
        self, user_id: int, reply_markup: object | None
    ) -> object | None:
        """Derive the current badge for a UI render while its lock is held."""
        if not isinstance(reply_markup, InlineKeyboardMarkup):
            return reply_markup
        return append_notification_badge(
            reply_markup, await self._store.pending_count(user_id)
        )

    async def _heartbeat_ui_markup_lock(
        self, key: str, token: str, lease_lost: asyncio.Event
    ) -> None:
        try:
            while True:
                await asyncio.sleep(UI_MARKUP_LOCK_TTL_SECONDS / 3)
                if await self._renew_ui_markup_lock(key, token):
                    continue
                lease_lost.set()
                logger.warning("notification UI markup lock lease was lost")
                return
        except asyncio.CancelledError:
            raise
        except Exception:
            lease_lost.set()
            logger.exception("notification UI markup lock heartbeat failed")

    async def _release_ui_markup_lock(self, key: str, token: str) -> bool:
        try:
            return bool(await self._redis.eval(_RELEASE_UI_MARKUP_LOCK, 1, key, token))
        except ResponseError as error:
            if "unknown command 'eval'" not in str(error).lower():
                raise
        while True:
            async with self._redis.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(key)
                    if await pipeline.get(key) != token:
                        return False
                    pipeline.multi()
                    pipeline.delete(key)
                    await pipeline.execute()
                    return True
                except WatchError:
                    continue

    async def _renew_ui_markup_lock(self, key: str, token: str) -> bool:
        try:
            return bool(
                await self._redis.eval(
                    _RENEW_UI_MARKUP_LOCK,
                    1,
                    key,
                    token,
                    UI_MARKUP_LOCK_TTL_SECONDS * 1000,
                )
            )
        except ResponseError as error:
            if "unknown command 'eval'" not in str(error).lower():
                raise
        while True:
            async with self._redis.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(key)
                    if await pipeline.get(key) != token:
                        return False
                    pipeline.multi()
                    pipeline.pexpire(key, UI_MARKUP_LOCK_TTL_SECONDS * 1000)
                    await pipeline.execute()
                    return True
                except WatchError:
                    continue

    @staticmethod
    def _key(user_id: int) -> str:
        return f"{BASE_MARKUP_KEY_PREFIX}{user_id}"

    @staticmethod
    def _ui_lock_key(user_id: int) -> str:
        return f"{UI_MARKUP_LOCK_KEY_PREFIX}{user_id}"


def append_notification_badge(
    base_markup: InlineKeyboardMarkup, pending_count: int
) -> InlineKeyboardMarkup:
    """Copy a base keyboard and add one derived bottom badge row when needed."""
    rows = [
        [button for button in row if button.callback_data != BADGE_CALLBACK_DATA]
        for row in base_markup.inline_keyboard
    ]
    rows = [row for row in rows if row]
    if pending_count > 0:
        noun = "notification" if pending_count == 1 else "notifications"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔔 {pending_count} pending {noun}",
                    callback_data=BADGE_CALLBACK_DATA,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)

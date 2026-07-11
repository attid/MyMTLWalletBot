"""Redis persistence for delayed blockchain notification delivery."""

from redis.asyncio import Redis
from redis.exceptions import ResponseError, WatchError

from core.models.blockchain_notification import BlockchainNotification


_TOUCH_HOLD = """
local existing = redis.call('GET', KEYS[1])
local requested = tonumber(ARGV[1])
if existing and tonumber(existing) > requested then
    requested = tonumber(existing)
end
redis.call('SET', KEYS[1], requested, 'EX', ARGV[2])
redis.call('ZADD', KEYS[2], requested, ARGV[3])
return requested
"""

_RELEASE_DUE_HOLD_IF_UNCHANGED = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('DEL', KEYS[1])
if redis.call('LLEN', KEYS[3]) > 0 then
    redis.call('ZADD', KEYS[2], ARGV[3], ARGV[2])
else
    redis.call('ZREM', KEYS[2], ARGV[2])
end
return 1
"""

_ENQUEUE = """
if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1
    or redis.call('SISMEMBER', KEYS[2], ARGV[1]) == 1 then
    return 0
end
redis.call('SADD', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('SADD', KEYS[2], ARGV[1])
redis.call('RPUSH', KEYS[3], ARGV[2])
return 1
"""

_CLAIM_ACCEPT = """
if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1
    or redis.call('SISMEMBER', KEYS[2], ARGV[1]) == 1 then
    return 'duplicate'
end
redis.call('SADD', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('SADD', KEYS[2], ARGV[1])
redis.call('RPUSH', KEYS[3], ARGV[2])
local hold_until = redis.call('GET', KEYS[4])
if hold_until and tonumber(hold_until) > tonumber(ARGV[4]) then
    return 'queued'
end
redis.call('ZADD', KEYS[5], ARGV[4], ARGV[5])
return 'direct'
"""

_ACKNOWLEDGE_HEAD = """
if redis.call('LINDEX', KEYS[1], 0) ~= ARGV[1] then
    return 0
end
redis.call('LPOP', KEYS[1])
redis.call('SREM', KEYS[2], ARGV[2])
return 1
"""

_ACKNOWLEDGE_HEAD_IF_LOCK_OWNED = """
if redis.call('GET', KEYS[3]) ~= ARGV[3] then
    return 0
end
if redis.call('LINDEX', KEYS[1], 0) ~= ARGV[1] then
    return 0
end
redis.call('LPOP', KEYS[1])
redis.call('SREM', KEYS[2], ARGV[2])
return 1
"""

_DUE_USERS = """
local due_users = {}
local stale_users = {}
local rescheduled_users = {}
local scan_limit = tonumber(ARGV[2])
local offset = 0
for _ = 1, tonumber(ARGV[5]) do
    local users = redis.call(
        'ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', offset, scan_limit
    )
    if #users == 0 then
        break
    end
    for _, user_id in ipairs(users) do
        local hold_until = redis.call('GET', ARGV[3] .. user_id)
        if not hold_until then
            if redis.call('LLEN', ARGV[4] .. user_id) > 0 then
                if #due_users < scan_limit then
                    table.insert(due_users, user_id)
                end
            else
                table.insert(stale_users, user_id)
            end
        elseif tonumber(hold_until) <= tonumber(ARGV[1]) then
            if #due_users < scan_limit then
                table.insert(due_users, user_id)
            end
        else
            rescheduled_users[user_id] = tonumber(hold_until)
        end
    end
    if #due_users >= scan_limit or #users < scan_limit then
        break
    end
    offset = offset + #users
end
for _, user_id in ipairs(stale_users) do
    redis.call('ZREM', KEYS[1], user_id)
end
for user_id, hold_until in pairs(rescheduled_users) do
    redis.call('ZADD', KEYS[1], hold_until, user_id)
end
return due_users
"""

_CLEAR_IMMEDIATE_DUE_IF_EMPTY_AND_LOCK_OWNED = """
if redis.call('GET', KEYS[4]) ~= ARGV[1] then
    return 0
end
if redis.call('LLEN', KEYS[1]) ~= 0 or redis.call('GET', KEYS[2]) then
    return 0
end
local due_at = redis.call('ZSCORE', KEYS[3], ARGV[2])
if due_at and tonumber(due_at) <= tonumber(ARGV[3]) then
    redis.call('ZREM', KEYS[3], ARGV[2])
    return 1
end
return 0
"""

_RELEASE_LOCK = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('DEL', KEYS[1])
return 1
"""

_RENEW_LOCK = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

DEFAULT_DEDUPE_TTL_SECONDS = 30 * 24 * 60 * 60
MAX_DUE_SCAN_PAGES = 10


class NotificationRedisStore:
    """Stores holds, FIFO notifications, and distributed flush locks in Redis."""

    def __init__(
        self,
        redis: Redis,
        *,
        hold_seconds: int,
        lock_ttl_seconds: int,
        dedupe_ttl_seconds: int = DEFAULT_DEDUPE_TTL_SECONDS,
        key_prefix: str = "",
    ) -> None:
        if hold_seconds <= 0:
            raise ValueError("hold_seconds must be positive")
        if lock_ttl_seconds <= 0:
            raise ValueError("lock_ttl_seconds must be positive")
        if dedupe_ttl_seconds <= 0:
            raise ValueError("dedupe_ttl_seconds must be positive")
        self._redis = redis
        self._hold_seconds = hold_seconds
        self._lock_ttl_seconds = lock_ttl_seconds
        # Pending queues deliberately have no TTL, so a queue can outlive this
        # 30-day dedupe window. Successful queue cleanup may later remove the
        # matching dedupe metadata; retention is conservative to limit retries.
        self._dedupe_ttl_seconds = dedupe_ttl_seconds
        self._key_prefix = key_prefix

    async def touch(self, user_id: int, *, now: int) -> int:
        """Create or extend a user's absolute hold and reschedule its deadline."""
        hold_until = now + self._hold_seconds
        try:
            result = await self._redis.eval(
                _TOUCH_HOLD,
                2,
                self._hold_key(user_id),
                self._due_key(),
                hold_until,
                self._hold_seconds,
                str(user_id),
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            result = await self._touch_without_lua(user_id, hold_until)
        return int(result)

    async def release(self, user_id: int) -> None:
        """Explicitly release a completed flow's hold and due schedule.

        This unconditional operation is for completion paths. Workers that
        observed a due deadline must use :meth:`release_due_hold_if_unchanged`.
        """
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.delete(self._hold_key(user_id))
            pipeline.zrem(self._due_key(), str(user_id))
            await pipeline.execute()

    async def release_due_hold_if_unchanged(
        self, user_id: int, expected_hold_until: int, *, now: int
    ) -> bool:
        """Release a worker-observed hold only if its deadline is unchanged.

        A false result means a concurrent touch renewed or replaced the hold;
        the renewed hold and its due schedule are left intact for rescheduling.
        If the matching generation has pending work, it is rescheduled at
        ``now`` before the hold is removed.
        """
        try:
            result = await self._redis.eval(
                _RELEASE_DUE_HOLD_IF_UNCHANGED,
                3,
                self._hold_key(user_id),
                self._due_key(),
                self._pending_key(user_id),
                expected_hold_until,
                str(user_id),
                now,
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            return await self._release_due_hold_if_unchanged_without_lua(
                user_id, expected_hold_until, now
            )
        return bool(result)

    async def release_hold_if_unchanged(
        self, user_id: int, expected_hold_until: int, *, now: int
    ) -> bool:
        """Release one observed flow generation, never a later touch."""
        return await self.release_due_hold_if_unchanged(
            user_id, expected_hold_until, now=now
        )

    async def hold_until(self, user_id: int) -> int | None:
        value = await self._redis.get(self._hold_key(user_id))
        return None if value is None else int(self._as_str(value))

    async def enqueue(self, user_id: int, notification: BlockchainNotification) -> bool:
        """Atomically deduplicate and append a notification to the FIFO queue."""
        if user_id != notification.user_id:
            raise ValueError("user_id must match notification.user_id")
        try:
            result = await self._redis.eval(
                _ENQUEUE,
                3,
                self._dedupe_key(user_id),
                self._pending_id_key(user_id),
                self._pending_key(user_id),
                notification.idempotency_key,
                notification.to_json(),
                self._dedupe_ttl_seconds,
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            return await self._enqueue_without_lua(user_id, notification)
        return bool(result)

    async def claim_accept(
        self, user_id: int, notification: BlockchainNotification, *, now: int
    ) -> str:
        """Atomically deduplicate, retain, and classify an accepted event.

        All accepted events enter the FIFO before a caller attempts Telegram
        delivery.  ``direct`` means no active hold existed at this atomic
        decision; the caller must still recheck before sending.
        """
        if user_id != notification.user_id:
            raise ValueError("user_id must match notification.user_id")
        try:
            result = await self._redis.eval(
                _CLAIM_ACCEPT,
                5,
                self._dedupe_key(user_id),
                self._pending_id_key(user_id),
                self._pending_key(user_id),
                self._hold_key(user_id),
                self._due_key(),
                notification.idempotency_key,
                notification.to_json(),
                self._dedupe_ttl_seconds,
                now,
                str(user_id),
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            return await self._claim_accept_without_lua(user_id, notification, now)
        return self._as_str(result)

    async def clear_immediate_due_if_empty_and_lock_owned(
        self, user_id: int, token: str, *, now: int
    ) -> bool:
        """Remove only an owned, immediate schedule after an empty flush.

        The queue, hold, due member, and lock are checked atomically. A new
        direct claim either makes the queue nonempty before this check or adds
        a new immediate schedule afterwards; a concurrent touch keeps its
        deadline schedule intact.
        """
        try:
            result = await self._redis.eval(
                _CLEAR_IMMEDIATE_DUE_IF_EMPTY_AND_LOCK_OWNED,
                4,
                self._pending_key(user_id),
                self._hold_key(user_id),
                self._due_key(),
                self._lock_key(user_id),
                token,
                str(user_id),
                now,
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            return await self._clear_immediate_due_if_empty_and_lock_owned_without_lua(
                user_id, token, now
            )
        return bool(result)

    async def peek(self, user_id: int) -> BlockchainNotification | None:
        value = await self._redis.lindex(self._pending_key(user_id), 0)
        if value is None:
            return None
        return BlockchainNotification.from_json(self._as_str(value))

    async def pending_count(self, user_id: int) -> int:
        return int(await self._redis.llen(self._pending_key(user_id)))

    async def acknowledge(
        self, user_id: int, expected_head: BlockchainNotification
    ) -> bool:
        """Remove a notification only if it is still the queue head."""
        try:
            result = await self._redis.eval(
                _ACKNOWLEDGE_HEAD,
                2,
                self._pending_key(user_id),
                self._pending_id_key(user_id),
                expected_head.to_json(),
                expected_head.idempotency_key,
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            return await self._acknowledge_without_lua(user_id, expected_head)
        return bool(result)

    async def acknowledge_if_lock_owned(
        self, user_id: int, expected_head: BlockchainNotification, token: str
    ) -> bool:
        """Remove the head only when both it and the lock owner still match."""
        try:
            result = await self._redis.eval(
                _ACKNOWLEDGE_HEAD_IF_LOCK_OWNED,
                3,
                self._pending_key(user_id),
                self._pending_id_key(user_id),
                self._lock_key(user_id),
                expected_head.to_json(),
                expected_head.idempotency_key,
                token,
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            return await self._acknowledge_if_lock_owned_without_lua(
                user_id, expected_head, token
            )
        return bool(result)

    async def due_users(self, *, now: int, limit: int = 100) -> list[int]:
        """Atomically return currently due users while cleaning stale schedules.

        A user whose hold was renewed is rescheduled to the actual deadline.
        A no-hold user remains due while its pending queue is nonempty; stale
        no-hold users without pending work are removed.
        """
        try:
            users = await self._redis.eval(
                _DUE_USERS,
                1,
                self._due_key(),
                now,
                limit,
                self._hold_key_prefix(),
                self._pending_key_prefix(),
                MAX_DUE_SCAN_PAGES,
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            users = await self._due_users_without_lua(now, limit)
        return [int(self._as_str(user)) for user in users]

    async def acquire_lock(self, user_id: int, token: str) -> bool:
        """Acquire a per-user lock whose owner is identified by ``token``."""
        acquired = await self._redis.set(
            self._lock_key(user_id), token, nx=True, ex=self._lock_ttl_seconds
        )
        return bool(acquired)

    async def release_lock(self, user_id: int, token: str) -> bool:
        """Release a lock only when ``token`` still identifies its owner."""
        try:
            result = await self._redis.eval(
                _RELEASE_LOCK, 1, self._lock_key(user_id), token
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            return await self._release_lock_without_lua(user_id, token)
        return bool(result)

    async def renew_lock(self, user_id: int, token: str) -> bool:
        """Extend a lock only if ``token`` still owns it."""
        try:
            result = await self._redis.eval(
                _RENEW_LOCK,
                1,
                self._lock_key(user_id),
                token,
                self._lock_ttl_seconds,
            )
        except ResponseError as error:
            if not self._is_unsupported_eval(error):
                raise
            return await self._renew_lock_without_lua(user_id, token)
        return bool(result)

    async def _touch_without_lua(self, user_id: int, hold_until: int) -> int:
        hold_key = self._hold_key(user_id)
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(hold_key)
                    existing = await pipeline.get(hold_key)
                    actual_hold = max(
                        hold_until,
                        int(self._as_str(existing)) if existing is not None else 0,
                    )
                    pipeline.multi()
                    pipeline.set(hold_key, actual_hold, ex=self._hold_seconds)
                    pipeline.zadd(self._due_key(), {str(user_id): actual_hold})
                    await pipeline.execute()
                    return actual_hold
            except WatchError:
                continue

    async def _release_due_hold_if_unchanged_without_lua(
        self, user_id: int, expected_hold_until: int, now: int
    ) -> bool:
        hold_key = self._hold_key(user_id)
        due_key = self._due_key()
        pending_key = self._pending_key(user_id)
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(hold_key, due_key, pending_key)
                    hold_until = await pipeline.get(hold_key)
                    if (
                        hold_until is None
                        or int(self._as_str(hold_until)) != expected_hold_until
                    ):
                        return False
                    pending_count = await pipeline.llen(pending_key)
                    pipeline.multi()
                    pipeline.delete(hold_key)
                    if pending_count:
                        pipeline.zadd(due_key, {str(user_id): now})
                    else:
                        pipeline.zrem(due_key, str(user_id))
                    await pipeline.execute()
                    return True
            except WatchError:
                continue

    async def _enqueue_without_lua(
        self, user_id: int, notification: BlockchainNotification
    ) -> bool:
        dedupe_key = self._dedupe_key(user_id)
        pending_id_key = self._pending_id_key(user_id)
        pending_key = self._pending_key(user_id)
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(dedupe_key, pending_id_key)
                    if await pipeline.sismember(
                        dedupe_key, notification.idempotency_key
                    ) or await pipeline.sismember(
                        pending_id_key, notification.idempotency_key
                    ):
                        return False
                    pipeline.multi()
                    pipeline.sadd(dedupe_key, notification.idempotency_key)
                    pipeline.expire(dedupe_key, self._dedupe_ttl_seconds)
                    pipeline.sadd(pending_id_key, notification.idempotency_key)
                    pipeline.rpush(pending_key, notification.to_json())
                    await pipeline.execute()
                    return True
            except WatchError:
                continue

    async def _claim_accept_without_lua(
        self, user_id: int, notification: BlockchainNotification, now: int
    ) -> str:
        dedupe_key = self._dedupe_key(user_id)
        pending_id_key = self._pending_id_key(user_id)
        pending_key = self._pending_key(user_id)
        hold_key = self._hold_key(user_id)
        due_key = self._due_key()
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(dedupe_key, pending_id_key, hold_key, due_key)
                    if await pipeline.sismember(
                        dedupe_key, notification.idempotency_key
                    ) or await pipeline.sismember(
                        pending_id_key, notification.idempotency_key
                    ):
                        return "duplicate"
                    hold_until = await pipeline.get(hold_key)
                    pipeline.multi()
                    pipeline.sadd(dedupe_key, notification.idempotency_key)
                    pipeline.expire(dedupe_key, self._dedupe_ttl_seconds)
                    pipeline.sadd(pending_id_key, notification.idempotency_key)
                    pipeline.rpush(pending_key, notification.to_json())
                    if hold_until is None or int(self._as_str(hold_until)) <= now:
                        pipeline.zadd(due_key, {str(user_id): now})
                    await pipeline.execute()
                    if hold_until is not None and int(self._as_str(hold_until)) > now:
                        return "queued"
                    return "direct"
            except WatchError:
                continue

    async def _clear_immediate_due_if_empty_and_lock_owned_without_lua(
        self, user_id: int, token: str, now: int
    ) -> bool:
        pending_key = self._pending_key(user_id)
        hold_key = self._hold_key(user_id)
        due_key = self._due_key()
        lock_key = self._lock_key(user_id)
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(pending_key, hold_key, due_key, lock_key)
                    owner = await pipeline.get(lock_key)
                    if owner is None or self._as_str(owner) != token:
                        return False
                    if await pipeline.llen(pending_key) != 0:
                        return False
                    if await pipeline.get(hold_key) is not None:
                        return False
                    due_at = await pipeline.zscore(due_key, str(user_id))
                    if due_at is None or float(due_at) > now:
                        return False
                    pipeline.multi()
                    pipeline.zrem(due_key, str(user_id))
                    await pipeline.execute()
                    return True
            except WatchError:
                continue

    async def _acknowledge_without_lua(
        self, user_id: int, expected_head: BlockchainNotification
    ) -> bool:
        pending_key = self._pending_key(user_id)
        pending_id_key = self._pending_id_key(user_id)
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(pending_key, pending_id_key)
                    current_head = await pipeline.lindex(pending_key, 0)
                    if (
                        current_head is None
                        or self._as_str(current_head) != expected_head.to_json()
                    ):
                        return False
                    pipeline.multi()
                    pipeline.lpop(pending_key)
                    pipeline.srem(pending_id_key, expected_head.idempotency_key)
                    await pipeline.execute()
                    return True
            except WatchError:
                continue

    async def _acknowledge_if_lock_owned_without_lua(
        self, user_id: int, expected_head: BlockchainNotification, token: str
    ) -> bool:
        pending_key = self._pending_key(user_id)
        pending_id_key = self._pending_id_key(user_id)
        lock_key = self._lock_key(user_id)
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(pending_key, pending_id_key, lock_key)
                    owner = await pipeline.get(lock_key)
                    current_head = await pipeline.lindex(pending_key, 0)
                    if (
                        owner is None
                        or self._as_str(owner) != token
                        or current_head is None
                        or self._as_str(current_head) != expected_head.to_json()
                    ):
                        return False
                    pipeline.multi()
                    pipeline.lpop(pending_key)
                    pipeline.srem(pending_id_key, expected_head.idempotency_key)
                    await pipeline.execute()
                    return True
            except WatchError:
                continue

    async def _due_users_without_lua(self, now: int, limit: int) -> list[str | bytes]:
        due_key = self._due_key()
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(due_key)
                    users: list[str | bytes] = []
                    offset = 0
                    for _ in range(MAX_DUE_SCAN_PAGES):
                        page = await pipeline.zrangebyscore(
                            due_key, "-inf", now, start=offset, num=limit
                        )
                        users.extend(page)
                        if len(page) < limit:
                            break
                        offset += len(page)
                    hold_keys = [
                        self._hold_key(int(self._as_str(user))) for user in users
                    ]
                    pending_keys = [
                        self._pending_key(int(self._as_str(user))) for user in users
                    ]
                    if hold_keys:
                        await pipeline.watch(*hold_keys, *pending_keys)
                        holds = await pipeline.mget(hold_keys)
                        pending_counts = [
                            await pipeline.llen(pending_key)
                            for pending_key in pending_keys
                        ]
                    else:
                        holds = []
                        pending_counts = []
                    due_users: list[str | bytes] = []
                    pipeline.multi()
                    for user, hold_until, pending_count in zip(
                        users, holds, pending_counts, strict=True
                    ):
                        user_id = self._as_str(user)
                        if hold_until is None:
                            if pending_count == 0:
                                pipeline.zrem(due_key, user_id)
                            elif len(due_users) < limit:
                                due_users.append(user)
                        elif int(self._as_str(hold_until)) <= now:
                            if len(due_users) < limit:
                                due_users.append(user)
                        else:
                            pipeline.zadd(
                                due_key, {user_id: int(self._as_str(hold_until))}
                            )
                    await pipeline.execute()
                    return due_users
            except WatchError:
                continue

    async def _release_lock_without_lua(self, user_id: int, token: str) -> bool:
        lock_key = self._lock_key(user_id)
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(lock_key)
                    owner = await pipeline.get(lock_key)
                    if owner is None or self._as_str(owner) != token:
                        return False
                    pipeline.multi()
                    pipeline.delete(lock_key)
                    await pipeline.execute()
                    return True
            except WatchError:
                continue

    async def _renew_lock_without_lua(self, user_id: int, token: str) -> bool:
        lock_key = self._lock_key(user_id)
        while True:
            try:
                async with self._redis.pipeline() as pipeline:
                    await pipeline.watch(lock_key)
                    owner = await pipeline.get(lock_key)
                    if owner is None or self._as_str(owner) != token:
                        return False
                    pipeline.multi()
                    pipeline.expire(lock_key, self._lock_ttl_seconds)
                    await pipeline.execute()
                    return True
            except WatchError:
                continue

    @staticmethod
    def _is_unsupported_eval(error: ResponseError) -> bool:
        return "unknown command 'eval'" in str(error).lower()

    @staticmethod
    def _as_str(value: str | bytes) -> str:
        return value.decode() if isinstance(value, bytes) else value

    def _hold_key(self, user_id: int) -> str:
        return f"{self._hold_key_prefix()}{user_id}"

    def _pending_key(self, user_id: int) -> str:
        return f"{self._pending_key_prefix()}{user_id}"

    def _pending_key_prefix(self) -> str:
        return f"{self._key_prefix}notification:pending:"

    def _dedupe_key(self, user_id: int) -> str:
        return f"{self._key_prefix}notification:dedupe:{user_id}"

    def _pending_id_key(self, user_id: int) -> str:
        return f"{self._key_prefix}notification:pending_ids:{user_id}"

    def _lock_key(self, user_id: int) -> str:
        return f"{self._key_prefix}notification:flush_lock:{user_id}"

    def _due_key(self) -> str:
        return f"{self._key_prefix}notification:due"

    def _hold_key_prefix(self) -> str:
        return f"{self._key_prefix}notification:hold:"

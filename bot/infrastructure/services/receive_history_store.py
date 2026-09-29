"""Redis persistence for the receive-invoice amount history."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import List, Optional, Protocol

from redis.asyncio import Redis

HISTORY_KEY_PREFIX = "receive_hist:"
HISTORY_LIMIT = 5
HISTORY_TTL_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True)
class HistoryAmount:
    """One (amount, asset) pair recently used on the invoice screen."""

    amount: str
    asset_code: str
    issuer: Optional[str]

    def to_json(self) -> str:
        return json.dumps(
            {
                "amount": self.amount,
                "asset_code": self.asset_code,
                "issuer": self.issuer,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw_json: str) -> "HistoryAmount":
        payload = json.loads(raw_json)
        return cls(
            amount=str(payload["amount"]),
            asset_code=str(payload["asset_code"]),
            issuer=payload.get("issuer"),
        )


class HistoryClock(Protocol):
    def __call__(self) -> float: ...


class ReceiveHistoryStore:
    """Keeps the last few (amount, asset) pairs per user in Redis.

    The pairs feed the quick-amount buttons on the invoice amount screen.
    Data is disposable: a losing Redis keyspace must not break anything.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        key_prefix: str = HISTORY_KEY_PREFIX,
        limit: int = HISTORY_LIMIT,
        ttl_seconds: int = HISTORY_TTL_SECONDS,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._limit = max(1, limit)
        self._ttl_seconds = ttl_seconds

    def _key(self, user_id: int) -> str:
        return f"{self._key_prefix}{user_id}"

    async def add(
        self, user_id: int, entry: HistoryAmount, *, now: Optional[float] = None
    ) -> None:
        """Record one (amount, asset) pair, keeping only the newest entries."""
        if not entry.amount or not entry.asset_code:
            return
        score = now if now is not None else time.time()
        key = self._key(user_id)
        member = entry.to_json()
        await self._redis.zadd(key, {member: score})
        await self._redis.zremrangebyrank(key, 0, -(self._limit + 1))
        await self._redis.expire(key, self._ttl_seconds)

    async def get_history(self, user_id: int) -> List[HistoryAmount]:
        """Return stored pairs, newest first, deduplicated by amount+asset."""
        raw_members = await self._redis.zrange(
            self._key(user_id),
            -self._limit,
            -1,
            desc=True,
        )
        entries: List[HistoryAmount] = []
        seen: set[str] = set()
        for raw in raw_members:
            member = raw.decode() if isinstance(raw, bytes) else raw
            try:
                entry = HistoryAmount.from_json(member)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                await self._redis.zrem(self._key(user_id), member)
                continue
            dedupe_key = (entry.amount, entry.asset_code)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            entries.append(entry)
        return entries

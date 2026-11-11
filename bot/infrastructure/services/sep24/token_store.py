"""Best-effort Redis cache for SEP-10 JWT tokens.

Anchor tokens live anywhere between 10 minutes and 24 hours (both observed
live), and a wallet needs the token for every SEP-24 call. Caching is keyed by
user, wallet public key and anchor domain, because the JWT is bound to the
authenticated account: switching the default wallet must not reuse a token.
"""

import base64
import binascii
import json
import time
from typing import Any, Callable

from loguru import logger

from core.models.sep24 import Sep10Token

DEFAULT_PREFIX = "sep10:"
DEFAULT_SKEW_SECONDS = 300


class Sep10TokenStore:
    """Redis-backed SEP-10 token cache with a degraded no-Redis mode."""

    def __init__(
        self,
        redis: Any = None,
        *,
        prefix: str = DEFAULT_PREFIX,
        skew_seconds: int = DEFAULT_SKEW_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._skew_seconds = skew_seconds
        self._clock = clock

    @staticmethod
    def key(
        user_id: int, public_key: str, domain: str, prefix: str = DEFAULT_PREFIX
    ) -> str:
        return f"{prefix}{user_id}:{public_key}:{domain}"

    def _key(self, user_id: int, public_key: str, domain: str) -> str:
        return self.key(user_id, public_key, domain, self._prefix)

    async def get(
        self, user_id: int, public_key: str, domain: str
    ) -> Sep10Token | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(self._key(user_id, public_key, domain))
        except Exception as exc:  # noqa: BLE001 - cache must never break a flow
            logger.warning(f"SEP-10 token cache read failed: {exc}")
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return None
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            return None
        expires_at = payload.get("expires_at")
        token_obj = Sep10Token(
            token=token,
            expires_at=int(expires_at) if isinstance(expires_at, int) else None,
        )
        if self.is_expired(token_obj):
            return None
        return token_obj

    async def set(
        self,
        user_id: int,
        public_key: str,
        domain: str,
        token: Sep10Token,
    ) -> None:
        if self._redis is None:
            return
        ttl = self.ttl_seconds(token)
        if ttl <= 0:
            return
        payload = json.dumps({"token": token.token, "expires_at": token.expires_at})
        try:
            await self._redis.set(
                self._key(user_id, public_key, domain), payload, ex=ttl
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"SEP-10 token cache write failed: {exc}")

    async def delete(self, user_id: int, public_key: str, domain: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(self._key(user_id, public_key, domain))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"SEP-10 token cache drop failed: {exc}")

    def ttl_seconds(self, token: Sep10Token) -> int:
        """Cache lifetime, always shorter than the token itself."""
        if token.expires_at is None:
            return 0
        return int(token.expires_at - self._clock()) - self._skew_seconds

    def is_expired(self, token: Sep10Token) -> bool:
        if token.expires_at is None:
            return False
        return token.expires_at <= self._clock() + self._skew_seconds


def jwt_expires_at(token: str) -> int | None:
    """Read the unix `exp` claim of a JWT without verifying the signature."""
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode())
        claims = json.loads(raw)
    except (binascii.Error, ValueError, TypeError):
        return None
    exp = claims.get("exp")
    return int(exp) if isinstance(exp, (int, float)) else None

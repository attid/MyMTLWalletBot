import json

import pytest

from core.models.sep24 import Sep10Token
from infrastructure.services.sep24.token_store import Sep10TokenStore, jwt_expires_at


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.deleted = []

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.ttls[key] = ex

    async def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)


def make_store(redis, *, now: float = 1_000_000.0) -> Sep10TokenStore:
    return Sep10TokenStore(redis, clock=lambda: now)


def test_key_is_scoped_by_user_public_key_and_domain():
    key = Sep10TokenStore.key(42, "GPUBLIC", "anchor.test")

    assert key == "sep10:42:GPUBLIC:anchor.test"


@pytest.mark.asyncio
async def test_roundtrip_keeps_token_and_applies_ttl_minus_skew():
    redis = FakeRedis()
    store = make_store(redis)
    token = Sep10Token(token="JWT", expires_at=1_000_600)

    await store.set(7, "GPUBLIC", "anchor.test", token)
    loaded = await store.get(7, "GPUBLIC", "anchor.test")

    assert loaded == token
    assert redis.ttls["sep10:7:GPUBLIC:anchor.test"] == 300


@pytest.mark.asyncio
async def test_expired_token_is_not_returned():
    redis = FakeRedis()
    store = make_store(redis)
    token = Sep10Token(token="JWT", expires_at=1_000_100)

    await store.set(7, "GPUBLIC", "anchor.test", token)

    assert await store.get(7, "GPUBLIC", "anchor.test") is None


@pytest.mark.asyncio
async def test_token_without_expiry_is_not_cached():
    redis = FakeRedis()
    store = make_store(redis)

    await store.set(7, "GPUBLIC", "anchor.test", Sep10Token(token="JWT"))

    assert redis.values == {}


@pytest.mark.asyncio
async def test_delete_drops_the_cached_token():
    redis = FakeRedis()
    store = make_store(redis)
    await store.set(
        7, "GPUBLIC", "anchor.test", Sep10Token(token="JWT", expires_at=1_000_600)
    )

    await store.delete(7, "GPUBLIC", "anchor.test")

    assert redis.deleted == ["sep10:7:GPUBLIC:anchor.test"]
    assert await store.get(7, "GPUBLIC", "anchor.test") is None


@pytest.mark.asyncio
async def test_store_without_redis_is_a_noop():
    store = Sep10TokenStore(None)

    await store.set(7, "GPUBLIC", "anchor.test", Sep10Token(token="JWT", expires_at=9))
    assert await store.get(7, "GPUBLIC", "anchor.test") is None
    await store.delete(7, "GPUBLIC", "anchor.test")


@pytest.mark.asyncio
async def test_cache_failure_never_breaks_the_flow():
    class BrokenRedis:
        async def get(self, key):
            raise RuntimeError("redis is down")

        async def set(self, key, value, ex=None):
            raise RuntimeError("redis is down")

        async def delete(self, key):
            raise RuntimeError("redis is down")

    store = make_store(BrokenRedis())
    token = Sep10Token(token="JWT", expires_at=1_000_600)

    await store.set(7, "GPUBLIC", "anchor.test", token)

    assert await store.get(7, "GPUBLIC", "anchor.test") is None


@pytest.mark.asyncio
async def test_corrupt_payload_is_ignored():
    redis = FakeRedis()
    store = make_store(redis)
    redis.values["sep10:7:GPUBLIC:anchor.test"] = "{not json"

    assert await store.get(7, "GPUBLIC", "anchor.test") is None


def test_jwt_expiry_is_read_from_payload():
    import base64

    payload = base64.urlsafe_b64encode(json.dumps({"exp": 1234}).encode()).decode()

    assert jwt_expires_at(f"header.{payload}.signature") == 1234
    assert jwt_expires_at("garbage") is None

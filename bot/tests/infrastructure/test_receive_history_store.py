"""Tests for the Redis-backed receive-invoice amount history."""

import fakeredis.aioredis
import pytest

from infrastructure.services.receive_history_store import (
    HISTORY_LIMIT,
    ReceiveHistoryStore,
    HistoryAmount,
)


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    subject = ReceiveHistoryStore(redis)
    yield subject, redis
    await redis.aclose()


def entry(amount: str, code: str, issuer: str | None = None) -> HistoryAmount:
    return HistoryAmount(amount=amount, asset_code=code, issuer=issuer)


@pytest.mark.asyncio
async def test_add_then_read_returns_newest_first(store):
    subject, _ = store
    await subject.add(42, entry("10", "EURMTL", "GISSUER"), now=1_000)
    await subject.add(42, entry("50", "USDT"), now=2_000)

    history = await subject.get_history(42)

    assert history == [
        entry("50", "USDT"),
        entry("10", "EURMTL", "GISSUER"),
    ]


@pytest.mark.asyncio
async def test_history_keeps_only_limit_entries(store):
    subject, _ = store
    for i in range(HISTORY_LIMIT + 3):
        await subject.add(42, entry(str(i), "EURMTL"), now=1_000 + i)

    history = await subject.get_history(42)

    assert len(history) == HISTORY_LIMIT
    assert history[0] == entry(str(HISTORY_LIMIT + 2), "EURMTL")
    assert history[-1] == entry(str(3), "EURMTL")


@pytest.mark.asyncio
async def test_duplicate_amount_and_asset_deduplicates(store):
    subject, _ = store
    await subject.add(42, entry("10", "EURMTL"), now=1_000)
    await subject.add(42, entry("10", "EURMTL"), now=2_000)

    history = await subject.get_history(42)

    assert history == [entry("10", "EURMTL")]


@pytest.mark.asyncio
async def test_re_add_moves_entry_to_newest(store):
    subject, _ = store
    await subject.add(42, entry("10", "EURMTL"), now=1_000)
    await subject.add(42, entry("50", "USDT"), now=2_000)
    await subject.add(42, entry("10", "EURMTL"), now=3_000)

    history = await subject.get_history(42)

    assert [h.amount for h in history] == ["10", "50"]


@pytest.mark.asyncio
async def test_same_amount_different_asset_kept_separately(store):
    subject, _ = store
    await subject.add(42, entry("10", "EURMTL"), now=1_000)
    await subject.add(42, entry("10", "USDT"), now=2_000)

    history = await subject.get_history(42)

    assert len(history) == 2


@pytest.mark.asyncio
async def test_invalid_entry_is_rejected(store):
    subject, _ = store
    await subject.add(42, entry("", "EURMTL"), now=1_000)
    await subject.add(42, entry("10", ""), now=1_000)

    assert await subject.get_history(42) == []


@pytest.mark.asyncio
async def test_corrupted_member_is_dropped_not_raised(store):
    subject, redis = store
    key = "receive_hist:42"
    await redis.zadd(key, {"not-json": 1_000})
    await subject.add(42, entry("10", "EURMTL"), now=2_000)

    history = await subject.get_history(42)

    assert history == [entry("10", "EURMTL")]
    assert not await redis.zscore(key, "not-json")


@pytest.mark.asyncio
async def test_key_expires_after_ttl(store):
    subject, redis = store
    await subject.add(42, entry("10", "EURMTL"), now=1_000)

    ttl = await redis.ttl("receive_hist:42")

    assert 0 < ttl <= 30 * 24 * 3600


@pytest.mark.asyncio
async def test_users_are_isolated(store):
    subject, _ = store
    await subject.add(42, entry("10", "EURMTL"), now=1_000)
    await subject.add(43, entry("20", "USDT"), now=1_000)

    assert await subject.get_history(42) == [entry("10", "EURMTL")]
    assert await subject.get_history(43) == [entry("20", "USDT")]

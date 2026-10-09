"""Tests for InternalApi (username -> address read-only endpoint)."""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from infrastructure.services.internal_api import normalize_username

TOKEN = "test-token-123"


@pytest.fixture
def patch_db_pool(monkeypatch):
    """Replace module-level db_pool with a controllable fake.

    Two-step lookup (custom address, then default wallet) = two
    session.execute() calls per request; the stub returns results in
    order.

    holder["user_rows"]: row of (user_id, default_address) or None.
    holder["wallet_rows"]: row of (public_key,) or None (2nd query).
    holder["db_error"]: raise instead of executing, when set.
    """
    import infrastructure.services.internal_api as mod

    holder: dict = {"user_rows": None, "wallet_rows": None, "db_error": None}

    @asynccontextmanager
    async def fake_session():
        session = MagicMock()

        # Plain stand-in for SQLAlchemy Row: real __getitem__/truthiness.
        def stub_for(rows):
            row = tuple(rows) if rows else None
            return type("RowStub", (), {"first": staticmethod(lambda: row)})()

        call_index = {"n": 0}

        async def execute(stmt):
            if holder["db_error"] is not None:
                raise holder["db_error"]
            which = "user_rows" if call_index["n"] == 0 else "wallet_rows"
            call_index["n"] += 1
            rows = holder[which]
            return stub_for(rows)

        session.execute = execute
        yield session

    fake = MagicMock()
    fake.get_session = fake_session
    monkeypatch.setattr(mod, "db_pool", fake)
    return holder


@pytest.fixture
async def client(patch_db_pool):
    import infrastructure.services.internal_api as mod

    api = mod.InternalApi(TOKEN)
    async with TestClient(TestServer(api.create_app())) as c:
        yield c


@pytest.mark.asyncio
async def test_missing_token_returns_401(client):
    resp = await client.get("/api/v1/address/alice")
    assert resp.status == 401
    assert (await resp.json()) == {"error": "unauthorized"}


@pytest.mark.asyncio
async def test_wrong_token_returns_401(client):
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": "nope"})
    assert resp.status == 401


@pytest.mark.asyncio
async def test_known_user_returns_address(client, patch_db_pool):
    address = "G" + "A" * 55  # valid 56-char stellar public key shape
    patch_db_pool["user_rows"] = [42, address]
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 200
    assert (await resp.json()) == {"username": "alice", "address": address}


@pytest.mark.asyncio
async def test_unknown_user_returns_404(client):
    resp = await client.get("/api/v1/address/nobody", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404
    assert (await resp.json()) == {"error": "not_found"}


@pytest.mark.asyncio
async def test_user_without_address_falls_back_to_default_wallet(client, patch_db_pool):
    # Custom address empty -> handler must return the default wallet's
    # public key (the bot's own payment path, like get_default_wallet).
    wallet_key = "G" + "B" * 55
    patch_db_pool["user_rows"] = [42, ""]
    patch_db_pool["wallet_rows"] = [wallet_key]
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 200
    assert (await resp.json()) == {"username": "alice", "address": wallet_key}


@pytest.mark.asyncio
async def test_invalid_custom_address_falls_back_to_default_wallet(
    client, patch_db_pool
):
    # 'S'-prefixed 56-char value is a secret seed, never a public key:
    # custom address is unusable -> default wallet must be returned.
    wallet_key = "G" + "B" * 55
    patch_db_pool["user_rows"] = [42, "S" + "A" * 55]
    patch_db_pool["wallet_rows"] = [wallet_key]
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 200
    assert (await resp.json())["address"] == wallet_key


@pytest.mark.asyncio
async def test_null_address_falls_back_to_default_wallet(client, patch_db_pool):
    wallet_key = "G" + "B" * 55
    patch_db_pool["user_rows"] = [42, None]
    patch_db_pool["wallet_rows"] = [wallet_key]
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 200
    assert (await resp.json())["address"] == wallet_key


@pytest.mark.asyncio
async def test_unknown_user_skips_wallet_query(client, patch_db_pool):
    # No such user: must 404 after ONE query; the wallet fallback query
    # with user_id IS NULL must never run (orphaned wallet rows with
    # default_wallet=1 would otherwise leak as 200).
    patch_db_pool["user_rows"] = None
    patch_db_pool["wallet_rows"] = ["G" + "B" * 55]
    resp = await client.get("/api/v1/address/nobody", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404
    assert (await resp.json()) == {"error": "not_found"}


@pytest.mark.asyncio
async def test_invalid_wallet_key_falls_through_to_404(client, patch_db_pool):
    # Default wallet stores a seed-shaped/garbage value instead of a
    # public key: not payable -> 404.
    for bad in ["S" + "B" * 55, "bad_len"]:
        patch_db_pool["user_rows"] = [42, None]
        patch_db_pool["wallet_rows"] = [bad]
        resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
        assert resp.status == 404


@pytest.mark.asyncio
async def test_padded_wallet_key_is_stripped(client, patch_db_pool):
    wallet_key = "G" + "B" * 55
    patch_db_pool["user_rows"] = [42, None]
    patch_db_pool["wallet_rows"] = ["  " + wallet_key + "  "]
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 200
    assert (await resp.json())["address"] == wallet_key


@pytest.mark.asyncio
async def test_user_without_address_and_wallet_returns_404(client, patch_db_pool):
    # No custom address AND no default wallet -> same 404 as unknown user.
    patch_db_pool["user_rows"] = [42, ""]
    patch_db_pool["wallet_rows"] = None
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404
    assert (await resp.json()) == {"error": "not_found"}


@pytest.mark.asyncio
async def test_username_normalized(client, patch_db_pool):
    patch_db_pool["user_rows"] = [42, "G" + "A" * 55]
    resp = await client.get("/api/v1/address/@Alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 200
    body = await resp.json()
    assert body["username"] == "alice"


def test_normalize_username_strips_at_and_lowers():
    assert normalize_username("@Alice") == "alice"
    assert normalize_username("Bob") == "bob"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["@", "@@", "%20"])
async def test_empty_username_returns_404_without_db(client, patch_db_pool, raw):
    # Users without a Telegram username are stored with user_name = "";
    # a bare "@" request must never match them.
    patch_db_pool["user_rows"] = [42, "G" + "A" * 55]
    resp = await client.get(f"/api/v1/address/{raw}", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["@@alice", "@@@alice", "%E2%84%AA", "%C2%B2"])
async def test_lookalike_usernames_never_reach_db(client, patch_db_pool, raw):
    # '@@alice' must not strip to 'alice'; U+212A (KELVIN SIGN) must not
    # fold to 'k', U+00B2 must not survive at all: all -> 404, no DB match.
    patch_db_pool["user_rows"] = [42, "G" + "A" * 55]
    resp = await client.get(f"/api/v1/address/{raw}", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404


@pytest.mark.asyncio
async def test_header_name_is_case_insensitive(client, patch_db_pool):
    patch_db_pool["user_rows"] = [42, "G" + "A" * 55]
    resp = await client.get("/api/v1/address/alice", headers={"x-api-token": TOKEN})
    assert resp.status == 200


@pytest.mark.asyncio
async def test_trailing_slash_url_is_plain_404_by_router(client):
    # aiohttp cannot match an empty path segment: GET /api/v1/address/ falls
    # through to the default router 404 (text/plain), before token checking.
    # Documented in docs/api/internal-api.md; not part of the JSON contract.
    resp = await client.get("/api/v1/address/")
    assert resp.status == 404
    assert resp.content_type != "application/json"


@pytest.mark.asyncio
async def test_db_failure_returns_500_json(client, patch_db_pool):
    import infrastructure.services.internal_api as mod
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def failing_session():
        raise RuntimeError("DB down")
        yield

    mod.db_pool.get_session = failing_session
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 500
    assert (await resp.json()) == {"error": "internal"}


@pytest.mark.asyncio
async def test_padded_valid_address_is_stripped(client, patch_db_pool):
    patch_db_pool["user_rows"] = [42, "  " + "G" + "A" * 55 + "  "]
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 200
    assert (await resp.json())["address"] == "G" + "A" * 55


@pytest.mark.asyncio
@pytest.mark.parametrize("addr", ["   ", "G" + "A" * 54, "G" + "A" * 56])
async def test_invalid_address_returns_404(client, patch_db_pool, addr):
    patch_db_pool["user_rows"] = [42, addr]
    patch_db_pool["wallet_rows"] = None  # no wallet -> still 404
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404


@pytest.mark.asyncio
async def test_secret_seed_shaped_value_returns_404(client, patch_db_pool):
    # 56 chars starting with 'S' is a Stellar secret seed, not a public key.
    patch_db_pool["user_rows"] = [42, "S" + "A" * 55]
    patch_db_pool["wallet_rows"] = None  # no wallet -> still 404
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404
    assert (await resp.json()) == {"error": "not_found"}


@pytest.mark.asyncio
async def test_null_address_returns_404(client, patch_db_pool):
    patch_db_pool["user_rows"] = [42, None]
    patch_db_pool["wallet_rows"] = None  # no wallet -> still 404
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["alice-bob", "alice bob", "alice!", "алиса", "a" * 33])
async def test_invalid_username_chars_return_404(client, patch_db_pool, raw):
    patch_db_pool["user_rows"] = [42, "G" + "A" * 55]
    resp = await client.get(f"/api/v1/address/{raw}", headers={"X-Api-Token": TOKEN})
    assert resp.status == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["a", "a" * 32])
async def test_username_length_boundaries_pass_regex(client, patch_db_pool, raw):
    address = "G" + "A" * 55
    patch_db_pool["user_rows"] = [42, address]
    resp = await client.get(f"/api/v1/address/{raw}", headers={"X-Api-Token": TOKEN})
    # Only a regex pass reaches the DB and yields 200; a regex reject would
    # also be 404, so assert on 200 to actually pin the boundary behaviour.
    assert resp.status == 200
    assert (await resp.json())["address"] == address


@pytest.mark.asyncio
async def test_post_method_not_allowed(client):
    resp = await client.post("/api/v1/address/alice", headers={"X-Api-Token": TOKEN})
    assert resp.status == 405


@pytest.mark.asyncio
async def test_non_ascii_token_returns_401_not_500(client):
    resp = await client.get(
        "/api/v1/address/alice", headers={"X-Api-Token": "токен-🔥"}
    )
    assert resp.status == 401


@pytest.mark.asyncio
async def test_stop_before_start_is_safe():
    import infrastructure.services.internal_api as mod

    api = mod.InternalApi(TOKEN)
    await api.stop()  # must not raise AttributeError


@pytest.mark.asyncio
async def test_stop_is_idempotent():
    import infrastructure.services.internal_api as mod

    api = mod.InternalApi(TOKEN)
    await api.start("127.0.0.1", 0)  # port 0: OS picks a free one
    await api.stop()
    await api.stop()  # second call: no-op, no raise


@pytest.mark.asyncio
async def test_start_failure_cleans_up_runner():
    import socket

    import infrastructure.services.internal_api as mod

    # Occupy a port with a plain socket, so a second bind raises OSError.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        api = mod.InternalApi(TOKEN)
        with pytest.raises(OSError):
            await api.start("127.0.0.1", port)
        assert api._runner is None  # runner cleaned up after failed bind


@pytest.mark.asyncio
async def test_double_start_raises_instead_of_leaking_runner():
    import infrastructure.services.internal_api as mod

    api = mod.InternalApi(TOKEN)
    await api.start("127.0.0.1", 0)
    with pytest.raises(RuntimeError):
        await api.start("127.0.0.1", 0)
    await api.stop()


@pytest.mark.asyncio
async def test_empty_token_header_returns_401(client):
    resp = await client.get("/api/v1/address/alice", headers={"X-Api-Token": ""})
    assert resp.status == 401
    assert (await resp.json()) == {"error": "unauthorized"}


@pytest.mark.asyncio
async def test_username_with_digits_and_underscore_succeeds(client, patch_db_pool):
    address = "G" + "A" * 55
    patch_db_pool["user_rows"] = [42, address]
    resp = await client.get("/api/v1/address/Alice_123", headers={"X-Api-Token": TOKEN})
    assert resp.status == 200
    assert (await resp.json()) == {"username": "alice_123", "address": address}

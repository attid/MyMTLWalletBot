"""DeName HTTP boundary and index freshness policy."""

from datetime import datetime, timedelta, timezone

import aiohttp
import pytest

from infrastructure.services.dename_service import DeNameResolutionError, DeNameService

ADDRESS = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
CONTRACT = "C" + "A" * 55


class FakeResponse:
    def __init__(self, status: int, payload: object):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses: dict[str, list[FakeResponse | Exception]]):
        self.responses = responses
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def get(self, url: str):
        self.calls.append(url)
        result = self.responses[url].pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_responses(
    *, address=ADDRESS, status="active", age_seconds=0, stream_status="idle"
):
    now = datetime.now(timezone.utc)
    updated_at = (now - timedelta(seconds=age_seconds)).isoformat()
    name = {
        "fullName": "alice.ns",
        "owner": "G" + "A" * 55,
        "status": status,
        "expiration": (now + timedelta(days=1)).isoformat(),
        "tldContractId": CONTRACT,
        "lastEventLedger": 100,
        "records": {"forward": address},
    }
    indexer = {
        "streams": [
            {
                "streamName": "root-registry",
                "contractId": "C" + "B" * 55,
                "lastProcessedLedger": 101,
                "status": stream_status,
                "updatedAt": updated_at,
            },
            {
                "streamName": f"tld-base:ns:{CONTRACT}",
                "contractId": CONTRACT,
                "lastProcessedLedger": 101,
                "status": stream_status,
                "updatedAt": updated_at,
            },
        ]
    }
    return {
        "https://api.example/api/v1/names/alice.ns": [FakeResponse(200, name)],
        "https://api.example/api/v1/indexer/status": [FakeResponse(200, indexer)],
    }


@pytest.mark.asyncio
async def test_resolve_uses_forward_address_and_checks_indexer(monkeypatch):
    session = FakeSession(make_responses())
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_kwargs: session)

    result = await DeNameService("https://api.example/api/v1").resolve(" Alice.NS ")

    assert result.name == "alice.ns"
    assert result.address == ADDRESS
    assert session.calls == [
        "https://api.example/api/v1/names/alice.ns",
        "https://api.example/api/v1/indexer/status",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"address": None}, "unresolved"),
        ({"address": "GINVALID"}, "unresolved"),
        ({"status": "grace"}, "inactive"),
        ({"age_seconds": 180}, "stale"),
        ({"stream_status": "failed"}, "stale"),
    ],
)
async def test_resolve_rejects_unusable_records(monkeypatch, changes, expected):
    session = FakeSession(make_responses(**changes))
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_kwargs: session)

    with pytest.raises(DeNameResolutionError) as error:
        await DeNameService("https://api.example/api/v1").resolve("alice.ns")
    assert error.value.reason == expected


@pytest.mark.asyncio
async def test_unknown_name_is_distinct_and_not_retried(monkeypatch):
    responses = make_responses()
    name_url = "https://api.example/api/v1/names/alice.ns"
    responses[name_url] = [FakeResponse(404, {})]
    session = FakeSession(responses)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_kwargs: session)

    with pytest.raises(DeNameResolutionError) as error:
        await DeNameService("https://api.example/api/v1").resolve("alice.ns")
    assert error.value.reason == "unknown"
    assert session.calls == [name_url]


@pytest.mark.asyncio
async def test_malformed_api_response_is_distinct(monkeypatch):
    responses = make_responses()
    responses["https://api.example/api/v1/names/alice.ns"] = [
        FakeResponse(200, {"fullName": "alice.ns"})
    ]
    monkeypatch.setattr(
        aiohttp, "ClientSession", lambda **_kwargs: FakeSession(responses)
    )

    with pytest.raises(DeNameResolutionError) as error:
        await DeNameService("https://api.example/api/v1").resolve("alice.ns")
    assert error.value.reason == "invalid_response"


@pytest.mark.asyncio
async def test_network_error_retries_once_then_fails_unavailable(monkeypatch):
    responses = make_responses()
    name_url = "https://api.example/api/v1/names/alice.ns"
    responses[name_url] = [
        aiohttp.ClientConnectionError("offline"),
        aiohttp.ClientConnectionError("offline"),
    ]
    session = FakeSession(responses)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_kwargs: session)

    with pytest.raises(DeNameResolutionError) as error:
        await DeNameService("https://api.example/api/v1").resolve("alice.ns")
    assert error.value.reason == "unavailable"
    assert session.calls == [name_url, name_url]


@pytest.mark.asyncio
async def test_server_error_has_one_retry(monkeypatch):
    responses = make_responses()
    name_url = "https://api.example/api/v1/names/alice.ns"
    responses[name_url].insert(0, FakeResponse(503, {}))
    session = FakeSession(responses)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_kwargs: session)

    result = await DeNameService("https://api.example/api/v1").resolve("alice.ns")
    assert result.address == ADDRESS
    assert session.calls.count(name_url) == 2


@pytest.mark.parametrize(
    "url", ["http://api.example/api/v1", "https://api.example/testnet/api/v1"]
)
def test_mainnet_api_url_required(url):
    with pytest.raises(ValueError):
        DeNameService(url)


@pytest.mark.asyncio
async def test_unconfigured_and_invalid_names_fail_closed():
    service = DeNameService(None)
    with pytest.raises(DeNameResolutionError) as error:
        await service.resolve("alice.ns")
    assert error.value.reason == "unavailable"
    with pytest.raises(DeNameResolutionError) as error:
        await service.resolve("alice..ns")
    assert error.value.reason == "invalid"

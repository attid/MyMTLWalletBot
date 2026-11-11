import pytest

from infrastructure.services.sep24.client import (
    AnchorTransactionRequestError,
    Sep24Client,
    build_url,
)


class Recorder:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    async def __call__(
        self,
        method,
        url,
        *,
        params=None,
        headers=None,
        data=None,
        json=None,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "headers": headers,
                "data": data,
                "json": json,
            }
        )
        if url in self.responses:
            value = self.responses[url]
            if isinstance(value, Exception):
                raise value
            return value
        raise AssertionError(f"unexpected url: {url}")


@pytest.mark.asyncio
async def test_challenge_request_queries_account_and_asset():
    recorder = Recorder(
        {
            "https://anchor.test/auth": {
                "transaction": "CHALLENGE_XDR",
                "network_passphrase": "Test SDF Network ; September 2015",
            }
        }
    )
    client = Sep24Client(fetch_json=recorder)

    challenge = await client.fetch_challenge(
        "https://anchor.test/auth", account="GPUBLIC", asset_code="yXLM"
    )

    assert challenge.xdr == "CHALLENGE_XDR"
    assert challenge.network_passphrase == "Test SDF Network ; September 2015"
    assert recorder.calls[0]["params"] == {"account": "GPUBLIC", "asset_code": "yXLM"}


@pytest.mark.asyncio
async def test_token_exchange_posts_form_and_reads_expiry_from_jwt():
    exp = 2_000_000_000
    import base64
    import json

    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode()
    token = f"header.{payload}.signature"
    recorder = Recorder({"https://anchor.test/auth": {"token": token}})
    client = Sep24Client(fetch_json=recorder)

    result = await client.exchange_token("https://anchor.test/auth", "SIGNED_XDR")

    assert result.token == token
    assert result.expires_at == exp
    assert recorder.calls[0]["data"] == {"transaction": "SIGNED_XDR"}
    assert recorder.calls[0]["json"] is None


@pytest.mark.asyncio
async def test_interactive_creation_sends_json_body_with_bearer_token():
    recorder = Recorder(
        {
            "https://anchor.test/sep24/transactions/deposit/interactive": {
                "url": "https://anchor.test/interactive/1",
                "id": "tx-1",
                "type": "interactive_customer_info_needed",
            }
        }
    )
    client = Sep24Client(fetch_json=recorder)

    session = await client.create_interactive(
        "https://anchor.test/sep24/",
        direction="deposit",
        asset_code="yXLM",
        account="GPUBLIC",
        amount="10",
        lang="ru",
        token="JWT",
    )

    assert session.url == "https://anchor.test/interactive/1"
    assert session.transaction_id == "tx-1"
    assert session.kind == "interactive_customer_info_needed"
    call = recorder.calls[0]
    assert call["data"] is None
    assert call["json"] == {
        "asset_code": "yXLM",
        "account": "GPUBLIC",
        "amount": "10",
        "lang": "ru",
    }
    assert call["headers"] == {"Authorization": "Bearer JWT"}
    assert call["url"] == "https://anchor.test/sep24/transactions/deposit/interactive"


@pytest.mark.asyncio
async def test_interactive_creation_requires_url():
    recorder = Recorder(
        {"https://anchor.test/sep24/transactions/withdraw/interactive": {"id": "tx"}}
    )
    client = Sep24Client(fetch_json=recorder)

    with pytest.raises(ValueError):
        await client.create_interactive(
            "https://anchor.test/sep24",
            direction="withdraw",
            asset_code="USDM",
            account="GPUBLIC",
        )


@pytest.mark.asyncio
async def test_transaction_read_uses_id_and_asset_code():
    recorder = Recorder(
        {"https://anchor.test/sep24/transaction": {"transaction": {"id": "tx-1"}}}
    )
    client = Sep24Client(fetch_json=recorder)

    payload = await client.fetch_transaction(
        "https://anchor.test/sep24",
        transaction_id="tx-1",
        asset_code="yXLM",
        token="JWT",
        lang="en",
    )

    assert payload["transaction"]["id"] == "tx-1"
    assert recorder.calls[0]["params"] == {
        "id": "tx-1",
        "asset_code": "yXLM",
        "lang": "en",
    }


@pytest.mark.asyncio
async def test_unexpected_status_raises_typed_error_with_auth_flag():
    recorder = Recorder(
        {
            "https://anchor.test/sep24/transactions": AnchorTransactionRequestError(
                url="https://anchor.test/sep24/transactions",
                status=401,
                body={"error": "authentication_required"},
            )
        }
    )
    client = Sep24Client(fetch_json=recorder)

    with pytest.raises(AnchorTransactionRequestError) as exc_info:
        await client.fetch_transactions("https://anchor.test/sep24", asset_code="yXLM")

    assert exc_info.value.is_auth_error is True


def test_query_params_are_appended_to_an_existing_query_string():
    assert (
        build_url("https://anchor.test/auth?network=pubnet", {"account": "G1"})
        == "https://anchor.test/auth?network=pubnet&account=G1"
    )
    assert (
        build_url("https://anchor.test/auth", {"account": "G1"})
        == "https://anchor.test/auth?account=G1"
    )
    assert build_url("https://anchor.test/auth", None) == "https://anchor.test/auth"

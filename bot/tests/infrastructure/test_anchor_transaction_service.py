from collections import defaultdict

import pytest
from stellar_sdk import Keypair

from core.domain.value_objects import Asset
from core.models.anchor_asset import AnchorAssetSupport, SepProtocol, SepProtocolSupport
from core.models.anchor_transaction import AnchorTransactionProtocol
from infrastructure.services.anchor_transaction_service import (
    AnchorTransactionRequestError,
    AnchorTransactionService,
)


@pytest.mark.asyncio
async def test_fetch_transactions_reads_sep6_and_sep24_history():
    calls = defaultdict(int)

    async def fetch_json(
        method, url, *, params=None, headers=None, data=None, json=None
    ):
        calls[(method, url)] += 1
        assert params == {"asset_code": "BTCLN"}
        assert headers is None
        assert data is None
        if url == "https://anchor.test/sep6/transactions":
            return {
                "transactions": [
                    {
                        "id": "sep6-1",
                        "kind": "deposit",
                        "status": "completed",
                        "amount_in": "10",
                        "updated_at": "2026-05-23T10:00:00Z",
                    }
                ]
            }
        if url == "https://anchor.test/sep24/transactions":
            return {
                "transactions": [
                    {
                        "id": "sep24-1",
                        "kind": "withdrawal",
                        "status": "pending_user",
                        "amount_out": "20",
                        "more_info_url": "https://anchor.test/more/sep24-1",
                    }
                ]
            }
        raise AssertionError(f"unexpected URL: {url}")

    service = AnchorTransactionService(fetch_json=fetch_json)
    support = AnchorAssetSupport(
        asset=Asset("BTCLN", "GISSUER"),
        anchor_domain="anchor.test",
        web_auth_endpoint=None,
        sep6=SepProtocolSupport(
            protocol=SepProtocol.SEP6,
            transfer_server="https://anchor.test/sep6",
        ),
        sep24=SepProtocolSupport(
            protocol=SepProtocol.SEP24,
            transfer_server="https://anchor.test/sep24",
        ),
    )

    transactions = await service.fetch_transactions(support, Keypair.random())

    assert [tx.id for tx in transactions] == ["sep6-1", "sep24-1"]
    assert transactions[0].protocol.value == "SEP-6"
    assert transactions[1].protocol.value == "SEP-24"
    assert calls[("GET", "https://anchor.test/sep6/transactions")] == 1
    assert calls[("GET", "https://anchor.test/sep24/transactions")] == 1


@pytest.mark.asyncio
async def test_fetch_transactions_keeps_successful_protocol_when_other_fails():
    async def fetch_json(
        method, url, *, params=None, headers=None, data=None, json=None
    ):
        if url == "https://anchor.test/sep6/transactions":
            raise AnchorTransactionRequestError(
                url=url,
                status=403,
                body={"type": "authentication_required"},
            )
        if url == "https://anchor.test/sep24/transactions":
            return {"transactions": [{"id": "sep24-1", "status": "completed"}]}
        raise AssertionError(f"unexpected URL: {url}")

    service = AnchorTransactionService(fetch_json=fetch_json)
    support = AnchorAssetSupport(
        asset=Asset("yXLM", "GISSUER"),
        anchor_domain="anchor.test",
        web_auth_endpoint=None,
        sep6=SepProtocolSupport(
            protocol=SepProtocol.SEP6,
            transfer_server="https://anchor.test/sep6",
        ),
        sep24=SepProtocolSupport(
            protocol=SepProtocol.SEP24,
            transfer_server="https://anchor.test/sep24",
        ),
    )

    transactions = await service.fetch_transactions(support, Keypair.random())

    assert [tx.id for tx in transactions] == ["sep24-1"]
    assert transactions[0].protocol is AnchorTransactionProtocol.SEP24


@pytest.mark.asyncio
async def test_start_sep24_interactive_sends_json_body_with_account():
    calls = []
    keypair = Keypair.random()

    async def fetch_json(
        method, url, *, params=None, headers=None, data=None, json=None
    ):
        calls.append((method, url, params, headers, data, json))
        if url == "https://anchor.test/sep24/transactions/deposit/interactive":
            return {
                "url": "https://anchor.test/interactive/deposit/1",
                "id": "tx-1",
                "type": "interactive_customer_info_needed",
            }
        raise AssertionError(f"unexpected URL: {url}")

    service = AnchorTransactionService(fetch_json=fetch_json)
    support = AnchorAssetSupport(
        asset=Asset("yXLM", "GISSUER"),
        anchor_domain="anchor.test",
        web_auth_endpoint=None,
        sep24=SepProtocolSupport(
            protocol=SepProtocol.SEP24,
            transfer_server="https://anchor.test/sep24",
        ),
    )

    session_result = await service.start_sep24_interactive(
        support,
        keypair,
        operation="deposit",
    )

    assert session_result.url == "https://anchor.test/interactive/deposit/1"
    assert session_result.transaction_id == "tx-1"
    assert session_result.kind == "interactive_customer_info_needed"
    assert calls == [
        (
            "POST",
            "https://anchor.test/sep24/transactions/deposit/interactive",
            None,
            None,
            None,
            {"asset_code": "yXLM", "account": keypair.public_key},
        )
    ]


class TokenAnchor:
    """Fake anchor that issues SEP-10 tokens and counts challenge requests."""

    def __init__(self, *, server: Keypair, reject_tokens: int = 0):
        from stellar_sdk import Network
        from stellar_sdk.sep.stellar_web_authentication import (
            build_challenge_transaction,
        )

        self.server = server
        self.network = Network.PUBLIC_NETWORK_PASSPHRASE
        self.build_challenge = build_challenge_transaction
        self.challenges = 0
        self.tokens = 0
        self.reject_tokens = reject_tokens
        self.sep24_requests = []

    async def fetch_json(
        self, method, url, *, params=None, headers=None, data=None, json=None
    ):
        if url == "https://anchor.test/auth" and method == "GET":
            self.challenges += 1
            return {
                "transaction": self.build_challenge(
                    self.server.secret,
                    params["account"],
                    "anchor.test",
                    "anchor.test",
                    self.network,
                ),
                "network_passphrase": self.network,
            }
        if url == "https://anchor.test/auth" and method == "POST":
            from stellar_sdk import TransactionEnvelope

            self.assert_signed_by_client(
                TransactionEnvelope.from_xdr(data["transaction"], self.network)
            )
            self.tokens += 1
            return {"token": f"JWT-{self.tokens}", "expires_at": 2_000_000_000}
        if url == "https://anchor.test/sep24/transactions/deposit/interactive":
            self.sep24_requests.append(headers)
            if self.reject_tokens:
                self.reject_tokens -= 1
                raise AnchorTransactionRequestError(
                    url=url, status=401, body={"error": "authentication_required"}
                )
            return {"url": "https://anchor.test/i/1", "id": "tx-1"}
        if url == "https://anchor.test/sep24/transaction":
            return {"transaction": {"id": params["id"], "status": "completed"}}
        raise AssertionError(f"unexpected request: {method} {url}")

    def assert_signed_by_client(self, envelope):
        assert envelope.transaction.operations


def make_support(*, signing_key: str | None = "GSERVER") -> AnchorAssetSupport:
    return AnchorAssetSupport(
        asset=Asset("yXLM", "GISSUER"),
        anchor_domain="anchor.test",
        web_auth_endpoint="https://anchor.test/auth",
        signing_key=signing_key,
        sep24=SepProtocolSupport(
            protocol=SepProtocol.SEP24,
            transfer_server="https://anchor.test/sep24",
        ),
    )


class FakeTokenStore:
    def __init__(self):
        self.values = {}
        self.deleted = []

    async def get(self, user_id, public_key, domain):
        return self.values.get((user_id, public_key, domain))

    async def set(self, user_id, public_key, domain, token):
        self.values[(user_id, public_key, domain)] = token

    async def delete(self, user_id, public_key, domain):
        self.deleted.append((user_id, public_key, domain))
        self.values.pop((user_id, public_key, domain), None)


@pytest.mark.asyncio
async def test_sep10_token_is_cached_per_user_and_wallet():
    from core.models.sep24 import Sep10Token
    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionService,
    )

    server = Keypair.random()
    anchor = TokenAnchor(server=server)
    store = FakeTokenStore()
    keypair = Keypair.random()
    service = AnchorTransactionService(fetch_json=anchor.fetch_json, token_store=store)
    support = AnchorAssetSupport(
        asset=Asset("yXLM", "GISSUER"),
        anchor_domain="anchor.test",
        web_auth_endpoint="https://anchor.test/auth",
        signing_key=server.public_key,
        sep24=SepProtocolSupport(
            protocol=SepProtocol.SEP24,
            transfer_server="https://anchor.test/sep24",
        ),
    )

    first = await service.start_sep24_interactive(
        support, keypair, operation="deposit", user_id=1
    )
    second = await service.start_sep24_interactive(
        support, keypair, operation="deposit", user_id=1
    )

    assert first.transaction_id == "tx-1"
    assert second.transaction_id == "tx-1"
    assert anchor.challenges == 1
    assert store.values[(1, keypair.public_key, "anchor.test")] == Sep10Token(
        token="JWT-1", expires_at=2_000_000_000
    )


@pytest.mark.asyncio
async def test_rejected_token_is_dropped_and_reissued_once():
    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionService,
    )

    server = Keypair.random()
    anchor = TokenAnchor(server=server, reject_tokens=1)
    store = FakeTokenStore()
    keypair = Keypair.random()
    service = AnchorTransactionService(fetch_json=anchor.fetch_json, token_store=store)
    support = make_support(signing_key=server.public_key)

    result = await service.start_sep24_interactive(
        support, keypair, operation="deposit", user_id=1
    )

    assert result.url == "https://anchor.test/i/1"
    assert anchor.challenges == 2
    assert anchor.tokens == 2
    assert store.deleted == [(1, keypair.public_key, "anchor.test")]


@pytest.mark.asyncio
async def test_unverified_challenge_is_signed_and_counted():
    from infrastructure.services.anchor_transaction_service import (
        SEP10_VERIFICATION_FAILURES,
        AnchorTransactionService,
    )

    server = Keypair.random()
    anchor = TokenAnchor(server=server)
    service = AnchorTransactionService(fetch_json=anchor.fetch_json)
    keypair = Keypair.random()
    support = make_support(signing_key=None)
    before = sum(SEP10_VERIFICATION_FAILURES.values())

    token = await service.authenticate(support, keypair)

    assert token == "JWT-1"
    assert sum(SEP10_VERIFICATION_FAILURES.values()) == before + 1
    assert SEP10_VERIFICATION_FAILURES["missing_signing_key"] >= 1


@pytest.mark.asyncio
async def test_challenge_for_another_account_is_rejected_before_signing():
    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionService,
    )
    from infrastructure.services.sep24 import Sep10ChallengeRejected

    server = Keypair.random()
    anchor = TokenAnchor(server=server)
    foreign_account = Keypair.random().public_key

    async def fetch_json(method, url, *, params=None, **kwargs):
        if method == "GET" and url == "https://anchor.test/auth":
            params = {**(params or {}), "account": foreign_account}
        return await anchor.fetch_json(method, url, params=params, **kwargs)

    service = AnchorTransactionService(fetch_json=fetch_json)
    support = make_support(signing_key=server.public_key)

    with pytest.raises(Sep10ChallengeRejected):
        await service.authenticate(support, Keypair.random())


@pytest.mark.asyncio
async def test_sep24_transaction_read_uses_cached_token():
    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionService,
    )

    server = Keypair.random()
    anchor = TokenAnchor(server=server)
    store = FakeTokenStore()
    keypair = Keypair.random()
    service = AnchorTransactionService(fetch_json=anchor.fetch_json, token_store=store)
    support = make_support(signing_key=server.public_key)

    await service.start_sep24_interactive(
        support, keypair, operation="deposit", user_id=1
    )
    view = await service.fetch_sep24_transaction(
        support, transaction_id="tx-1", keypair=keypair, user_id=1
    )

    assert view.id == "tx-1"
    assert view.status == "completed"
    assert anchor.challenges == 1


@pytest.mark.asyncio
async def test_cached_status_read_requires_reauth_without_token():
    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionService,
        Sep24ReauthRequired,
    )

    server = Keypair.random()
    anchor = TokenAnchor(server=server)
    service = AnchorTransactionService(
        fetch_json=anchor.fetch_json, token_store=FakeTokenStore()
    )

    with pytest.raises(Sep24ReauthRequired):
        await service.fetch_sep24_transaction_cached(
            make_support(signing_key=server.public_key),
            transaction_id="tx-1",
            user_id=1,
            public_key=Keypair.random().public_key,
        )


@pytest.mark.asyncio
async def test_cached_status_read_uses_stored_token():
    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionService,
    )

    server = Keypair.random()
    anchor = TokenAnchor(server=server)
    store = FakeTokenStore()
    keypair = Keypair.random()
    service = AnchorTransactionService(fetch_json=anchor.fetch_json, token_store=store)
    support = make_support(signing_key=server.public_key)
    await service.start_sep24_interactive(
        support, keypair, operation="deposit", user_id=1
    )

    view = await service.fetch_sep24_transaction_cached(
        support,
        transaction_id="tx-1",
        user_id=1,
        public_key=keypair.public_key,
    )

    assert view.status == "completed"
    assert anchor.challenges == 1


@pytest.mark.asyncio
async def test_payment_inside_challenge_is_never_signed():
    """Regression for the review P1: a real payment XDR must not be signed."""
    from stellar_sdk import Account, Asset, Network, TransactionBuilder

    from infrastructure.services.anchor_transaction_service import (
        AnchorTransactionService,
    )
    from infrastructure.services.sep24 import Sep10ChallengeRejected

    server = Keypair.random()
    victim = Keypair.random()
    attacker = Keypair.random()
    posted = []

    async def fetch_json(
        method, url, *, params=None, headers=None, data=None, json=None
    ):
        if method == "GET" and url == "https://anchor.test/auth":
            builder = TransactionBuilder(
                Account(server.public_key, 42), Network.PUBLIC_NETWORK_PASSPHRASE, 100
            )
            builder.append_payment_op(attacker.public_key, Asset.native(), "1000")
            return {
                "transaction": builder.build().to_xdr(),
                "network_passphrase": Network.PUBLIC_NETWORK_PASSPHRASE,
            }
        if method == "POST" and url == "https://anchor.test/auth":
            posted.append(data)
            return {"token": "JWT"}
        raise AssertionError(f"unexpected request: {method} {url}")

    service = AnchorTransactionService(fetch_json=fetch_json)
    support = make_support(signing_key=server.public_key)

    with pytest.raises(Sep10ChallengeRejected):
        await service.authenticate(support, victim)

    assert posted == []

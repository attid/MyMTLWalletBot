import pytest
from stellar_sdk import Keypair, Network
from stellar_sdk.sep.stellar_web_authentication import build_challenge_transaction

from core.models.sep24 import Sep10Challenge
from infrastructure.services.sep24.challenge import (
    Sep10ChallengeAccountMismatch,
    Sep10ChallengeInvalid,
    expected_home_domains,
    verify_sep10_challenge,
)


def make_challenge(
    client_account: str,
    *,
    server: Keypair,
    home_domain: str = "anchor.test",
    web_auth_domain: str = "auth.anchor.test",
) -> Sep10Challenge:
    return Sep10Challenge(
        xdr=build_challenge_transaction(
            server.secret,
            client_account,
            home_domain,
            web_auth_domain,
            Network.PUBLIC_NETWORK_PASSPHRASE,
        ),
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
    )


def test_expected_home_domains_includes_web_auth_host():
    assert expected_home_domains("anchor.test", "https://auth.anchor.test/auth") == [
        "anchor.test",
        "auth.anchor.test",
    ]


def test_verified_when_signing_key_matches_challenge_source():
    server = Keypair.random()
    client = Keypair.random()
    challenge = make_challenge(client.public_key, server=server)

    result = verify_sep10_challenge(
        challenge,
        account=client.public_key,
        anchor_domain="anchor.test",
        web_auth_endpoint="https://auth.anchor.test/auth",
        signing_key=server.public_key,
    )

    assert result.verified is True
    assert result.client_account_id == client.public_key


def test_web_auth_host_from_another_domain_is_accepted():
    """Ultra Capital serves /auth from a host different from home_domain."""
    server = Keypair.random()
    client = Keypair.random()
    challenge = make_challenge(client.public_key, server=server)

    result = verify_sep10_challenge(
        challenge,
        account=client.public_key,
        anchor_domain="ultracapital.xyz",
        web_auth_endpoint="https://auth.anchor.test/auth",
        signing_key=server.public_key,
    )

    assert result.verified is False
    assert "home domain" in (result.reason or "").lower()


def test_missing_signing_key_is_soft_and_reports_reason():
    server = Keypair.random()
    client = Keypair.random()
    challenge = make_challenge(client.public_key, server=server)

    result = verify_sep10_challenge(
        challenge,
        account=client.public_key,
        anchor_domain="anchor.test",
        web_auth_endpoint="https://auth.anchor.test/auth",
        signing_key=None,
    )

    assert result.verified is False
    assert result.reason == "missing_signing_key"
    assert result.client_account_id == client.public_key


def test_account_mismatch_is_a_hard_error():
    server = Keypair.random()
    challenge = make_challenge(Keypair.random().public_key, server=server)

    with pytest.raises(Sep10ChallengeAccountMismatch):
        verify_sep10_challenge(
            challenge,
            account=Keypair.random().public_key,
            anchor_domain="anchor.test",
            signing_key=server.public_key,
        )


def test_wrong_server_signing_key_is_not_verified():
    server = Keypair.random()
    client = Keypair.random()
    challenge = make_challenge(client.public_key, server=server)

    result = verify_sep10_challenge(
        challenge,
        account=client.public_key,
        anchor_domain="anchor.test",
        web_auth_endpoint="https://auth.anchor.test/auth",
        signing_key=Keypair.random().public_key,
    )

    assert result.verified is False


def test_unparsable_challenge_is_rejected():
    with pytest.raises(Sep10ChallengeInvalid):
        verify_sep10_challenge(
            Sep10Challenge(
                xdr="not-an-xdr",
                network_passphrase="Test SDF Network ; September 2015",
            ),
            account=Keypair.random().public_key,
            anchor_domain="anchor.test",
            signing_key=Keypair.random().public_key,
        )


def test_challenge_with_unparsable_xdr_is_rejected_even_without_signing_key():
    with pytest.raises(Sep10ChallengeInvalid):
        verify_sep10_challenge(
            Sep10Challenge(
                xdr="garbage", network_passphrase="Test SDF Network ; September 2015"
            ),
            account=Keypair.random().public_key,
            anchor_domain="anchor.test",
            signing_key=None,
        )


def test_payment_transaction_is_rejected_before_signing():
    """A real payment (sequence > 0, Payment op) must never be signed."""
    from stellar_sdk import Account, Asset, TransactionBuilder

    server = Keypair.random()
    builder = TransactionBuilder(
        Account(server.public_key, 42), Network.PUBLIC_NETWORK_PASSPHRASE, 100
    )
    builder.append_payment_op(Keypair.random().public_key, Asset.native(), "1000")

    with pytest.raises(Sep10ChallengeInvalid):
        verify_sep10_challenge(
            Sep10Challenge(
                xdr=builder.build().to_xdr(),
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            ),
            account=Keypair.random().public_key,
            anchor_domain="anchor.test",
            signing_key=server.public_key,
        )


def test_manage_data_without_operation_source_is_rejected():
    from stellar_sdk import Account, TransactionBuilder

    server = Keypair.random()
    builder = TransactionBuilder(
        Account(server.public_key, 0), Network.PUBLIC_NETWORK_PASSPHRASE, 100
    )
    builder.add_time_bounds(min_time=0, max_time=2_000_000_000)
    builder.append_manage_data_op(data_name="anchor.test auth", data_value=b"nonce")

    with pytest.raises(Sep10ChallengeInvalid):
        verify_sep10_challenge(
            Sep10Challenge(
                xdr=builder.build().to_xdr(),
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            ),
            account=Keypair.random().public_key,
            anchor_domain="anchor.test",
            signing_key=server.public_key,
        )

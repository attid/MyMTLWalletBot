"""Soft (C2) verification of SEP-10 challenge transactions.

The bot signs a challenge with a user key, so before signing it must be sure the
XDR really is a challenge for *this* account. Two different things are checked:

* **Structural invariants — always strict.** The envelope must parse, the
  transaction sequence number must be zero, and the first operation must be a
  `ManageData` op with an explicit source. A failure here means the anchor sent
  something that is not a SEP-10 challenge (e.g. a real payment), and signing it
  would hand the anchor a signature over arbitrary code.
* **Anchor trust — deliberately soft (C2).** Home-domain/`web_auth_domain`
  matching, timebounds and the server signature are verified only when the
  anchor publishes `SIGNING_KEY`; failures are reported as `verified=False` so
  the caller can log them and still sign. Live anchors deviate from the spec
  (Ultra Capital serves `/auth` from a different host than the challenge domain),
  so a hard failure here would break working integrations.
"""

from typing import Any
from urllib.parse import urlparse

from stellar_sdk import TransactionEnvelope
from stellar_sdk.operation import ManageData
from stellar_sdk.sep.exceptions import InvalidSep10ChallengeError
from stellar_sdk.sep.stellar_web_authentication import read_challenge_transaction

from core.models.sep24 import ChallengeVerification, Sep10Challenge


class Sep10ChallengeRejected(Exception):
    """Base class for challenges that must never be signed."""


class Sep10ChallengeAccountMismatch(Sep10ChallengeRejected):
    """The challenge was issued for another account; signing it is pointless."""


class Sep10ChallengeInvalid(Sep10ChallengeRejected):
    """The payload is not a structurally valid SEP-10 challenge."""


def expected_home_domains(
    anchor_domain: str | None, web_auth_endpoint: str | None
) -> list[str]:
    """Domains accepted in the challenge `manage_data` operation name."""
    domains: list[str] = []
    for candidate in (anchor_domain, _host(web_auth_endpoint)):
        if candidate and candidate not in domains:
            domains.append(candidate)
    return domains


def challenge_client_account(challenge_xdr: str, network_passphrase: str) -> str:
    """Return the account the challenge is bound to.

    Raises `Sep10ChallengeInvalid` when the payload is not a well-formed
    SEP-10 challenge: an unparsable envelope, a non-zero sequence number, a
    first operation that is not `ManageData`, or a missing operation source all
    make the XDR unsafe to sign.
    """
    try:
        envelope = TransactionEnvelope.from_xdr(challenge_xdr, network_passphrase)
    except Exception as exc:  # noqa: BLE001 - anchors send arbitrary XDR
        raise Sep10ChallengeInvalid(f"challenge XDR is not parsable: {exc}") from exc

    transaction = envelope.transaction
    if transaction.sequence != 0:
        raise Sep10ChallengeInvalid(
            f"challenge sequence must be zero, got {transaction.sequence}"
        )
    operations = transaction.operations
    if not operations or not isinstance(operations[0], ManageData):
        raise Sep10ChallengeInvalid("challenge first operation must be ManageData")
    source = getattr(operations[0], "source", None)
    if source is None:
        raise Sep10ChallengeInvalid("challenge operation must have a source account")
    return source.account_muxed or source.account_id


def verify_sep10_challenge(
    challenge: Sep10Challenge,
    *,
    account: str,
    anchor_domain: str | None,
    web_auth_endpoint: str | None = None,
    signing_key: str | None = None,
) -> ChallengeVerification:
    """Verify a SEP-10 challenge as far as the published anchor data allows."""
    client_account = challenge_client_account(
        challenge.xdr, challenge.network_passphrase
    )
    if client_account != account:
        raise Sep10ChallengeAccountMismatch(
            f"challenge is bound to {client_account}, not to {account}"
        )

    if not signing_key:
        return ChallengeVerification(
            verified=False,
            reason="missing_signing_key",
            client_account_id=client_account,
        )

    domains = expected_home_domains(anchor_domain, web_auth_endpoint)
    if not domains:
        return ChallengeVerification(
            verified=False,
            reason="missing_home_domain",
            client_account_id=client_account,
        )

    try:
        read_challenge_transaction(
            challenge.xdr,
            signing_key,
            domains,
            _host(web_auth_endpoint) or domains[0],
            challenge.network_passphrase,
        )
    except (InvalidSep10ChallengeError, ValueError) as exc:
        return ChallengeVerification(
            verified=False,
            reason=str(exc),
            client_account_id=client_account,
        )
    return ChallengeVerification(verified=True, client_account_id=client_account)


def _host(url: str | None) -> str | None:
    if not url:
        return None
    parsed: Any = urlparse(url)
    return parsed.netloc or parsed.path or None

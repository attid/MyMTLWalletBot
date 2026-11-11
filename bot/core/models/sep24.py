"""SEP-24/SEP-10 value objects shared by the bot protocol adapters."""

import re
from dataclasses import dataclass
from typing import Mapping

# SEP-24 statuses, including the legacy names that live anchors still return
# (`pending_user_transfer_start` instead of `pending_user_transfer`).
SEP24_STATUS_I18N_KEYS: Mapping[str, str] = {
    "incomplete": "sep24_status_incomplete",
    "pending_user_transfer_start": "sep24_status_pending_user_transfer",
    "pending_user_transfer_complete": "sep24_status_pending_user_transfer",
    "pending_user_transfer": "sep24_status_pending_user_transfer",
    "pending_anchor": "sep24_status_pending_anchor",
    "pending_stellar": "sep24_status_pending_stellar",
    "pending_external": "sep24_status_pending_external",
    "pending_trust": "sep24_status_pending_trust",
    "pending_user": "sep24_status_pending_user",
    "pending_customer_info_update": "sep24_status_pending_customer_info",
    "pending_transaction_info_update": "sep24_status_pending_customer_info",
    "on_hold": "sep24_status_on_hold",
    "completed": "sep24_status_completed",
    "refunded": "sep24_status_refunded",
    "expired": "sep24_status_expired",
    "error": "sep24_status_failed",
    "no_market": "sep24_status_no_market",
    "too_small": "sep24_status_too_small",
    "too_large": "sep24_status_too_large",
}

SEP24_STATUS_FALLBACK_I18N_KEY = "sep24_status_unknown"

# Anchor errors that deserve their own user-facing wording.
SEP24_ERROR_I18N_KEYS: Mapping[str, str] = {
    "authentication_required": "sep24_error_authentication",
    "invalid_token": "sep24_error_authentication",
    "permission_denied": "sep24_error_authentication",
    "asset_not_supported": "sep24_error_asset",
    "invalid_asset": "sep24_error_asset",
    "transaction_not_found": "sep24_error_not_found",
    "too_small": "sep24_status_too_small",
    "too_large": "sep24_status_too_large",
    "no_market": "sep24_status_no_market",
}

SEP24_ERROR_FALLBACK_I18N_KEY = "sep24_error_generic"

# Statuses in which the anchor is waiting for the user's on-chain payment.
# Instructions must be shown only here: anchors keep the addresses in the
# payload after a transaction is completed or closed.
SEP24_PENDING_USER_TRANSFER_STATUSES = frozenset(
    {
        "incomplete",
        "pending_user_transfer_start",
        "pending_user_transfer",
    }
)

_MUXED_ADDRESS_RE = re.compile(r"^M[A-Z2-7]{68}$")

# Bot languages are not always ISO 639-1; SEP-24 `lang` is only a hint.
SEP24_LANG_ALIASES: Mapping[str, str] = {
    "ua": "uk",
    "me": "sr",
    "am": "hy",
}


@dataclass(frozen=True)
class Sep10Challenge:
    """A fetched SEP-10 challenge transaction."""

    xdr: str
    network_passphrase: str


@dataclass(frozen=True)
class Sep10Token:
    """A SEP-10 JWT plus its expiry (unix seconds) when the anchor reports it."""

    token: str
    expires_at: int | None = None


@dataclass(frozen=True)
class ChallengeVerification:
    """Result of the soft (C2) SEP-10 challenge verification."""

    verified: bool
    reason: str | None = None
    client_account_id: str | None = None


@dataclass(frozen=True)
class InteractiveSession:
    """Response of `POST /transactions/{deposit,withdraw}/interactive`."""

    url: str
    transaction_id: str | None = None
    kind: str | None = None


@dataclass(frozen=True)
class PaymentInstructions:
    """Where the user has to send funds for a SEP-24 transaction."""

    destination: str
    memo: str | None = None
    memo_type: str | None = None
    asset_code: str | None = None
    asset_issuer: str | None = None
    amount: str | None = None
    source: str = "instructions"

    @property
    def is_muxed(self) -> bool:
        return is_muxed_address(self.destination)


@dataclass(frozen=True)
class Sep24TransactionView:
    """Anchor transaction rendered for the user (status + instructions)."""

    id: str
    kind: str | None = None
    status: str | None = None
    amount_in: str | None = None
    amount_out: str | None = None
    amount_fee: str | None = None
    more_info_url: str | None = None
    message: str | None = None
    instructions: PaymentInstructions | None = None
    stellar_transaction_id: str | None = None
    external_transaction_id: str | None = None

    @property
    def status_i18n_key(self) -> str:
        return sep24_status_i18n_key(self.status)


def sep24_status_i18n_key(status: str | None) -> str:
    """Map an anchor status to a localization key."""
    if not status:
        return SEP24_STATUS_FALLBACK_I18N_KEY
    return SEP24_STATUS_I18N_KEYS.get(
        status.strip().lower(), SEP24_STATUS_FALLBACK_I18N_KEY
    )


def is_muxed_address(destination: str | None) -> bool:
    """True for a 69-character muxed `M...` Stellar account address."""
    return bool(destination and _MUXED_ADDRESS_RE.match(destination))


def sep24_known_error_i18n_key(error_code: str | None) -> str | None:
    """Localization key for a *known* anchor error code, else None."""
    if not error_code:
        return None
    return SEP24_ERROR_I18N_KEYS.get(str(error_code).strip().lower())


def awaits_user_transfer(status: str | None) -> bool:
    """True when the anchor is waiting for the user's payment."""
    if not status:
        return False
    return status.strip().lower() in SEP24_PENDING_USER_TRANSFER_STATUSES


def sep24_error_i18n_key(error_code: str | None) -> str:
    """Map an anchor error code to a localization key."""
    if not error_code:
        return SEP24_ERROR_FALLBACK_I18N_KEY
    return SEP24_ERROR_I18N_KEYS.get(
        str(error_code).strip().lower(), SEP24_ERROR_FALLBACK_I18N_KEY
    )


def sep24_lang_hint(language: str | None) -> str | None:
    """Translate a bot language into a SEP-24 `lang` hint."""
    if not language:
        return None
    normalized = language.strip().lower()
    if not normalized:
        return None
    return SEP24_LANG_ALIASES.get(normalized, normalized)

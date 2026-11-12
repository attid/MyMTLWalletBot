"""On-chain provisioning for free Stellar wallets.

A free wallet is written to the DB first (fast, crash-safe), then activated on
the Stellar network: `create_account` funded from the master wallet, trustlines
for the project assets and notifier subscription.

Callers must hold `other.locks.new_wallet_lock`: every transaction is submitted
from the same master account, so concurrent provisioning would race on the
master account sequence number.
"""

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from loguru import logger

from core.constants import EURMTL_ASSET, MTL_ASSET, SATSMTL_ASSET, USDM_ASSET

FREE_WALLET_STARTING_BALANCE = "5"
FREE_WALLET_ASSETS = (MTL_ASSET, EURMTL_ASSET, SATSMTL_ASSET, USDM_ASSET)
ACCOUNT_CREATE_ATTEMPTS = 3


class WalletProvisioningError(RuntimeError):
    """Free wallet could not be fully provisioned on-chain."""

    def __init__(self, step: str, cause: Exception) -> None:
        super().__init__(f"{step}: {cause}")
        self.step = step
        self.cause = cause


@dataclass
class ProvisionResult:
    public_key: str
    account_created: bool
    account_existed: bool
    trustlines_created: int


def missing_free_wallet_assets(
    account_details: Optional[dict[str, Any]],
) -> list[str]:
    """Return asset codes from FREE_WALLET_ASSETS that the account lacks."""
    if not account_details:
        return [asset.code for asset in FREE_WALLET_ASSETS]
    present = {
        (balance.get("asset_code"), balance.get("asset_issuer"))
        for balance in account_details.get("balances", [])
        if balance.get("asset_type") not in (None, "native")
    }
    return [
        asset.code
        for asset in FREE_WALLET_ASSETS
        if (asset.code, asset.issuer) not in present
    ]


def _is_account_already_exists(error: Exception) -> bool:
    """Detect Horizon 'account already exists' after a lost submit response."""
    markers = ("op_already_exists", "already exist")
    text = str(error).lower()
    if any(marker in text for marker in markers):
        return True
    extras = getattr(error, "extras", None)
    if isinstance(extras, dict):
        result_codes = extras.get("result_codes") or {}
        operations = result_codes.get("operations") or []
        return any("already_exists" in str(code) for code in operations)
    return False


async def _submit_create_account_with_retries(
    *,
    service: Any,
    user_id: int,
    source_account_id: str,
    destination_account_id: str,
    master_secret: str,
    attempts: int = ACCOUNT_CREATE_ATTEMPTS,
) -> None:
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            logger.info(
                "wallet_stellar_account_create_attempt user_id={} public_key={} source_account={} attempt={}/{}",
                user_id,
                destination_account_id,
                source_account_id,
                attempt,
                attempts,
            )
            xdr = await service.build_payment_transaction(
                source_account_id=source_account_id,
                destination_account_id=destination_account_id,
                asset_code="XLM",
                asset_issuer=None,
                amount=FREE_WALLET_STARTING_BALANCE,
                create_account=True,
            )
            signed_xdr = await service.sign_transaction(xdr, master_secret)
            response = await service.submit_transaction(signed_xdr)
            if response.get("successful", True) is False:
                raise RuntimeError(f"Horizon rejected create_account: {response}")
            logger.info(
                "wallet_stellar_account_created user_id={} public_key={} source_account={} attempt={}",
                user_id,
                destination_account_id,
                source_account_id,
                attempt,
            )
            return
        except Exception as e:
            last_error = e
            if _is_account_already_exists(e) and await service.check_account_exists(
                destination_account_id
            ):
                logger.info(
                    "wallet_stellar_account_created user_id={} public_key={} source_account={} attempt={} already_exists=true",
                    user_id,
                    destination_account_id,
                    source_account_id,
                    attempt,
                )
                return
            logger.warning(
                "wallet_stellar_account_create_attempt_failed user_id={} public_key={} source_account={} attempt={}/{} error_type={} error={}",
                user_id,
                destination_account_id,
                source_account_id,
                attempt,
                attempts,
                type(e).__name__,
                e,
            )

    if last_error is None:  # defensive: attempts <= 0
        raise WalletProvisioningError(
            "submit_create_account",
            RuntimeError("no create_account attempts were made"),
        )
    raise WalletProvisioningError("submit_create_account", last_error)


async def ensure_provisioned(
    *,
    stellar_service: Any,
    encryption_service: Any,
    wallet_repository: Any,
    notification_service: Any,
    user_id: int,
    public_key: str,
    secret_key: str,
    account_exists: bool = False,
    assets: Optional[Sequence[Any]] = None,
) -> ProvisionResult:
    """Activate a free wallet on-chain and make it usable.

    Args:
        account_exists: caller-known account state. Pass False for a freshly
            generated keypair. Callers that already loaded account details must
            pass their result so this function never probes Horizon again under
            `new_wallet_lock`.
        assets: trustlines to create. Defaults to all project assets; retries pass
            only the assets that are actually missing.
    """
    provision_assets = tuple(FREE_WALLET_ASSETS if assets is None else assets)
    logger.info(
        "wallet_provision_start user_id={} public_key={} account_exists={} assets={}",
        user_id,
        public_key,
        account_exists,
        ",".join(asset.code for asset in provision_assets),
    )

    if account_exists:
        logger.info(
            "wallet_provision_account_exists user_id={} public_key={}",
            user_id,
            public_key,
        )
    else:
        try:
            master_wallet = await wallet_repository.get_default_wallet(0)
        except Exception as e:
            raise WalletProvisioningError("load_master_wallet", e) from e
        if master_wallet is None or not master_wallet.secret_key:
            raise WalletProvisioningError(
                "load_master_wallet",
                RuntimeError("master wallet with secret key not found"),
            )
        try:
            master_secret = encryption_service.decrypt(master_wallet.secret_key, "0")
        except Exception as e:
            raise WalletProvisioningError("decrypt_master_secret", e) from e
        if not master_secret:
            raise WalletProvisioningError(
                "decrypt_master_secret",
                RuntimeError("master wallet secret decryption returned empty value"),
            )

        await _submit_create_account_with_retries(
            service=stellar_service,
            user_id=user_id,
            source_account_id=master_wallet.public_key,
            destination_account_id=public_key,
            master_secret=master_secret,
        )

    if notification_service is not None:
        try:
            await notification_service.subscribe(public_key)
            logger.info(
                "wallet_notification_subscribed user_id={} public_key={}",
                user_id,
                public_key,
            )
        except Exception as e:
            # Subscription must not leave the user with a DB-only wallet.
            logger.warning(
                "wallet_notification_subscribe_failed user_id={} public_key={} error_type={} error={}",
                user_id,
                public_key,
                type(e).__name__,
                e,
            )

    trustlines_created = 0
    for asset in provision_assets:
        logger.info(
            "wallet_trustline_create_start user_id={} public_key={} asset_code={}",
            user_id,
            public_key,
            asset.code,
        )
        try:
            trust_xdr = await stellar_service.build_change_trust_transaction(
                source_account_id=public_key,
                asset_code=asset.code,
                asset_issuer=asset.issuer,
            )
            signed_trust = await stellar_service.sign_transaction(trust_xdr, secret_key)
            await stellar_service.submit_transaction(signed_trust)
        except Exception as e:
            logger.warning(
                "wallet_trustline_failed user_id={} public_key={} asset_code={} error_type={} error={}",
                user_id,
                public_key,
                asset.code,
                type(e).__name__,
                e,
            )
            raise WalletProvisioningError(f"trustline_{asset.code}", e) from e
        trustlines_created += 1
        logger.info(
            "wallet_trustline_created user_id={} public_key={} asset_code={}",
            user_id,
            public_key,
            asset.code,
        )

    logger.info(
        "wallet_trustlines_created user_id={} public_key={} count={}",
        user_id,
        public_key,
        trustlines_created,
    )
    logger.info(
        "wallet_provision_completed user_id={} public_key={} account_created={} account_existed={} trustlines={}",
        user_id,
        public_key,
        not account_exists,
        account_exists,
        trustlines_created,
    )
    return ProvisionResult(
        public_key=public_key,
        account_created=not account_exists,
        account_existed=account_exists,
        trustlines_created=trustlines_created,
    )

from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

from infrastructure.services.free_wallet_provisioning import (
    FREE_WALLET_ASSETS,
    WalletProvisioningError,
    ensure_provisioned,
    missing_free_wallet_assets,
)

MASTER_PUBLIC_KEY = "GAXLST7ZHHXGQGIIRJYICL4PRDFB4Q7KVL65HX6BN6DELPYOJEHZSPSG"
USER_PUBLIC_KEY = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
# Placeholder value: the fake stellar service signs nothing real, so this is not
# a key. Keep it low-entropy, otherwise the generic-api-key secret scan flags it.
MASTER_SECRET = "dummy"


class FakeStellarService:
    """Minimal Horizon double for provisioning tests."""

    def __init__(
        self,
        *,
        exists_checks: tuple[bool, ...] = (False,),
        fail_create_attempts: int = 0,
        create_error: str | None = None,
    ) -> None:
        self._checks = list(exists_checks)
        self._last_exists = False
        self.fail_create_attempts = fail_create_attempts
        self.create_error = create_error
        self.exists_checks: list[str] = []
        self.create_attempts = 0
        self.submitted: list[str] = []
        self.trustlines: list[str] = []

    async def check_account_exists(self, public_key: str) -> bool:
        self.exists_checks.append(public_key)
        if self._checks:
            self._last_exists = self._checks.pop(0)
        return self._last_exists

    async def build_payment_transaction(self, **kwargs) -> str:
        self.create_attempts += 1
        return "xdr-create"

    async def sign_transaction(self, xdr: str, secret: str) -> str:
        return f"signed:{xdr}"

    async def submit_transaction(self, xdr: str) -> dict:
        if xdr == "signed:xdr-create":
            if self.create_error is not None:
                raise RuntimeError(self.create_error)
            if self.create_attempts <= self.fail_create_attempts:
                raise RuntimeError("tx_bad_seq")
        self.submitted.append(xdr)
        return {"successful": True, "hash": "abc"}

    async def build_change_trust_transaction(
        self, source_account_id: str, asset_code: str, asset_issuer: str, limit=None
    ) -> str:
        self.trustlines.append(asset_code)
        return f"xdr-trust-{asset_code}"


@pytest.fixture
def stellar_service() -> FakeStellarService:
    return FakeStellarService()


@pytest.fixture
def master_wallet() -> MagicMock:
    wallet = MagicMock()
    wallet.public_key = MASTER_PUBLIC_KEY
    wallet.secret_key = "ENC_MASTER"
    return wallet


@pytest.fixture
def wallet_repository(master_wallet) -> MagicMock:
    repo = MagicMock()
    repo.get_default_wallet = AsyncMock(return_value=master_wallet)
    return repo


@pytest.fixture
def encryption_service() -> MagicMock:
    service = MagicMock()
    service.decrypt = MagicMock(return_value=MASTER_SECRET)
    return service


@pytest.fixture
def notification_service() -> MagicMock:
    service = MagicMock()
    service.subscribe = AsyncMock()
    return service


async def _provision(
    *,
    stellar_service,
    wallet_repository,
    encryption_service,
    notification_service,
    account_exists: bool = False,
    assets=None,
    secret_key: str = MASTER_SECRET,
):
    return await ensure_provisioned(
        stellar_service=stellar_service,
        encryption_service=encryption_service,
        wallet_repository=wallet_repository,
        notification_service=notification_service,
        user_id=123,
        public_key=USER_PUBLIC_KEY,
        secret_key=secret_key,
        account_exists=account_exists,
        assets=assets,
    )


def _capture_logs():
    messages: list[str] = []
    sink_id = logger.add(lambda m: messages.append(m.record["message"]), level="INFO")
    return messages, sink_id


async def test_creates_account_trustlines_and_subscription(
    stellar_service,
    wallet_repository,
    encryption_service,
    notification_service,
):
    logs, sink_id = _capture_logs()
    try:
        result = await _provision(
            stellar_service=stellar_service,
            wallet_repository=wallet_repository,
            encryption_service=encryption_service,
            notification_service=notification_service,
        )
    finally:
        logger.remove(sink_id)

    assert result.account_created is True
    assert result.account_existed is False
    assert result.trustlines_created == len(FREE_WALLET_ASSETS)
    assert stellar_service.create_attempts == 1
    assert stellar_service.trustlines == [a.code for a in FREE_WALLET_ASSETS]
    notification_service.subscribe.assert_awaited_once_with(USER_PUBLIC_KEY)
    assert any("wallet_provision_start" in m for m in logs)
    assert any("wallet_stellar_account_created" in m for m in logs)
    assert any("wallet_trustlines_created" in m for m in logs)
    assert any("wallet_provision_completed" in m for m in logs)


async def test_skips_create_account_when_account_exists(
    wallet_repository, encryption_service, notification_service
):
    stellar_service = FakeStellarService(exists_checks=(True,))

    result = await _provision(
        stellar_service=stellar_service,
        wallet_repository=wallet_repository,
        encryption_service=encryption_service,
        notification_service=notification_service,
        account_exists=True,
    )

    assert result.account_existed is True
    assert result.account_created is False
    assert stellar_service.create_attempts == 0
    wallet_repository.get_default_wallet.assert_not_awaited()
    assert stellar_service.trustlines == [a.code for a in FREE_WALLET_ASSETS]


async def test_creates_only_requested_assets(
    wallet_repository, encryption_service, notification_service
):
    """Retries pass only missing trustlines, not all project assets."""
    stellar_service = FakeStellarService(exists_checks=(True,))
    missing = [FREE_WALLET_ASSETS[-1]]

    result = await _provision(
        stellar_service=stellar_service,
        wallet_repository=wallet_repository,
        encryption_service=encryption_service,
        notification_service=notification_service,
        account_exists=True,
        assets=missing,
    )

    assert result.trustlines_created == 1
    assert stellar_service.trustlines == [missing[0].code]


async def test_retries_create_account_and_reports_step(
    wallet_repository, encryption_service, notification_service
):
    stellar_service = FakeStellarService(fail_create_attempts=3)

    with pytest.raises(WalletProvisioningError) as exc_info:
        await _provision(
            stellar_service=stellar_service,
            wallet_repository=wallet_repository,
            encryption_service=encryption_service,
            notification_service=notification_service,
        )

    assert exc_info.value.step == "submit_create_account"
    assert stellar_service.create_attempts == 3
    assert stellar_service.trustlines == []


async def test_lost_response_with_existing_account_counts_as_created(
    wallet_repository, encryption_service, notification_service
):
    stellar_service = FakeStellarService(
        exists_checks=(False, True), create_error="op_already_exists"
    )

    result = await _provision(
        stellar_service=stellar_service,
        wallet_repository=wallet_repository,
        encryption_service=encryption_service,
        notification_service=notification_service,
    )

    assert result.account_created is True
    assert stellar_service.trustlines == [a.code for a in FREE_WALLET_ASSETS]


async def test_subscription_failure_does_not_break_provisioning(
    stellar_service, wallet_repository, encryption_service
):
    notification_service = MagicMock()
    notification_service.subscribe = AsyncMock(
        side_effect=RuntimeError("notifier down")
    )

    result = await _provision(
        stellar_service=stellar_service,
        wallet_repository=wallet_repository,
        encryption_service=encryption_service,
        notification_service=notification_service,
    )

    assert result.trustlines_created == len(FREE_WALLET_ASSETS)


async def test_missing_master_wallet_raises_with_step(encryption_service):
    repo = MagicMock()
    repo.get_default_wallet = AsyncMock(return_value=None)

    with pytest.raises(WalletProvisioningError) as exc_info:
        await _provision(
            stellar_service=FakeStellarService(),
            wallet_repository=repo,
            encryption_service=encryption_service,
            notification_service=None,
        )

    assert exc_info.value.step == "load_master_wallet"


async def test_empty_master_secret_raises_with_step(
    wallet_repository, notification_service
):
    encryption_service = MagicMock()
    encryption_service.decrypt = MagicMock(return_value=None)

    with pytest.raises(WalletProvisioningError) as exc_info:
        await _provision(
            stellar_service=FakeStellarService(),
            wallet_repository=wallet_repository,
            encryption_service=encryption_service,
            notification_service=notification_service,
        )

    assert exc_info.value.step == "decrypt_master_secret"


async def test_trustline_failure_reports_asset_step(
    wallet_repository, encryption_service, notification_service
):
    stellar_service = FakeStellarService()
    first_asset = FREE_WALLET_ASSETS[0]

    async def failing_build_change_trust(
        source_account_id: str, asset_code: str, asset_issuer: str, limit=None
    ) -> str:
        if asset_code == first_asset.code:
            raise RuntimeError("horizon 502")
        return f"xdr-trust-{asset_code}"

    stellar_service.build_change_trust_transaction = (  # type: ignore[method-assign]
        failing_build_change_trust
    )

    with pytest.raises(WalletProvisioningError) as exc_info:
        await _provision(
            stellar_service=stellar_service,
            wallet_repository=wallet_repository,
            encryption_service=encryption_service,
            notification_service=notification_service,
        )

    assert exc_info.value.step == f"trustline_{first_asset.code}"
    assert stellar_service.trustlines == []


def test_missing_free_wallet_assets_detects_all_states():
    all_codes = [asset.code for asset in FREE_WALLET_ASSETS]

    assert missing_free_wallet_assets(None) == all_codes

    full_balances = [{"asset_type": "native", "balance": "5.0"}]
    for asset in FREE_WALLET_ASSETS:
        full_balances.append(
            {
                "asset_type": "credit_alphanum12",
                "asset_code": asset.code,
                "asset_issuer": asset.issuer,
                "balance": "0.0",
            }
        )
    assert missing_free_wallet_assets({"balances": full_balances}) == []

    partial = {"balances": full_balances[:-1]}
    assert missing_free_wallet_assets(partial) == [FREE_WALLET_ASSETS[-1].code]

    # Same code from a different issuer is not a valid project trustline.
    wrong_issuer = {
        "balances": [
            {
                "asset_type": "credit_alphanum12",
                "asset_code": FREE_WALLET_ASSETS[0].code,
                "asset_issuer": "GWRONGISSUER",
                "balance": "0.0",
            }
        ]
    }
    assert FREE_WALLET_ASSETS[0].code in missing_free_wallet_assets(wrong_issuer)

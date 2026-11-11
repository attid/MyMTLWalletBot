from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from core.domain.value_objects import Asset


class SepProtocol(str, Enum):
    SEP6 = "sep6"
    SEP24 = "sep24"


@dataclass(frozen=True)
class SepOperationSupport:
    enabled: bool
    min_amount: float | None = None
    max_amount: float | None = None
    fee_fixed: float | None = None
    fee_percent: float | None = None
    fields: dict[str, Any] | None = None
    types: dict[str, Any] | None = None


@dataclass(frozen=True)
class SepProtocolSupport:
    protocol: SepProtocol
    transfer_server: str
    # Asset code spelling advertised by the anchor (codes are case-sensitive,
    # e.g. `yXLM`), used verbatim in protocol requests.
    asset_code: str | None = None
    deposit: SepOperationSupport | None = None
    withdraw: SepOperationSupport | None = None
    transactions_enabled: bool = False

    @property
    def has_user_actions(self) -> bool:
        return bool(self.deposit or self.withdraw or self.transactions_enabled)


@dataclass(frozen=True)
class AnchorAssetSupport:
    asset: Asset
    anchor_domain: str
    web_auth_endpoint: str | None
    # SEP-1 `SIGNING_KEY`; without it the SEP-10 challenge cannot be verified.
    signing_key: str | None = None
    sep6: SepProtocolSupport | None = None
    sep24: SepProtocolSupport | None = None
    checked_at: datetime = datetime.now(UTC)

    @property
    def has_deposit(self) -> bool:
        return bool(
            (self.sep6 and self.sep6.deposit) or (self.sep24 and self.sep24.deposit)
        )

    @property
    def has_withdraw(self) -> bool:
        return bool(
            (self.sep6 and self.sep6.withdraw) or (self.sep24 and self.sep24.withdraw)
        )

    @property
    def has_transactions(self) -> bool:
        return bool(
            (self.sep6 and self.sep6.transactions_enabled)
            or (self.sep24 and self.sep24.transactions_enabled)
        )

    def asset_code_for(self, protocol: SepProtocol) -> str:
        """Return the asset code spelling used by this protocol."""
        support = self.sep24 if protocol is SepProtocol.SEP24 else self.sep6
        if support is not None and support.asset_code:
            return support.asset_code
        return self.asset.code

    @property
    def supported_protocols(self) -> list[SepProtocol]:
        protocols = []
        if self.sep6:
            protocols.append(SepProtocol.SEP6)
        if self.sep24:
            protocols.append(SepProtocol.SEP24)
        return protocols

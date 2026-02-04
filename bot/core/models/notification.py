from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class NotificationOperation:
    """
    Represents an operation for notification purposes.
    Replaces the legacy TOperations DB model.
    """
    id: str
    operation: str
    dt: datetime
    
    # Accounts
    from_account: Optional[str] = None
    for_account: Optional[str] = None
    
    # Payment
    payment_amount: float = 0.0
    payment_asset: str = "XLM"
    
    # Path Payment
    path_sent_amount: float = 0.0
    path_sent_asset: str = "XLM"
    path_received_amount: float = 0.0
    path_received_asset: str = "XLM"

    # Trade
    trade_bought_amount: float = 0.0
    trade_bought_asset: str = "XLM"
    trade_sold_amount: float = 0.0
    trade_sold_asset: str = "XLM"

    # Manage Offer
    # selling_asset is what we give, buying_asset is what we want
    offer_amount: float = 0.0
    offer_price: float = 0.0
    offer_selling_asset: str = "XLM"
    offer_buying_asset: str = "XLM"
    offer_id: int = 0

    # Manage Data
    data_name: Optional[str] = None
    data_value: Optional[str] = None
    
    transaction_hash: Optional[str] = None
    memo: Optional[str] = None

    @property
    def display_amount_value(self) -> float:
        """Helper for History Service: Primary amount to display depending on type."""
        if self.operation == "payment":
            return self.payment_amount
        if self.operation == "create_account":
            return self.payment_amount
        if self.operation in ("path_payment_strict_send", "path_payment_strict_receive"):
            return self.path_received_amount
        if self.operation == "trade":
            return self.trade_bought_amount
        if self.operation in ("manage_sell_offer", "manage_buy_offer"):
            return self.offer_amount
        return 0.0

    @property
    def display_asset_code(self) -> str:
        """Helper for History Service: Primary asset to display depending on type."""
        if self.operation == "payment":
            return self.payment_asset
        if self.operation == "create_account":
            return self.payment_asset
        if self.operation in ("path_payment_strict_send", "path_payment_strict_receive"):
            return self.path_received_asset
        if self.operation == "trade":
            return self.trade_bought_asset
        if self.operation in ("manage_sell_offer", "manage_buy_offer"):
            return self.offer_buying_asset
        # Let's keep consistent with "Buying Asset" for Offers in filters usually.
        # But wait, manage_sell_offer: selling X, buying Y.
        if self.operation == "manage_data":
            return self.data_name or "DATA"
        return "XLM"

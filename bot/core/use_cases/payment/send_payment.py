from typing import Optional
import math
from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService
from core.domain.value_objects import Asset, PaymentResult

class SendPayment:
    def __init__(self, wallet_repository: IWalletRepository, stellar_service: IStellarService):
        self.wallet_repository = wallet_repository
        self.stellar_service = stellar_service

    async def execute(self, user_id: int, destination_address: str, asset: Asset, amount: float, memo: Optional[str] = None, cancel_offers: bool = False, create_account: bool = False) -> PaymentResult:
        # 1. Validation
        if amount <= 0 or math.isinf(amount):
            return PaymentResult(success=False, error_message="Amount must be positive and finite (not unlimited)")
        
        # 2. Get User Wallet (Source)
        source_wallet = await self.wallet_repository.get_default_wallet(user_id)
        if not source_wallet:
            return PaymentResult(success=False, error_message="User wallet not found")
        
        # 3. Check Destination Exists
        exists = await self.stellar_service.check_account_exists(destination_address)
        
        if create_account:
             if exists:
                  # CreateAccount op fails if account exists.
                  return PaymentResult(success=False, error_message="Destination account already exists")
             if asset.code != "XLM":
                  return PaymentResult(success=False, error_message="Can only create account with XLM (native asset)")
        else:
             if not exists:
                  return PaymentResult(success=False, error_message="Destination account does not exist")

        # 4. Build XDR
        try:
            xdr = await self.stellar_service.build_payment_transaction(
                source_account_id=source_wallet.public_key,
                destination_account_id=destination_address,
                asset_code=asset.code,
                asset_issuer=asset.issuer,
                amount=str(amount),
                memo=memo,
                cancel_offers=cancel_offers,
                create_account=create_account
            )
            return PaymentResult(success=True, xdr=xdr)
        except Exception as e:
            return PaymentResult(success=False, error_message=str(e))

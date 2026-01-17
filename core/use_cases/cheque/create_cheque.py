from typing import Optional
from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService
from core.domain.value_objects import PaymentResult
from core.constants import CHEQUE_PUBLIC_KEY, EURMTL_ASSET

class CreateCheque:
    def __init__(self, wallet_repository: IWalletRepository, stellar_service: IStellarService):
        self.wallet_repository = wallet_repository
        self.stellar_service = stellar_service

    async def execute(self, user_id: int, amount: float, count: int, memo: str) -> PaymentResult:
        if amount <= 0:
            return PaymentResult(success=False, error_message="Amount must be positive")
        if count <= 0:
            return PaymentResult(success=False, error_message="Count must be positive")
            
        total_amount = amount * count
        
        source_wallet = await self.wallet_repository.get_default_wallet(user_id)
        if not source_wallet:
            return PaymentResult(success=False, error_message="User wallet not found")

        try:
            xdr = await self.stellar_service.build_payment_transaction(
                source_account_id=source_wallet.public_key,
                destination_account_id=CHEQUE_PUBLIC_KEY,
                asset_code=EURMTL_ASSET.code,
                asset_issuer=EURMTL_ASSET.issuer,
                amount=str(total_amount),
                memo=memo
            )
            return PaymentResult(success=True, xdr=xdr)
        except Exception as e:
            return PaymentResult(success=False, error_message=str(e))

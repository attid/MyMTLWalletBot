from typing import Optional
from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService
from core.domain.value_objects import Asset, PaymentResult

class SendPayment:
    def __init__(self, wallet_repository: IWalletRepository, stellar_service: IStellarService):
        self.wallet_repository = wallet_repository
        self.stellar_service = stellar_service

    async def execute(self, user_id: int, destination_address: str, asset: Asset, amount: float, memo: Optional[str] = None, cancel_offers: bool = False) -> PaymentResult:
        # 1. Validation
        if amount <= 0:
            return PaymentResult(success=False, error_message="Amount must be positive")
        
        # 2. Get User Wallet (Source)
        source_wallet = await self.wallet_repository.get_default_wallet(user_id)
        if not source_wallet:
            return PaymentResult(success=False, error_message="User wallet not found")
        
        # 3. Check Destination Exists (Optional, but good practice before building)
        # Some flows might require create_account if not exists, but 'SendPayment' usually implies payment to existing.
        # Router logic: "await stellar_check_account(send_address)" - if not exists, might try to activate/create.
        # For this primitive Use Case, let's assume strict payment. 
        # We can implement a separate "ActivateAccount" use case or handle it here.
        # Let's check existence.
        exists = await self.stellar_service.check_account_exists(destination_address)
        if not exists:
             # If destination doesn't exist, we might need to use 'create_account' op.
             # Clean Architecture: The decision to 'create' vs 'pay' is business logic.
             # If amount is enough to activate, we could switch op.
             # For Phase 2 simple migration, let's return error or handle creation if requested.
             # To match existing router behavior: `stellar_check_account` checks validation.
             # Then `stellar_pay` uses `create=True` if logic dictates.
             # Let's stick to standard payment for now, failure if not found.
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
                cancel_offers=cancel_offers
            )
            return PaymentResult(success=True, xdr=xdr)
        except Exception as e:
            return PaymentResult(success=False, error_message=str(e))

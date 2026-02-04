from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService
from core.domain.value_objects import Asset, PaymentResult

class ManageOffer:
    def __init__(self, wallet_repository: IWalletRepository, stellar_service: IStellarService):
        self.wallet_repository = wallet_repository
        self.stellar_service = stellar_service

    async def execute(
        self,
        user_id: int,
        selling: Asset,
        buying: Asset,
        amount: float,
        price: float,
        offer_id: int = 0
    ) -> PaymentResult:
        if amount < 0 or price < 0:
            return PaymentResult(success=False, error_message="Amount and price must be non-negative")
            
        source_wallet = await self.wallet_repository.get_default_wallet(user_id)
        if not source_wallet:
            return PaymentResult(success=False, error_message="User wallet not found")

        try:
            xdr = await self.stellar_service.manage_offer(
                source_account_id=source_wallet.public_key,
                selling=selling,
                buying=buying,
                amount=str(amount),
                price=str(price),
                offer_id=offer_id
            )
            return PaymentResult(success=True, xdr=xdr)
        except Exception as e:
            return PaymentResult(success=False, error_message=str(e))

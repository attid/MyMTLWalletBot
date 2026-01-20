import math
from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService
from core.domain.value_objects import Asset, PaymentResult

class SwapAssets:
    def __init__(self, wallet_repository: IWalletRepository, stellar_service: IStellarService):
        self.wallet_repository = wallet_repository
        self.stellar_service = stellar_service

    async def execute(
        self,
        user_id: int,
        send_asset: Asset,
        send_amount: float,
        receive_asset: Asset,
        receive_amount: float,
        strict_receive: bool = False,
        cancel_offers: bool = False
    ) -> PaymentResult:
        if send_amount <= 0 or receive_amount <= 0 or math.isinf(send_amount) or math.isinf(receive_amount):
            return PaymentResult(success=False, error_message="Amounts must be positive and finite")
            
        source_wallet = await self.wallet_repository.get_default_wallet(user_id)
        if not source_wallet:
            return PaymentResult(success=False, error_message="User wallet not found")

        try:
            xdr = await self.stellar_service.swap_assets(
                source_account_id=source_wallet.public_key,
                send_asset=send_asset,
                send_amount=str(send_amount),
                receive_asset=receive_asset,
                receive_amount=str(receive_amount),
                strict_receive=strict_receive,
                cancel_offers=cancel_offers
            )
            return PaymentResult(success=True, xdr=xdr)
        except Exception as e:
            return PaymentResult(success=False, error_message=str(e))

from typing import Optional
from dataclasses import dataclass
from core.interfaces.repositories import IWalletRepository, IChequeRepository
from core.interfaces.services import IStellarService, IEncryptionService
from core.domain.entities import ChequeStatus

@dataclass
class CancelResult:
    success: bool
    xdr: Optional[str] = None
    error_message: Optional[str] = None

class CancelCheque:
    def __init__(self, 
                 wallet_repository: IWalletRepository, 
                 cheque_repository: IChequeRepository,
                 stellar_service: IStellarService,
                 encryption_service: IEncryptionService,
                 cheque_public_key: str):
        self.wallet_repository = wallet_repository
        self.cheque_repository = cheque_repository
        self.stellar_service = stellar_service
        self.encryption_service = encryption_service
        self.cheque_public_key = cheque_public_key

    async def execute(self, user_id: int, cheque_uuid: str) -> CancelResult:
        cheque = await self.cheque_repository.get_by_uuid(cheque_uuid, user_id)
        if not cheque:
            return CancelResult(False, error_message="Cheque not found or access denied")
            
        if cheque.status == ChequeStatus.CANCELED.value:
             return CancelResult(False, error_message="Cheque already canceled")

        receive_count = await self.cheque_repository.get_receive_count(cheque_uuid)
        remaining_count = cheque.count - receive_count
        
        if remaining_count <= 0:
             return CancelResult(False, error_message="Nothing to cancel")

        # Cancel in DB
        success = await self.cheque_repository.cancel(cheque_uuid, user_id)
        if not success:
             return CancelResult(False, error_message="Failed to canel cheque")

        # Refund Payment
        wallet = await self.wallet_repository.get_default_wallet(user_id)
        if not wallet:
            return CancelResult(False, error_message="User wallet not found")

        if not cheque.asset:
            return CancelResult(False, error_message="Cheque asset not defined")

        refund_amount = remaining_count * float(cheque.amount)
        refund_amount_str = f"{refund_amount:.7f}"

        cheque_asset_parts = cheque.asset.split(':')

        tx_xdr = await self.stellar_service.build_payment_transaction(
            source_account_id=self.cheque_public_key,
            destination_account_id=wallet.public_key,
            asset_code=cheque_asset_parts[0],
            asset_issuer=cheque_asset_parts[1] if len(cheque_asset_parts) > 1 else None,
            amount=refund_amount_str,
            memo=cheque_uuid[:16]
        )

        master_wallet = await self.wallet_repository.get_default_wallet(0)
        if not master_wallet:
            return CancelResult(False, error_message="Master wallet not found")

        if not master_wallet.secret_key:
            return CancelResult(False, error_message="Master wallet secret not available")

        master_secret = self.encryption_service.decrypt(master_wallet.secret_key, "0")
        if not master_secret:
            return CancelResult(False, error_message="Failed to decrypt master secret")

        signed_xdr = await self.stellar_service.sign_xdr(tx_xdr, master_secret)
        
        return CancelResult(True, xdr=signed_xdr)

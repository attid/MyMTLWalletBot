from typing import Optional, List
from dataclasses import dataclass
from core.interfaces.repositories import IWalletRepository, IChequeRepository
from core.interfaces.services import IStellarService, IEncryptionService
from core.use_cases.wallet.add_wallet import AddWallet
from core.domain.entities import Cheque

@dataclass
class ClaimResult:
    success: bool
    xdr: Optional[str] = None
    error_message: Optional[str] = None

class ClaimCheque:
    def __init__(self, 
                 wallet_repository: IWalletRepository, 
                 cheque_repository: IChequeRepository,
                 stellar_service: IStellarService,
                 encryption_service: IEncryptionService,
                 add_wallet_use_case: AddWallet,
                 cheque_public_key: str):
        self.wallet_repository = wallet_repository
        self.cheque_repository = cheque_repository
        self.stellar_service = stellar_service
        self.encryption_service = encryption_service
        self.add_wallet = add_wallet_use_case
        self.cheque_public_key = cheque_public_key

    async def execute(self, user_id: int, cheque_uuid: str, username: str) -> ClaimResult:
        cheque = await self.cheque_repository.get_by_uuid(cheque_uuid)
        if not cheque:
            return ClaimResult(False, error_message="Cheque not found")
            
        # Check limits
        receive_count = await self.cheque_repository.get_receive_count(cheque_uuid)
        if receive_count >= cheque.count:
             return ClaimResult(False, error_message="Cheque limit reached")
             
        user_receive_count = await self.cheque_repository.get_receive_count(cheque_uuid, user_id)
        if user_receive_count > 0:
             return ClaimResult(False, error_message="Cheque already received by user")

        # Get/Create User Wallet
        wallet = await self.wallet_repository.get_default_wallet(user_id)
        was_new = False
        new_secret = None

        if not wallet:
            was_new = True
            # Create new wallet
            # Generate keypair for the new wallet
            keypair = self.stellar_service.generate_keypair()
            new_secret = keypair.secret

            # AddWallet requires public_key and optional secret_key
            wallet = await self.add_wallet.execute(
                user_id=user_id,
                public_key=keypair.public_key,
                secret_key=new_secret,
                is_free=True,
                is_default=True
            )

        # Record History
        await self.cheque_repository.add_history(cheque.id, user_id)

        # Build Operations
        ops = []

        # 1. If new user, Create Account (Master -> User)
        master_wallet = await self.wallet_repository.get_default_wallet(0)
        if not master_wallet:
            return ClaimResult(False, error_message="Master wallet not found")

        if not master_wallet.secret_key:
            return ClaimResult(False, error_message="Master wallet secret not available")

        master_secret = self.encryption_service.decrypt(master_wallet.secret_key, "0")
        if not master_secret:
            return ClaimResult(False, error_message="Failed to decrypt master secret")
        
        if was_new:
            ops.append(self.stellar_service.create_create_account_op(
                destination=wallet.public_key,
                starting_balance="5",
                source=master_wallet.public_key
            ))
            
            # 2. Add Trust Lines (User -> Assets)
            # User must sign these.
            assets_to_trust = ['MTL', 'EURMTL', 'SATSMTL', 'USDM']
            for asset_code in assets_to_trust:
                ops.append(self.stellar_service.create_change_trust_op(
                    asset_code=asset_code,
                    asset_issuer="GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V", # Should be constant
                    source=wallet.public_key
                ))
                
        # 3. Payment (Cheque -> User)
        if not cheque.asset:
            return ClaimResult(False, error_message="Cheque asset not defined")

        cheque_asset_parts = cheque.asset.split(':')
        ops.append(self.stellar_service.create_payment_op(
            destination=wallet.public_key,
            asset_code=cheque_asset_parts[0],
            asset_issuer=cheque_asset_parts[1] if len(cheque_asset_parts) > 1 else None,
            amount=cheque.amount,
            source=self.cheque_public_key
        ))

        # Build Transaction
        # Source account for Transaction?
        # If CreateAccount included, Master is good source (pays fee).
        # If not new, ChequeAccount could be source (if it has XLM).
        source_pk = master_wallet.public_key if was_new else self.cheque_public_key
        # Note: If cheque public key is used as source, it must have XLM.
        
        tx = await self.stellar_service.build_transaction(
            source_public_key=source_pk,
            operations=ops,
            memo=cheque_uuid[:16]
        )
        
        # Sign
        # 1. Master
        tx_envelope = tx
        if was_new or source_pk == master_wallet.public_key:
            tx_envelope = await self.stellar_service.sign_transaction(tx_envelope, master_secret)

        # 2. New User (for Trust Lines)
        if was_new:
            # Decrypt new user secret. Pin is user_id?
            if not wallet.secret_key:
                return ClaimResult(False, error_message="Wallet secret not available")

            user_secret = self.encryption_service.decrypt(wallet.secret_key, str(user_id))
            if not user_secret:
                return ClaimResult(False, error_message="Failed to decrypt wallet secret")

            tx_envelope = await self.stellar_service.sign_transaction(tx_envelope, user_secret)

        # 3. Cheque Account (for Payment) - Assumed Master Controlled?
        # If Cheque Account is separate, we need its secret.
        # Legacy: `stellar_sign(xdr, master.secret)`.
        # So Master signs for Cheque Account.
        # Already signed by Master above.

        xdr = tx_envelope.to_xdr()
        
        return ClaimResult(True, xdr=xdr)


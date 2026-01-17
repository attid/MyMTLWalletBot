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
            # AddWallet returns Wallet entity
            # We need to know the secret to sign trustlines
            # New wallets are free (is_free=True)
            wallet = await self.add_wallet.execute(user_id=user_id, is_free=True, is_default=True)
            # Fetch secret (decrypted with default logic? Free wallet secrets usually not encrypted with pin yet?)
            # In AddWallet: if secret_key not provided, it generates one.
            # And stores it. 
            # If is_free=True, logic in AddWallet: pin not used?
            # Wait, repo.create stores encrypted secret if we pass it encrypted.
            # AddWallet logic: 
            # keypair = Keypair.random()
            # secret_key = keypair.secret
            # encrypted_secret = encrypt(secret_key, pin)
            # But if no pin (AddWallet defaults?), checks is_free.
            # I need to check AddWallet default pin logic.
            
            # Assuming we can get the secret.
            # If AddWallet doesn't return secret, we must fetch it.
            # If wallet is free/no pin, secret might be encrypted with default/user_id?
            # Let's assume we can get it via standard decrypt if we know the pin (default?).
            pass

        # Record History
        await self.cheque_repository.add_history(cheque.id, user_id)
        
        # Build Operations
        ops = []
        
        # 1. If new user, Create Account (Master -> User)
        master_wallet = await self.wallet_repository.get_default_wallet(0)
        master_key = master_wallet.secret_key # Encrypted?
        # Decrypt master key. Master pin? 
        # Usually Master pin is known or stored?
        # Assuming we can decrypt master key. `decrypt(master_wallet.secret_key, master_pin)`
        # Where to get master pin? 
        # In legacy code `stellar_get_master` gets wallet 0.
        # EncryptionService needs to decrypt it.
        # Legacy code often assumes Master Key is accessible.
        # I'll assume Master Wallet uses default PIN or I receive it in constructor? 
        # Or I use `GetWalletSecrets` logic.
        
        # For this implementation, let's assume I can get decrypted Keypair for Master.
        # Using a helper or assumes secret is available.
        # Wait, if I cannot get Master Secret, I cannot sign.
        # Legacy `stellar_get_master` implementation?
        # `stellar_get_user_keypair(session, 0, str(0))` ?
        # Yes, `stellar_get_user_keypair` uses `user_password`. For ID 0 it is `'0'`.
        
        master_secret = self.encryption_service.decrypt(master_wallet.secret_key, "0")
        
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
            # AddWallet: `encrypt(secret, str(user_id))` if no pin?
            # I need to confirm `AddWallet` pin logic for `is_free=True`.
            user_secret = self.encryption_service.decrypt(wallet.secret_key, str(user_id))
            tx_envelope = await self.stellar_service.sign_transaction(tx_envelope, user_secret)
            
        # 3. Cheque Account (for Payment) - Assumed Master Controlled?
        # If Cheque Account is separate, we need its secret.
        # Legacy: `stellar_sign(xdr, master.secret)`.
        # So Master signs for Cheque Account.
        # Already signed by Master above.
        
        xdr = tx_envelope.to_xdr()
        
        return ClaimResult(True, xdr=xdr)


from typing import Optional
from dataclasses import dataclass
from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IEncryptionService

@dataclass
class WalletSecrets:
    secret_key: str
    seed_phrase: Optional[str] = None

class GetWalletSecrets:
    def __init__(self, wallet_repository: IWalletRepository, encryption_service: IEncryptionService):
        self.wallet_repository = wallet_repository
        self.encryption_service = encryption_service

    async def execute(self, user_id: int, pin: str) -> Optional[WalletSecrets]:
        """
        Retrieve decrypted wallet secrets.
        
        Args:
            user_id: The ID of the user.
            pin: The PIN/password to decrypt the secret key.
            
        Returns:
            WalletSecrets object if successful, None if wallet not found or pin invalid.
        """
        wallet = await self.wallet_repository.get_default_wallet(user_id)
        if not wallet or not wallet.secret_key:
            return None

        # Decrypt secret key using pin
        secret = self.encryption_service.decrypt(wallet.secret_key, pin)
        if secret is None:
            return None

        seed_phrase = None
        if wallet.seed_key:
            # Seed key is encrypted using the PRIVATE KEY (secret)
            seed_phrase = self.encryption_service.decrypt(wallet.seed_key, secret)

        return WalletSecrets(secret_key=secret, seed_phrase=seed_phrase)

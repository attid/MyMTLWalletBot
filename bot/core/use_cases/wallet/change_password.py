from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IEncryptionService


class ChangeWalletPassword:
    def __init__(
        self,
        wallet_repository: IWalletRepository,
        encryption_service: IEncryptionService,
    ):
        self.wallet_repository = wallet_repository
        self.encryption_service = encryption_service

    async def execute(
        self, user_id: int, old_pin: str, new_pin: str, pin_type: int
    ) -> bool:
        """
        Change the wallet password (re-encrypt secret key).

        Args:
            user_id: The ID of the user.
            old_pin: The current PIN/password.
            new_pin: The new PIN/password.
            pin_type: The new PIN type identifier (e.g. 1 for pin, 2 for password).

        Returns:
            True if successful, False if old password invalid or wallet not found.
        """
        wallet = await self.wallet_repository.get_default_wallet(user_id)
        if not wallet:
            return False

        secret = None
        seed = None

        if wallet.wallet_crypto_v2:
            secret = self.encryption_service.decrypt_wallet_secret(
                wallet.wallet_crypto_v2,
                pin=old_pin,
            )
            seed = self.encryption_service.decrypt_wallet_seed(
                wallet.wallet_crypto_v2,
                pin=old_pin,
            )

        if secret is None and wallet.secret_key:
            # Legacy fallback
            secret = self.encryption_service.decrypt(wallet.secret_key, old_pin)
            if wallet.seed_key and secret:
                seed = self.encryption_service.decrypt(wallet.seed_key, secret)

        if secret is None:
            return False

        # Legacy dual-write
        new_encrypted_secret = self.encryption_service.encrypt(secret, new_pin)

        # v2 write (single container field)
        wallet_kind = "stellar_free" if wallet.is_free else "stellar_user"
        mode = "free" if pin_type == 0 else "user"
        wallet.wallet_crypto_v2 = self.encryption_service.encrypt_wallet_container(
            secret_key=secret,
            seed_key=seed,
            mode=mode,
            wallet_kind=wallet_kind,
            pin=new_pin if mode == "user" else None,
        )

        # Update wallet
        wallet.secret_key = new_encrypted_secret
        wallet.use_pin = pin_type

        # Note: We do not re-encrypt seed_key because it is encrypted with the PRIVATE KEY (secret),
        # which does not change.

        await self.wallet_repository.update(wallet)
        return True

from typing import Optional
from core.domain.entities import Wallet
from core.interfaces.repositories import IWalletRepository

class AddWallet:
    def __init__(self, wallet_repo: IWalletRepository):
        self.wallet_repo = wallet_repo

    async def execute(self, user_id: int, public_key: str, secret_key: Optional[str] = None, 
                      is_free: bool = False, is_default: bool = True, seed_key: Optional[str] = None,
                      is_read_only: bool = False) -> Wallet:
        """
        Add a wallet for an existing user.
        
        Args:
            user_id: The ID of the user.
            public_key: The public key of the wallet.
            secret_key: The secret key (optional).
            is_free: Whether this is a 'free' wallet (bot-managed).
            is_default: Whether to set this wallet as default.
            seed_key: Mnemonic phrase (optional).
            is_read_only: Whether this is a read-only wallet.
        
        Returns:
            The created Wallet entity.
            
        Raises:
            ValueError: If wallet limit reached or validation fails.
        """
        if is_free:
            # Check maximum free wallets rule. 
            # Logic from legacy db/requests.py: if result > 2 return False.
            # This means if user has 0, 1, or 2 free wallets, they CAN adds another.
            # So the max total free wallets is 3. 
            count = await self.wallet_repo.count_free_wallets(user_id)
            if count > 2:
               raise ValueError("Maximum number of free wallets reached.")

        # Determine PIN state
        use_pin = 0
        if is_read_only:
             use_pin = 10
        elif secret_key:
             use_pin = 1
             
        # Create wallet entity
        # Note: ID is 0 or None for new entity, Repo will handle generation/ignore it on create.
        wallet = Wallet(
            id=0,   # Placeholder
            user_id=user_id,
            public_key=public_key,
            is_default=is_default,
            is_free=is_free,
            secret_key=secret_key,
            seed_key=seed_key,
            use_pin=use_pin, 
            # Legacy: if secret_key, default pin might be set? 
            # db_add_wallet defaults: default_wallet=0, free_wallet=i_free_wallet, last_event_id=max...
            # db used default values for other columns.
            # Entity defaults: use_pin=0, assets_visibility="{}"
        )
        
        # If secret_key is not provided (e.g. read-only), use_pin might be different.
        # Legacy stellar_save_ro sets use_pin=10 (r/o) via db_update_secret_key call immediately after.
        # Use Case caller should probably set use_pin or we infer it?
        # Argument 'is_read_only' is not in execute signature yet, but 'secret_key' optional implies strictness.
        if not secret_key and not is_read_only:
             wallet.use_pin = 10 # Default to read-only if no secret? OR 0 (no pin)?
             # Legacy only has 0 (no pin), 1 (pin), 2 (pass), 10 (r/o)
             # If no secret, must be r/o? Or watch-only without validation?
             # Let's default to 0 if not specified.
             wallet.use_pin = 0
             
        created_wallet = await self.wallet_repo.create(wallet)

        if is_default:
             await self.wallet_repo.set_default_wallet(user_id, public_key)
             created_wallet.is_default = True
             
        return created_wallet

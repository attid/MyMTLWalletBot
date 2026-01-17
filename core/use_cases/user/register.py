from typing import Tuple
from core.domain.entities import User, Wallet
from core.interfaces.repositories import IUserRepository, IWalletRepository
# Note: In a real scenario, we might need a KeyGenerationService. 
# For now, assuming keys are passed in or generated simple.
# Existing logic in routers/common_start.py usually generates keys.
# We will assume keys are provided to this use case for simplicity of migration 
# OR we should implement a helper here.
# Given the plan doesn't specify KeyGen service, let's keep it simple: 
# The use case creates the User and a default Wallet.

class RegisterUser:
    def __init__(self, user_repository: IUserRepository, wallet_repository: IWalletRepository):
        self.user_repository = user_repository
        self.wallet_repository = wallet_repository

    async def execute(self, user_id: int, username: str, language: str, public_key: str, secret_key: str = None) -> Tuple[User, Wallet]:
        """
        Registers a new user and their initial wallet.
        Atomic operation is ideal (Unit of Work), but here we do sequential.
        """
        # 1. Check if user exists
        existing_user = await self.user_repository.get_by_id(user_id)
        if existing_user:
            # Maybe just return existing, or update?
            # 'start' command often re-initializes or just welcomes back.
            # We'll return existing user and their default wallet.
            default_wallet = await self.wallet_repository.get_default_wallet(user_id)
            if not default_wallet:
                # Should not happen ideally if registered fully, but handle repair?
                 # Create wallet if missing
                default_wallet = await self._create_wallet(user_id, public_key, secret_key)
            return existing_user, default_wallet

        # 2. Create User
        new_user = User(id=user_id, username=username, language=language)
        saved_user = await self.user_repository.create(new_user)

        # 3. Create Default Wallet
        saved_wallet = await self._create_wallet(user_id, public_key, secret_key)

        return saved_user, saved_wallet

    async def _create_wallet(self, user_id: int, public_key: str, secret_key: str) -> Wallet:
        new_wallet = Wallet(
            id=0, # Auto-increment
            user_id=user_id,
            public_key=public_key,
            is_default=True,
            is_free=True # Default to free/checking wallet logic
        )
        return await self.wallet_repository.create(new_wallet)

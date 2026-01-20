"""SQLAlchemy implementation of IWalletSecretService."""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.interfaces.services import IWalletSecretService
from db.models import MyMtlWalletBot


class SqlAlchemyWalletSecretService(IWalletSecretService):
    """SQLAlchemy implementation for secure wallet secret access.
    
    This service provides access to sensitive wallet data (secret_key, seed_key)
    that should not be part of the domain entity for security reasons.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def _get_default_wallet(self, user_id: int) -> Optional[MyMtlWalletBot]:
        """Get the default wallet model for a user."""
        stmt = select(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id
        ).where(
            MyMtlWalletBot.default_wallet == 1
        ).where(
            MyMtlWalletBot.need_delete == 0
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_wallet_type(self, user_id: int) -> Optional[str]:
        """
        Get the wallet type identifier.
        Returns 'TON' for TON wallets, or the secret_key identifier for Stellar.
        """
        wallet = await self._get_default_wallet(user_id)
        if wallet:
            return wallet.secret_key
        return None
    
    async def get_ton_mnemonic(self, user_id: int) -> Optional[str]:
        """
        Get the TON wallet mnemonic (seed_key) for the user's default wallet.
        Returns None if not a TON wallet.
        """
        wallet = await self._get_default_wallet(user_id)
        if wallet and wallet.secret_key == 'TON':
            return wallet.seed_key
        return None
    
    async def is_ton_wallet(self, user_id: int) -> bool:
        """Check if the user's default wallet is a TON wallet."""
        wallet_type = await self.get_wallet_type(user_id)
        return wallet_type == 'TON'

from typing import List, Optional
from sqlalchemy import update, func
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from core.domain.entities import Wallet
from core.interfaces.repositories import IWalletRepository
from db.models import MyMtlWalletBot

class SqlAlchemyWalletRepository(IWalletRepository):
    def __init__(self, session: Session):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> List[Wallet]:
        stmt = select(MyMtlWalletBot).where(MyMtlWalletBot.user_id == user_id)
        result = self.session.execute(stmt)
        db_wallets = result.scalars().all()
        return [self._to_entity(w) for w in db_wallets]

    async def get_by_public_key(self, public_key: str) -> Optional[Wallet]:
        stmt = select(MyMtlWalletBot).where(MyMtlWalletBot.public_key == public_key)
        result = self.session.execute(stmt)
        db_wallet = result.scalar_one_or_none()
        if db_wallet:
            return self._to_entity(db_wallet)
        return None

    async def get_default_wallet(self, user_id: int) -> Optional[Wallet]:
        stmt = select(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id,
            MyMtlWalletBot.default_wallet == 1 
        )
        result = self.session.execute(stmt)
        db_wallet = result.scalar_one_or_none()
        if db_wallet:
            return self._to_entity(db_wallet)
        return None

    async def get_all_active(self, user_id: int) -> List[Wallet]:
        """Retrieve all active (non-deleted) wallets for a user."""
        stmt = select(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id,
            MyMtlWalletBot.need_delete == 0
        )
        result = self.session.execute(stmt)
        db_wallets = result.scalars().all()
        return [self._to_entity(w) for w in db_wallets]

    async def create(self, wallet: Wallet) -> Wallet:
        db_wallet = MyMtlWalletBot(
            user_id=wallet.user_id,
            public_key=wallet.public_key,
            default_wallet=1 if wallet.is_default else 0,
            free_wallet=1 if wallet.is_free else 0,
            assets_visibility=wallet.assets_visibility,
            secret_key=wallet.secret_key,
            seed_key=wallet.seed_key,
            balances=None, # New wallets have no cache
            balances_event_id=0,
            last_event_id=0
        )
        self.session.add(db_wallet)
        self.session.flush()
        return self._to_entity(db_wallet)

    async def update(self, wallet: Wallet) -> Wallet:
        stmt = select(MyMtlWalletBot).where(MyMtlWalletBot.id == wallet.id)
        result = self.session.execute(stmt)
        db_wallet = result.scalar_one_or_none()
        if db_wallet:
            db_wallet.default_wallet = 1 if wallet.is_default else 0
            db_wallet.assets_visibility = wallet.assets_visibility
            
            # Serialize balances
            if wallet.balances is not None:
                import jsonpickle
                db_wallet.balances = jsonpickle.encode(wallet.balances)
                
            db_wallet.balances_event_id = wallet.balances_event_id
            # last_event_id should probably be managed by DB or specific logic, but we map it back
            # Usually last_event_id increments on events. 
            # If we are updating cache, we likely set balances_event_id = last_event_id
            
            if wallet.last_event_id:
                db_wallet.last_event_id = wallet.last_event_id

            # Update sensitive fields
            db_wallet.secret_key = wallet.secret_key
            db_wallet.seed_key = wallet.seed_key
            db_wallet.use_pin = wallet.use_pin
            db_wallet.free_wallet = 1 if wallet.is_free else 0
                
            self.session.flush()
            return self._to_entity(db_wallet)
        raise ValueError(f"Wallet with id {wallet.id} not found for update")

    async def reset_balance_cache(self, user_id: int) -> None:
        """Reset the cached balance for the user's default wallet."""
        stmt = select(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id,
            MyMtlWalletBot.default_wallet == 1
        )
        result = self.session.execute(stmt)
        db_wallet = result.scalar_one_or_none()
        if db_wallet:
            db_wallet.balances_event_id = '0'
            self.session.commit()

    async def delete(self, user_id: int, public_key: str, erase: bool = False, wallet_id: int = None) -> None:
        """Delete or soft-delete a wallet."""
        if user_id < 1:
            return
        stmt = select(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id,
            MyMtlWalletBot.public_key == public_key
        )
        if wallet_id is not None:
            stmt = stmt.where(MyMtlWalletBot.id == wallet_id)
        result = self.session.execute(stmt)
        db_wallet = result.scalar_one_or_none()
        if db_wallet:
            if erase:
                self.session.delete(db_wallet)
            else:
                db_wallet.need_delete = 1
            self.session.commit()

    async def count_free_wallets(self, user_id: int) -> int:
        """Count the number of active free wallets for a user."""
        stmt = select(func.count(MyMtlWalletBot.user_id)).where(
            MyMtlWalletBot.user_id == user_id,
            MyMtlWalletBot.free_wallet == 1,
            MyMtlWalletBot.need_delete == 0
        )
        result = self.session.execute(stmt)
        return result.scalar() or 0

    async def set_default_wallet(self, user_id: int, public_key: str) -> bool:
        """Set a wallet as default for the user."""
        # Unset all default wallets
        stmt_unset = update(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id
        ).values(default_wallet=0)
        self.session.execute(stmt_unset)
        
        # Set new default
        stmt_set = update(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id,
            MyMtlWalletBot.public_key == public_key,
            MyMtlWalletBot.need_delete == 0
        ).values(default_wallet=1)
        result = self.session.execute(stmt_set)
        # We usually let the service layer commit, but here we might need flush to ensure updates are ready?
        # db/requests.py committed immediately. 
        self.session.flush()
        return result.rowcount > 0

    async def delete_all_by_user(self, user_id: int) -> None:
        """Delete (soft-delete) all wallets for a user."""
        if user_id < 1:
            return
        
        stmt = update(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id
        ).values(need_delete=1)
        self.session.execute(stmt)
        self.session.flush()

    async def get_info(self, user_id: int, public_key: str) -> str:
        """Get wallet info string."""
        stmt = select(MyMtlWalletBot).where(
            MyMtlWalletBot.user_id == user_id,
            MyMtlWalletBot.public_key == public_key,
            MyMtlWalletBot.need_delete == 0
        )
        result = self.session.execute(stmt)
        db_wallet = result.scalar_one_or_none()
        if db_wallet is None:
            return "(нет данных)"
        if db_wallet.free_wallet == 1:
            return '(free)'
        elif db_wallet.use_pin == 0:
            return '(no pin)'
        elif db_wallet.use_pin == 1:
            return '(pin)'
        elif db_wallet.use_pin == 2:
            return '(pass)'
        elif db_wallet.use_pin == 10:
            return '(r/o)'
        else:
            return '(?)'

    def _to_entity(self, db_wallet: MyMtlWalletBot) -> Wallet:
        balances = None
        if db_wallet.balances:
            try:
                import jsonpickle
                balances = jsonpickle.decode(db_wallet.balances)
            except Exception:
                balances = []
                
        return Wallet(
            id=db_wallet.id,
            user_id=db_wallet.user_id,
            public_key=db_wallet.public_key,
            is_default=bool(db_wallet.default_wallet),
            is_free=bool(db_wallet.free_wallet),
            use_pin=db_wallet.use_pin or 0,
            assets_visibility=db_wallet.assets_visibility,
            secret_key=db_wallet.secret_key,
            seed_key=db_wallet.seed_key,
            balances=balances,
            balances_event_id=db_wallet.balances_event_id or 0,
            last_event_id=db_wallet.last_event_id or 0
        )

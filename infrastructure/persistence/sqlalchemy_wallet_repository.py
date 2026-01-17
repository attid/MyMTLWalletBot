from typing import List, Optional
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

    async def create(self, wallet: Wallet) -> Wallet:
        # Note: mapping entity to DB model. 
        # WARNING: Entity 'id' might be None/0 if it's new, but DB needs it or autogenerates it.
        # entities.Wallet has 'id', which maps to MyMtlWalletBot.id (Integer primary key)
        
        db_wallet = MyMtlWalletBot(
            user_id=wallet.user_id,
            public_key=wallet.public_key,
            default_wallet=1 if wallet.is_default else 0,
            free_wallet=1 if wallet.is_free else 0,
            assets_visibility=wallet.assets_visibility
            # secret_key is not in Entity Wallet currently as per rules (no secrets in domain entities ideally)
            # We might need to handle secret key differently or add it to entity but carefully.
            # For this phase/task, let's assume we are migrating existing logic where secrets are likely managed elsewhere or passed in?
            # Creating a wallet usually requires generating keys. 
            # The Use Case logic will likely handle key generation and pass public key here.
            # But the DB expects a secret key probably?
            # Checking models.py: secret_key = Column(String(160))
            # It's nullable? No 'nullable=False' specified, so it is nullable by default in SQLAlchemy unless specified.
            # However, logic likely relies on it.
            # For now, I will omit writing secret_key if it's not in the entity. 
            # This might be an issue for creating NEW wallets if the DB requires it.
            # But for "Foundation & Identity Context" migration, we might just be reading mostly?
            # The plan says "RegisterUser" use case.
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
            # Other fields update...
            self.session.flush()
            return self._to_entity(db_wallet)
        raise ValueError(f"Wallet with id {wallet.id} not found for update")

    def _to_entity(self, db_wallet: MyMtlWalletBot) -> Wallet:
        return Wallet(
            id=db_wallet.id,
            user_id=db_wallet.user_id,
            public_key=db_wallet.public_key,
            is_default=bool(db_wallet.default_wallet),
            is_free=bool(db_wallet.free_wallet),
            assets_visibility=db_wallet.assets_visibility
        )

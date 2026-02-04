from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.repositories import (
    IRepositoryFactory,
    IWalletRepository,
    IUserRepository,
    IAddressBookRepository,
    IChequeRepository,
    INotificationRepository,
    IMessageRepository,
)
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.persistence.sqlalchemy_addressbook_repository import SqlAlchemyAddressBookRepository
from infrastructure.persistence.sqlalchemy_cheque_repository import SqlAlchemyChequeRepository
from infrastructure.persistence.sqlalchemy_notification_repository import SqlAlchemyNotificationRepository

from infrastructure.persistence.sqlalchemy_message_repository import SqlAlchemyMessageRepository

class SqlAlchemyRepositoryFactory(IRepositoryFactory):
    """
    Factory for creating SQLAlchemy implementations of repositories.
    """

    def get_wallet_repository(self, session: Any) -> IWalletRepository:
        if not isinstance(session, AsyncSession):
            raise ValueError("SqlAlchemyRepositoryFactory requires a SQLAlchemy AsyncSession")
        return SqlAlchemyWalletRepository(session)

    def get_user_repository(self, session: Any) -> IUserRepository:
        if not isinstance(session, AsyncSession):
            raise ValueError("SqlAlchemyRepositoryFactory requires a SQLAlchemy AsyncSession")
        return SqlAlchemyUserRepository(session)

    def get_addressbook_repository(self, session: Any) -> IAddressBookRepository:
        if not isinstance(session, AsyncSession):
            raise ValueError("SqlAlchemyRepositoryFactory requires a SQLAlchemy AsyncSession")
        return SqlAlchemyAddressBookRepository(session)

    def get_cheque_repository(self, session: Any) -> IChequeRepository:
        if not isinstance(session, AsyncSession):
            raise ValueError("SqlAlchemyRepositoryFactory requires a SQLAlchemy AsyncSession")
        return SqlAlchemyChequeRepository(session)
    
    def get_notification_repository(self, session: Any) -> INotificationRepository:
        if not isinstance(session, AsyncSession):
            raise ValueError("SqlAlchemyRepositoryFactory requires a SQLAlchemy AsyncSession")
        return SqlAlchemyNotificationRepository(session)



    def get_message_repository(self, session: Any) -> IMessageRepository:
        if not isinstance(session, AsyncSession):
            raise ValueError("SqlAlchemyRepositoryFactory requires a SQLAlchemy AsyncSession")
        return SqlAlchemyMessageRepository(session)

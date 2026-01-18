import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import async_sessionmaker
from infrastructure.services.localization_service import LocalizationService
from core.interfaces.repositories import IRepositoryFactory
from core.interfaces.services import IStellarService

class AppContext:
    """
    Application-wide context container.
    Replaces GlobalData singleton for Dependency Injection.
    """
    def __init__(
        self,
        bot: Bot,
        db_pool: async_sessionmaker,
        admin_id: int,
        cheque_queue: asyncio.Queue,
        log_queue: asyncio.Queue,
        repository_factory: IRepositoryFactory,
        stellar_service: IStellarService,
        localization_service: LocalizationService = None,
        dispatcher: Optional[Dispatcher] = None
    ):
        self.bot = bot
        self.db_pool = db_pool
        self.admin_id = admin_id
        self.cheque_queue = cheque_queue
        self.log_queue = log_queue
        self.repository_factory = repository_factory
        self.stellar_service = stellar_service
        self.localization_service = localization_service
        self.dispatcher = dispatcher

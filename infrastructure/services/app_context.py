import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher
from sqlalchemy.orm import sessionmaker
from infrastructure.services.localization_service import LocalizationService

class AppContext:
    """
    Application-wide context container.
    Replaces GlobalData singleton for Dependency Injection.
    """
    def __init__(
        self,
        bot: Bot,
        db_pool: sessionmaker,
        admin_id: int,
        cheque_queue: asyncio.Queue,
        log_queue: asyncio.Queue,
        localization_service: LocalizationService = None,
        dispatcher: Optional[Dispatcher] = None
    ):
        self.bot = bot
        self.db_pool = db_pool
        self.admin_id = admin_id
        self.cheque_queue = cheque_queue
        self.log_queue = log_queue
        self.localization_service = localization_service
        self.dispatcher = dispatcher

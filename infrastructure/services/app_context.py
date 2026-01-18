import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher
from sqlalchemy.orm import sessionmaker

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
        dispatcher: Optional[Dispatcher] = None
    ):
        self.bot = bot
        self.db_pool = db_pool
        self.admin_id = admin_id
        self.cheque_queue = cheque_queue
        self.log_queue = log_queue
        self.dispatcher = dispatcher

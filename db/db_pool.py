from contextlib import contextmanager
from typing import Generator

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from utils.config_reader import config


class DatabasePool:
    def __init__(self):
        self.engine = create_engine(config.db_dns,
                                   pool_pre_ping=True,
                                   pool_size=20,
                                   max_overflow=50,
                                   pool_timeout=30,
                                   pool_recycle=1800)
        self.session_maker = sessionmaker(bind=self.engine)
        self.active_connections = 0
        self.borrowed_connections = 0

    @contextmanager
    def get_session(self) -> Generator[sessionmaker, None, None]:
        logger.info("Получение сессии из пула...")
        session = self.session_maker()
        self.active_connections += 1
        self.borrowed_connections += 1
        try:
            yield session
        except Exception as e:
            logger.exception(f"Ошибка при работе с сессией: {e}")
            raise
        finally:
            self.active_connections -= 1
            self.borrowed_connections -= 1
            session.close()
            logger.info(f"Сессия возвращена в пул. Активные соединения: {self.active_connections}, взятые соединения: {self.borrowed_connections}")


    def get_active_connections(self):
        return self.active_connections

    def get_borrowed_connections(self):
        return self.borrowed_connections


db_pool = DatabasePool()
from contextlib import contextmanager
from typing import Generator
import asyncio
import random

from loguru import logger
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from other.config_reader import config
from db.models import MyMtlWalletBot


class DatabasePool:
    def __init__(self):
        self.engine = create_engine(config.db_url,
                                    pool_pre_ping=True,
                                    pool_size=20,
                                    max_overflow=50,
                                    pool_timeout=30,
                                    pool_recycle=1800)
        self.get_session = sessionmaker(bind=self.engine)
        self.active_connections = 0
        self.pool_connections = 0

        @event.listens_for(self.engine, 'connect')
        def connect(dbapi_connection, connection_record):
            print(dbapi_connection.default_tpb)
            self.pool_connections += 1
            logger.info(f"Новое соединение. Соединений {self.active_connections}/{self.pool_connections}")

        @event.listens_for(self.engine, 'close')
        def close(dbapi_connection, connection_record):
            self.pool_connections -= 1
            logger.info(f"Соединение закрыто. Соединений {self.active_connections}/{self.pool_connections}")

        @event.listens_for(self.engine, 'checkout')
        def checkout(dbapi_connection, connection_record, connection_proxy):
            self.active_connections += 1
            if self.active_connections > 3:
                logger.info(f"Соединение взято из пула. Соединений {self.active_connections}/{self.pool_connections}")

        @event.listens_for(self.engine, 'checkin')
        def checkin(dbapi_connection, connection_record):
            self.active_connections -= 1
            if self.active_connections > 3:
                logger.info(
                    f"Соединение возвращено в пул. Соединений {self.active_connections}/{self.pool_connections}")

        # @event.listens_for(self.get_session, "after_begin")
        # def set_transaction_timeout(session, transaction, connection):
        #     logger.info("after_begin")
        #     # session.execute(text("SET LOCAL lock_timeout = '5s'"))

        # @event.listens_for(MyMtlWalletBot, 'before_update')
        # def before_update(mapper, connection, target):
        #     logger.info(f"Объект {target} будет обновлен")

        # @event.listens_for(self.engine, 'before_cursor_execute')
        # def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        #     if "UPDATE" in statement:
        #         logger.info(f"Выполняется массовое обновление: {statement}, Параметры: {parameters}")
        #         # conn.execute(text("SET TRANSACTION LOCK TIMEOUT 5"))

        # @event.listens_for(self.engine.pool, 'connect')
        # def pool_connect(dbapi_connection, connection_record):
        #     logger.info("Pool создан")
        #
        # @event.listens_for(self.engine.pool, 'close')
        # def pool_close(dbapi_connection, connection_record):
        #     logger.info("Pool закрыт")

        # Настройка события after_begin
        # @event.listens_for(self.session_maker, "after_begin")
        # def set_transaction_defaults(session, transaction, connection):

    #     session.execute(text("SET TRANSACTION LOCK TIMEOUT 5"))

    # @contextmanager
    # def get_session(self) -> Generator[sessionmaker, None, None]:
    #     logger.info("Получение сессии из пула...")
    #     session = self.session_maker()
    #     self.active_connections += 1
    #     self.borrowed_connections += 1
    #     try:
    #         #session.begin()
    #         #session.execute(text("SET TRANSACTION READ COMMITTED NO WAIT")) # possible deadlock prevention
    #         yield session
    #     except Exception as e:
    #         logger.exception(f"Ошибка при работе с сессией: {e}")
    #         raise
    #     finally:
    #         self.active_connections -= 1
    #         self.borrowed_connections -= 1
    #         session.close()
    #         logger.info(f"Сессия возвращена в пул. Активные соединения: {self.active_connections}, взятые соединения: {self.borrowed_connections}")

    def get_active_connections(self):
        return self.active_connections


db_pool = DatabasePool()


async def update_last_event_id(my_id, public_key):
    random_id = random.randint(1, 10)
    print(21, my_id, random_id)
    with db_pool.get_session() as session:
        print(22, my_id)
        # result = session.query(MyMtlWalletBot)\
        #             .filter(MyMtlWalletBot.public_key == public_key)\
        #             .with_for_update(nowait=False).first()
        q = session.query(MyMtlWalletBot) \
            .filter(MyMtlWalletBot.public_key == public_key)

        await asyncio.to_thread(q.update, {MyMtlWalletBot.last_event_id: random_id})
        print(23, my_id)
        await asyncio.sleep(random_id)
        print(24, my_id)
        session.commit()
        print(25, my_id)


async def test():
    with db_pool.get_session() as session:
        record = session.query(MyMtlWalletBot).first()
        if record:
            tasks = []
            for _ in range(100):
                task = asyncio.create_task(update_last_event_id(_, record.public_key))
                tasks.append(task)
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)
            for _ in range(10):
                task = asyncio.create_task(update_last_event_id(_, record.public_key))
                tasks.append(task)
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)
            for _ in range(10):
                task = asyncio.create_task(update_last_event_id(_, record.public_key))
                tasks.append(task)
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)


if __name__ == '__main__':
    asyncio.run(test())
    pass

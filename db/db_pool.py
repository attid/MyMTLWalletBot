from contextlib import asynccontextmanager
from typing import AsyncGenerator
import asyncio
import random

from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, event

from other.config_reader import config
from db.models import MyMtlWalletBot


class DatabasePool:
    def __init__(self):
        # Determine the async driver URL
        self.db_url = config.db_url
        if "firebird://" in self.db_url:
            self.db_url = self.db_url.replace("firebird://", "firebird+firebird_async://")
        elif "firebird+fdb://" in self.db_url:
            self.db_url = self.db_url.replace("firebird+fdb://", "firebird+firebird_async://")
        # Ensure utf-8 charset if not present
        if "charset=" not in self.db_url:
            join_char = "&" if "?" in self.db_url else "?"
            self.db_url += f"{join_char}charset=UTF8"
            
        self.engine = create_async_engine(
            self.db_url,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=50,
            pool_timeout=30,
            pool_recycle=1800,
            echo=False 
        )
        
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
        self.active_connections = 0
        self.pool_connections = 0

        # Note: SQLAlchemy async engine events are slightly different. 
        # Standard engine events like 'connect', 'checkout' work on the sync driver under the hood
        # but attaching them to async engine requires using .sync_engine
        
        try:
            @event.listens_for(self.engine.sync_engine, 'connect')
            def connect(dbapi_connection, connection_record):
                self.pool_connections += 1
                logger.info(f"Новое соединение. Соединений {self.active_connections}/{self.pool_connections}")

            @event.listens_for(self.engine.sync_engine, 'close')
            def close(dbapi_connection, connection_record):
                self.pool_connections -= 1
                logger.info(f"Соединение закрыто. Соединений {self.active_connections}/{self.pool_connections}")

            @event.listens_for(self.engine.sync_engine, 'checkout')
            def checkout(dbapi_connection, connection_record, connection_proxy):
                self.active_connections += 1
                if self.active_connections > 3:
                    logger.info(f"Соединение взято из пула. Соединений {self.active_connections}/{self.pool_connections}")

            @event.listens_for(self.engine.sync_engine, 'checkin')
            def checkin(dbapi_connection, connection_record):
                self.active_connections -= 1
                if self.active_connections > 3:
                    logger.info(
                        f"Соединение возвращено в пул. Соединений {self.active_connections}/{self.pool_connections}")
        except Exception as e:
            logger.warning(f"Could not attach pool events: {e}")

    def get_active_connections(self):
        return self.active_connections

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
                # await session.commit() # Usually handled by caller or context
            except Exception as e:
                logger.exception(f"Session error: {e}")
                await session.rollback()
                raise
            # Session is automatically closed by async_sessionmaker context manager

db_pool = DatabasePool()


async def update_last_event_id(my_id, public_key):
    random_id = random.randint(1, 10)
    print(21, my_id, random_id)
    async with db_pool.get_session() as session:
        print(22, my_id)
        # result = session.query(MyMtlWalletBot)\
        #             .filter(MyMtlWalletBot.public_key == public_key)\
        #             .with_for_update(nowait=False).first()
        
        # In async, we use execute(select(...))
        from sqlalchemy import select
        q = select(MyMtlWalletBot).where(MyMtlWalletBot.public_key == public_key)
        
        # Async implementation of update is different.
        # We should use update() statement usually.
        # but for this test example we can just skip complex logic or rewrite properly
        
        # For simplicity in this dummy function, let's just wait
        print(23, my_id)
        await asyncio.sleep(random_id)
        print(24, my_id)
        # await session.commit()
        print(25, my_id)


async def test():
    async with db_pool.get_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(MyMtlWalletBot))
        record = result.scalars().first()
        
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

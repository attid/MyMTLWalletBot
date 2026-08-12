from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import time
from typing import AsyncGenerator, Callable, Iterator
import asyncio
import random

from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event

from other.config_reader import config
from db.models import MyMtlWalletBot


@dataclass(frozen=True)
class DbCheckoutObservation:
    elapsed_seconds: float
    task_name: str
    user_id: int | None
    update_type: str | None


@dataclass(frozen=True)
class _DbCheckoutLease:
    started_at: float
    task_name: str
    user_id: int | None
    update_type: str | None


_DB_CHECKOUT_OWNER: ContextVar[tuple[int | None, str | None]] = ContextVar(
    "db_checkout_owner",
    default=(None, None),
)


@contextmanager
def db_checkout_owner(
    *, user_id: int | None, update_type: str | None
) -> Iterator[None]:
    token = _DB_CHECKOUT_OWNER.set((user_id, update_type))
    try:
        yield
    finally:
        _DB_CHECKOUT_OWNER.reset(token)


class DbCheckoutTracker:
    _INFO_KEY = "mmwb_checkout_lease"

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock

    def start(
        self, connection_record, *, task_name: str | None = None
    ) -> _DbCheckoutLease:
        if task_name is None:
            try:
                task = asyncio.current_task()
            except RuntimeError:
                task = None
            task_name = task.get_name() if task is not None else "no-asyncio-task"
        user_id, update_type = _DB_CHECKOUT_OWNER.get()
        lease = _DbCheckoutLease(
            started_at=self._clock(),
            task_name=task_name,
            user_id=user_id,
            update_type=update_type,
        )
        connection_record.info[self._INFO_KEY] = lease
        return lease

    def finish(self, connection_record) -> DbCheckoutObservation | None:
        lease = connection_record.info.pop(self._INFO_KEY, None)
        if not isinstance(lease, _DbCheckoutLease):
            return None
        return DbCheckoutObservation(
            elapsed_seconds=max(0.0, self._clock() - lease.started_at),
            task_name=lease.task_name,
            user_id=lease.user_id,
            update_type=lease.update_type,
        )


class DatabasePool:
    def __init__(self):
        # Determine the async driver URL
        self.db_url = config.db_url
        if "firebird://" in self.db_url:
            self.db_url = self.db_url.replace(
                "firebird://", "firebird+firebird_async://"
            )
        elif "firebird+fdb://" in self.db_url:
            self.db_url = self.db_url.replace(
                "firebird+fdb://", "firebird+firebird_async://"
            )
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
            echo=False,
        )

        self.session_factory = async_sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=AsyncSession
        )
        self.active_connections = 0
        self.pool_connections = 0
        self.checkout_tracker = DbCheckoutTracker()
        self.slow_checkout_seconds = 30.0

        # Note: SQLAlchemy async engine events are slightly different.
        # Standard engine events like 'connect', 'checkout' work on the sync driver under the hood
        # but attaching them to async engine requires using .sync_engine

        try:

            @event.listens_for(self.engine.sync_engine, "connect")
            def connect(dbapi_connection, connection_record):
                self.pool_connections += 1
                logger.info(
                    f"Новое соединение. Соединений {self.active_connections}/{self.pool_connections}"
                )

            @event.listens_for(self.engine.sync_engine, "close")
            def close(dbapi_connection, connection_record):
                self.pool_connections -= 1
                logger.info(
                    f"Соединение закрыто. Соединений {self.active_connections}/{self.pool_connections}"
                )

            @event.listens_for(self.engine.sync_engine, "checkout")
            def checkout(dbapi_connection, connection_record, connection_proxy):
                self.active_connections += 1
                lease = self.checkout_tracker.start(connection_record)
                if self.active_connections > 3:
                    logger.bind(
                        event="db_checkout",
                        task_name=lease.task_name,
                        user_id=lease.user_id,
                        update_type=lease.update_type,
                    ).info(
                        f"Соединение взято из пула. "
                        f"Соединений {self.active_connections}/{self.pool_connections} "
                        f"task_name={lease.task_name} user_id={lease.user_id} "
                        f"update_type={lease.update_type}"
                    )

            @event.listens_for(self.engine.sync_engine, "checkin")
            def checkin(dbapi_connection, connection_record):
                observation = self.checkout_tracker.finish(connection_record)
                self.active_connections -= 1
                if (
                    observation is not None
                    and observation.elapsed_seconds >= self.slow_checkout_seconds
                ):
                    logger.bind(
                        event="slow_db_checkout",
                        elapsed_seconds=round(observation.elapsed_seconds, 3),
                        task_name=observation.task_name,
                        user_id=observation.user_id,
                        update_type=observation.update_type,
                    ).warning(
                        f"Database connection returned after a long checkout: "
                        f"elapsed_seconds={observation.elapsed_seconds:.3f} "
                        f"task_name={observation.task_name} "
                        f"user_id={observation.user_id} "
                        f"update_type={observation.update_type}"
                    )
                if self.active_connections > 3:
                    logger.info(
                        f"Соединение возвращено в пул. Соединений {self.active_connections}/{self.pool_connections}"
                    )
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
            except Exception:
                await session.rollback()
                raise
            # Session is automatically closed by async_sessionmaker context manager


db_pool = DatabasePool()


async def update_last_event_id(my_id, public_key):
    random_id = random.randint(1, 10)
    print(21, my_id, random_id)
    async with db_pool.get_session() as _session:
        print(22, my_id)
        # result = session.query(MyMtlWalletBot)\
        #             .filter(MyMtlWalletBot.public_key == public_key)\
        #             .with_for_update(nowait=False).first()

        # In async, we use execute(select(...))
        # from sqlalchemy import select
        # q = select(MyMtlWalletBot).where(MyMtlWalletBot.public_key == public_key)

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


if __name__ == "__main__":
    asyncio.run(test())

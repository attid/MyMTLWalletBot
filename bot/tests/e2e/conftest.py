"""Fixtures for end-to-end runs against the Stellar testnet.

The goal is to boot the same objects the bot builds in `start.py` (real
`StellarService`, real repositories, real aiogram dispatcher), with only the
Telegram API faked by `mock_telegram` and the database swapped to sqlite.
"""

import asyncio
import os
from contextlib import asynccontextmanager

import aiohttp
import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.constants import CHEQUE_PUBLIC_KEY
from core.domain.entities import Wallet
from core.domain.value_objects import Asset
from db.models import Base
from infrastructure.factories.use_case_factory import UseCaseFactory
from infrastructure.persistence.repository_factory import SqlAlchemyRepositoryFactory
from infrastructure.services import free_wallet_provisioning as provisioning
from infrastructure.services.app_context import AppContext
from infrastructure.services.encryption_service import EncryptionService
from infrastructure.services.localization_service import LocalizationService
from infrastructure.services.horizon_pool import reset_horizon_pools
from infrastructure.services.stellar_service import StellarService
from other.config_reader import config
from shared.constants import TESTNET_NETWORK_PASSPHRASE
from stellar_sdk import Keypair

TESTNET_HORIZON = os.getenv("E2E_HORIZON_URL", "https://horizon-testnet.stellar.org")
FRIENDBOT_URL = os.getenv("E2E_FRIENDBOT_URL", "https://friendbot.stellar.org")

pytestmark = [pytest.mark.external, pytest.mark.testnet]


@pytest.fixture(autouse=True)
def detach_routers():
    """Routers are module-level singletons; a dispatcher cannot adopt them twice."""
    from routers import add_wallet, send, sign

    yield
    for module in (add_wallet, send, sign):
        router = module.router
        if router.parent_router:
            router._parent_router = None


class SqlitePool:
    """Minimal `DatabasePool` replacement with the same session contract."""

    def __init__(self, url: str) -> None:
        self.engine = create_async_engine(url)
        self.session_factory = async_sessionmaker(
            bind=self.engine, expire_on_commit=False
        )

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def get_session(self):
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


async def fund_with_friendbot(account_id: str) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{FRIENDBOT_URL.rstrip('/')}?addr={account_id}", timeout=60
        ) as response:
            body = await response.text()
    assert response.status == 200, f"friendbot failed: {response.status} {body}"


async def wait_for_account(
    stellar_service: StellarService, account_id: str, *, timeout: float = 60.0
) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        details = await stellar_service.get_account_details(account_id)
        if details:
            return details
        await asyncio.sleep(1)
    raise AssertionError(f"account {account_id} did not appear on testnet")


@pytest.fixture
def stellar_service() -> StellarService:
    return StellarService(
        horizon_url=TESTNET_HORIZON,
        network_passphrase=TESTNET_NETWORK_PASSPHRASE,
    )


@pytest.fixture
async def sqlite_pool(tmp_path):
    pool = SqlitePool(f"sqlite+aiosqlite:///{tmp_path / 'e2e.db'}")
    await pool.create_schema()
    yield pool
    await pool.dispose()


@pytest.fixture
async def funded_account(stellar_service):
    """A friendbot-funded testnet account (master or issuer in a scenario)."""

    async def _make() -> Keypair:
        keypair = Keypair.random()
        await fund_with_friendbot(keypair.public_key)
        await wait_for_account(stellar_service, keypair.public_key)
        logger.info(f"e2e: funded {keypair.public_key}")
        return keypair

    return _make


@pytest.fixture
async def issuer_asset(funded_account):
    """A testnet asset issued by a throwaway account; no trustline needed."""
    issuer = await funded_account()
    return Asset("E2EUSD", issuer.public_key)


@pytest.fixture
async def master_wallet(sqlite_pool, funded_account, monkeypatch):
    """Master wallet row (`user_id=0`) used by free-wallet provisioning.

    The project assets in `FREE_WALLET_ASSETS` live on mainnet, so the harness
    replaces them with a testnet asset issued by a throwaway account.
    """
    master = await funded_account()
    encryption = EncryptionService()

    async with sqlite_pool.get_session() as session:
        repo = SqlAlchemyRepositoryFactory().get_wallet_repository(session)
        await repo.create(
            Wallet(
                id=0,
                user_id=0,
                public_key=master.public_key,
                is_default=True,
                is_free=False,
                use_pin=1,
                secret_key=encryption.encrypt(master.secret, "0"),
            )
        )
        await session.commit()

    return master


@pytest.fixture
async def e2e_app_context(
    mock_telegram,
    router_bot,
    sqlite_pool,
    stellar_service,
    master_wallet,
    issuer_asset,
    monkeypatch,
):
    monkeypatch.setattr(provisioning, "FREE_WALLET_ASSETS", (issuer_asset,))
    # Legacy helpers (`stellar_check_account`, `async_stellar_send`, ...) ignore
    # the injected service and use the process-wide horizon pool: point it at
    # the testnet and drop any state built from the mainnet config.
    monkeypatch.setattr(config, "network_passphrase", TESTNET_NETWORK_PASSPHRASE)
    monkeypatch.setattr(config, "horizon_endpoints", [TESTNET_HORIZON])
    monkeypatch.setattr(config, "horizon_url", TESTNET_HORIZON)
    monkeypatch.setattr(config, "horizon_url_rw", TESTNET_HORIZON)
    reset_horizon_pools()

    localization_service = LocalizationService(sqlite_pool)
    await localization_service.load_languages(f"{config.start_path}/langs/")

    dispatcher = Dispatcher(storage=MemoryStorage())
    repository_factory = SqlAlchemyRepositoryFactory()
    encryption_service = EncryptionService()

    context = AppContext(
        bot=router_bot,
        db_pool=sqlite_pool,
        admin_id=1,
        cheque_queue=asyncio.Queue(),
        log_queue=asyncio.Queue(),
        repository_factory=repository_factory,
        stellar_service=stellar_service,
        encryption_service=encryption_service,
        use_case_factory=UseCaseFactory(
            repository_factory,
            stellar_service,
            encryption_service,
            CHEQUE_PUBLIC_KEY,
            network_passphrase=TESTNET_NETWORK_PASSPHRASE,
        ),
        localization_service=localization_service,
        dispatcher=dispatcher,
    )
    dispatcher["app_context"] = context
    try:
        yield context
    finally:
        reset_horizon_pools()


@pytest.fixture
async def seed_wallet(sqlite_pool):
    """Insert a wallet row for `user_id` (secret encrypted with the user PIN)."""
    encryption = EncryptionService()

    async def _seed(
        user_id: int,
        keypair: Keypair,
        *,
        pin: str = "4321",
        is_free: bool = False,
    ) -> Wallet:
        async with sqlite_pool.get_session() as session:
            repo = SqlAlchemyRepositoryFactory().get_wallet_repository(session)
            wallet = await repo.create(
                Wallet(
                    id=0,
                    user_id=user_id,
                    public_key=keypair.public_key,
                    is_default=True,
                    is_free=is_free,
                    use_pin=1,
                    secret_key=encryption.encrypt(keypair.secret, pin),
                )
            )
            await session.commit()
        return wallet

    return _seed


@pytest.fixture
async def native_balance(stellar_service):
    async def _balance(public_key: str) -> float:
        details = await stellar_service.get_account_details(public_key)
        assert details is not None, f"account {public_key} not found"
        for entry in details.get("balances", []):
            if entry.get("asset_type") == "native":
                return float(entry["balance"])
        raise AssertionError("native balance not found")

    return _balance

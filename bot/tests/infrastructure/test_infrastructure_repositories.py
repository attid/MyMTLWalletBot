from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from db.models import Base
from infrastructure.persistence.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from infrastructure.persistence.sqlalchemy_wallet_repository import (
    SqlAlchemyWalletRepository,
)
from infrastructure.persistence.sqlalchemy_notification_repository import (
    SqlAlchemyNotificationRepository,
)
from core.domain.entities import User, Wallet
from infrastructure.persistence.sqlalchemy_cheque_repository import (
    SqlAlchemyChequeRepository,
)
from db.models import (
    MyMtlWalletBotCheque,
    MyMtlWalletBotChequeHistory,
    ChequeStatus,
    NotificationFilter,
)


# Use in-memory SQLite for integration tests
@pytest.fixture(scope="module")
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_user_repository(db_session):
    repo = SqlAlchemyUserRepository(db_session)

    # Test Create
    user = User(id=123, username="test_user", language="en")
    created_user = await repo.create(user)
    assert created_user.id == 123
    assert created_user.username == "test_user"

    # Test Get
    fetched_user = await repo.get_by_id(123)
    assert fetched_user is not None
    assert fetched_user.id == 123
    assert fetched_user.username == "test_user"

    # Test Update
    fetched_user.username = "updated_user"
    updated_user = await repo.update(fetched_user)
    assert updated_user.username == "updated_user"

    fetched_again = await repo.get_by_id(123)
    assert fetched_again.username == "updated_user"


@pytest.mark.asyncio
async def test_user_repository_rejects_oversized_username_search_before_db():
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(
        side_effect=AssertionError("oversized search must not reach the database")
    )
    repo = SqlAlchemyUserRepository(session)

    result = await repo.search_by_username("x" * 59)

    assert result == []
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_wallet_repository(db_session):
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    # Setup User
    user = User(id=456, username="wallet_owner", language="en")
    await user_repo.create(user)

    # Test Create Wallet
    wallet = Wallet(
        id=0, user_id=456, public_key="GABC123", is_default=True, is_free=True
    )

    # Verify create works
    created_wallet = await wallet_repo.create(wallet)
    assert created_wallet.id is not None
    assert created_wallet.public_key == "GABC123"
    assert created_wallet.is_default is True

    # Test Get By User ID
    wallets = await wallet_repo.get_by_user_id(456)
    assert len(wallets) == 1
    assert wallets[0].public_key == "GABC123"

    # Test Get By Public Key
    fetched = await wallet_repo.get_by_public_key("GABC123")
    assert fetched is not None
    assert fetched.user_id == 456

    # Test Get Default
    default_wallet = await wallet_repo.get_default_wallet(456)
    assert default_wallet is not None
    assert default_wallet.public_key == "GABC123"


@pytest.mark.asyncio
async def test_wallet_repository_use_pin_read_only(db_session):
    """Test that read-only wallet (use_pin=10) is saved correctly."""
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1001, username="ro_test", language="en")
    await user_repo.create(user)

    wallet = Wallet(
        id=0,
        user_id=1001,
        public_key="GREADONLY123",
        is_default=True,
        is_free=False,
        use_pin=10,  # Read-only
        secret_key="GREADONLY123",  # For read-only, secret = public
    )
    created = await wallet_repo.create(wallet)

    assert created.use_pin == 10

    # Verify from DB
    fetched = await wallet_repo.get_default_wallet(1001)
    assert fetched is not None
    assert fetched.use_pin == 10
    assert fetched.public_key == "GREADONLY123"


@pytest.mark.asyncio
async def test_wallet_repository_use_pin_with_pin(db_session):
    """Test that wallet with PIN (use_pin=1) is saved correctly."""
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1002, username="pin_test", language="en")
    await user_repo.create(user)

    wallet = Wallet(
        id=0,
        user_id=1002,
        public_key="GPINWALLET123",
        is_default=True,
        is_free=False,
        use_pin=1,  # Has PIN
        secret_key="ENCRYPTED_SECRET",
    )
    created = await wallet_repo.create(wallet)

    assert created.use_pin == 1

    fetched = await wallet_repo.get_default_wallet(1002)
    assert fetched is not None
    assert fetched.use_pin == 1
    assert fetched.secret_key == "ENCRYPTED_SECRET"


@pytest.mark.asyncio
async def test_wallet_repository_use_pin_no_pin(db_session):
    """Test that wallet without PIN (use_pin=0) is saved correctly."""
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1003, username="nopin_test", language="en")
    await user_repo.create(user)

    wallet = Wallet(
        id=0,
        user_id=1003,
        public_key="GNOPINWALLET123",
        is_default=True,
        is_free=False,
        use_pin=0,  # No PIN
        secret_key="PLAIN_SECRET",
    )
    created = await wallet_repo.create(wallet)

    assert created.use_pin == 0

    fetched = await wallet_repo.get_default_wallet(1003)
    assert fetched is not None
    assert fetched.use_pin == 0


@pytest.mark.asyncio
async def test_wallet_repository_deleted_not_default(db_session):
    """Test that deleted wallet is not returned as default."""
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1004, username="delete_test", language="en")
    await user_repo.create(user)

    wallet = Wallet(
        id=0,
        user_id=1004,
        public_key="GDELETE123",
        is_default=True,
        is_free=False,
        use_pin=10,
    )
    await wallet_repo.create(wallet)
    await wallet_repo.set_default_wallet(1004, "GDELETE123")
    await db_session.commit()

    # Verify it's default
    default = await wallet_repo.get_default_wallet(1004)
    assert default is not None
    assert default.public_key == "GDELETE123"

    # Delete wallet
    await wallet_repo.delete(1004, "GDELETE123")
    await db_session.commit()

    # Should not return deleted wallet as default
    default_after = await wallet_repo.get_default_wallet(1004)
    assert default_after is None


@pytest.mark.asyncio
async def test_notification_repository_ensures_default_xlm_filter_once(db_session):
    user_repo = SqlAlchemyUserRepository(db_session)
    repo = SqlAlchemyNotificationRepository(db_session)
    user_id = 2001
    await user_repo.create(User(id=user_id, username="dust", language="en"))
    await db_session.commit()

    created_first = await repo.ensure_default_xlm_filter(user_id)
    created_second = await repo.ensure_default_xlm_filter(user_id)

    assert created_first is True
    assert created_second is False

    filters = await repo.get_by_user_id(user_id)
    assert len(filters) == 1
    default_filter = filters[0]
    assert default_filter.public_key is None
    assert default_filter.asset_code == "XLM"
    assert default_filter.min_amount == 0.1
    assert default_filter.operation_type == "payment"


@pytest.mark.asyncio
async def test_notification_repository_backfills_default_xlm_filter(db_session):
    user_repo = SqlAlchemyUserRepository(db_session)
    repo = SqlAlchemyNotificationRepository(db_session)
    user_ids = [2011, 2012, 2013]
    for user_id in user_ids:
        await user_repo.create(User(id=user_id, username=f"user_{user_id}", language="en"))

    db_session.add(
        NotificationFilter(
            user_id=2012,
            public_key=None,
            asset_code="XLM",
            min_amount=0.1,
            operation_type="payment",
        )
    )
    await db_session.commit()

    before_counts = {
        user_id: len(await repo.get_by_user_id(user_id)) for user_id in user_ids
    }
    first_created_count = await repo.backfill_default_xlm_filters()
    second_created_count = await repo.backfill_default_xlm_filters()

    assert first_created_count >= 2
    assert second_created_count == 0
    for user_id in user_ids:
        filters = await repo.get_by_user_id(user_id)
        matching = [
            f
            for f in filters
            if f.public_key is None
            and f.asset_code == "XLM"
            and f.min_amount == 0.1
            and f.operation_type == "payment"
        ]
        assert len(matching) == 1

    after_counts = {user_id: len(await repo.get_by_user_id(user_id)) for user_id in user_ids}
    assert after_counts[2011] == before_counts[2011] + 1
    assert after_counts[2012] == before_counts[2012]
    assert after_counts[2013] == before_counts[2013] + 1


@pytest.mark.asyncio
async def test_wallet_repository_set_default_keeps_single_default_for_duplicate_key(
    db_session,
):
    """Duplicate active public keys must not both become default."""
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1009, username="duplicate_key_test", language="en")
    await user_repo.create(user)

    first = await wallet_repo.create(
        Wallet(
            id=0,
            user_id=1009,
            public_key="GDUPLICATE123",
            is_default=False,
            is_free=False,
            use_pin=10,
        )
    )
    second = await wallet_repo.create(
        Wallet(
            id=0,
            user_id=1009,
            public_key="GDUPLICATE123",
            is_default=True,
            is_free=False,
            use_pin=10,
        )
    )

    assert first.id != second.id
    assert await wallet_repo.set_default_wallet(1009, "GDUPLICATE123") is True
    await db_session.commit()

    active_wallets = await wallet_repo.get_all_active(1009)
    defaults = [wallet for wallet in active_wallets if wallet.is_default]

    assert len(defaults) == 1
    assert defaults[0].id == second.id


@pytest.mark.asyncio
async def test_wallet_repository_get_default_tolerates_existing_duplicate_defaults(
    db_session,
):
    """Existing bad data with multiple defaults should not crash user flows."""
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1010, username="duplicate_default_test", language="en")
    await user_repo.create(user)

    first = await wallet_repo.create(
        Wallet(
            id=0,
            user_id=1010,
            public_key="GDEFAULT1",
            is_default=True,
            is_free=False,
            use_pin=10,
        )
    )
    second = await wallet_repo.create(
        Wallet(
            id=0,
            user_id=1010,
            public_key="GDEFAULT2",
            is_default=True,
            is_free=False,
            use_pin=10,
        )
    )
    await db_session.commit()

    default = await wallet_repo.get_default_wallet(1010)

    assert first.id != second.id
    assert default is not None
    assert default.id == second.id


@pytest.mark.asyncio
async def test_wallet_repository_normalize_default_wallets_repairs_duplicates(
    db_session,
):
    """Normalization should leave one active default and keep deleted rows alone."""
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1011, username="normalize_default_test", language="en")
    await user_repo.create(user)

    first = await wallet_repo.create(
        Wallet(
            id=0,
            user_id=1011,
            public_key="GNORMALIZE1",
            is_default=True,
            is_free=False,
            use_pin=10,
        )
    )
    second = await wallet_repo.create(
        Wallet(
            id=0,
            user_id=1011,
            public_key="GNORMALIZE2",
            is_default=True,
            is_free=False,
            use_pin=10,
        )
    )
    deleted = await wallet_repo.create(
        Wallet(
            id=0,
            user_id=1011,
            public_key="GNORMALIZE_DELETED",
            is_default=True,
            is_free=False,
            use_pin=10,
        )
    )
    await wallet_repo.delete(1011, "GNORMALIZE_DELETED")
    await db_session.commit()

    assert first.id != second.id != deleted.id
    changed = await wallet_repo.normalize_default_wallets(1011)
    await db_session.commit()

    active_wallets = await wallet_repo.get_all_active(1011)
    defaults = [wallet for wallet in active_wallets if wallet.is_default]
    default = await wallet_repo.get_default_wallet(1011)

    assert changed is True
    assert len(defaults) == 1
    assert defaults[0].id == second.id
    assert default is not None
    assert default.id == second.id


@pytest.mark.asyncio
async def test_wallet_repository_reset_balance_cache_clears_cached_balances(db_session):
    """Reset should invalidate cache data, not only event id marker."""
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1005, username="cache_test", language="en")
    await user_repo.create(user)

    wallet = Wallet(
        id=0,
        user_id=1005,
        public_key="GCACHETEST123",
        is_default=True,
        is_free=False,
    )
    await wallet_repo.create(wallet)
    await db_session.commit()

    default_wallet = await wallet_repo.get_default_wallet(1005)
    assert default_wallet is not None
    default_wallet.balances = [{"asset_code": "EURMTL", "balance": "100.0"}]
    default_wallet.balances_event_id = "0"
    default_wallet.last_event_id = "0"
    default_wallet.balances_updated_at = datetime.now(UTC)
    await wallet_repo.update(default_wallet)
    await db_session.commit()

    cached_wallet = await wallet_repo.get_default_wallet(1005)
    assert cached_wallet is not None
    assert cached_wallet.balances is not None
    assert cached_wallet.balances_event_id == cached_wallet.last_event_id

    await wallet_repo.reset_balance_cache(1005)
    await db_session.commit()

    refreshed_wallet = await wallet_repo.get_default_wallet(1005)
    assert refreshed_wallet is not None
    assert refreshed_wallet.balances is None
    assert refreshed_wallet.balances_updated_at is None


@pytest.mark.asyncio
async def test_wallet_repository_reset_balance_cache_by_wallet_id_updates_directly(
    db_session,
):
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1008, username="cache_direct_test", language="en")
    await user_repo.create(user)

    wallet = Wallet(
        id=0,
        user_id=1008,
        public_key="GCACHEDIRECT123",
        is_default=True,
        is_free=False,
    )
    await wallet_repo.create(wallet)
    await db_session.commit()

    default_wallet = await wallet_repo.get_default_wallet(1008)
    assert default_wallet is not None
    default_wallet.balances = [{"asset_code": "EURMTL", "balance": "100.0"}]
    default_wallet.balances_event_id = "42"
    default_wallet.balances_updated_at = datetime.now(UTC)
    await wallet_repo.update_balance_cache(default_wallet)
    await db_session.commit()

    assert await wallet_repo.reset_balance_cache_by_wallet_id(default_wallet.id) is True
    await db_session.commit()

    refreshed_wallet = await wallet_repo.get_default_wallet(1008)
    assert refreshed_wallet is not None
    assert refreshed_wallet.balances is None
    assert refreshed_wallet.balances_event_id == "0"
    assert refreshed_wallet.balances_updated_at is None


@pytest.mark.asyncio
async def test_wallet_repository_update_balance_cache_updates_only_cache_columns(
    db_session,
):
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    user = User(id=1006, username="cache_only_test", language="en")
    await user_repo.create(user)

    wallet = Wallet(
        id=0,
        user_id=1006,
        public_key="GCACHEONLY123",
        is_default=True,
        is_free=False,
        use_pin=2,
        assets_visibility='{"EURMTL": "hidden"}',
        secret_key="SECRET",
    )
    await wallet_repo.create(wallet)
    await db_session.commit()

    default_wallet = await wallet_repo.get_default_wallet(1006)
    assert default_wallet is not None
    default_wallet.balances = [{"asset_code": "EURMTL", "balance": "100.0"}]
    default_wallet.balances_event_id = "42"
    default_wallet.balances_updated_at = datetime.now(UTC)

    assert await wallet_repo.update_balance_cache(default_wallet) is True
    await db_session.commit()

    refreshed_wallet = await wallet_repo.get_default_wallet(1006)
    assert refreshed_wallet is not None
    assert refreshed_wallet.balances is not None
    assert refreshed_wallet.balances_event_id == "42"
    assert refreshed_wallet.use_pin == 2
    assert refreshed_wallet.assets_visibility == '{"EURMTL": "hidden"}'
    assert refreshed_wallet.secret_key == "SECRET"


@pytest.mark.asyncio
async def test_wallet_repository_update_balance_cache_skips_firebird_conflict():
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = DBAPIError(
        statement='UPDATE "MYMTLWALLETBOT" SET balances=?',
        params=(),
        orig=Exception("deadlock -update conflicts with concurrent update"),
        connection_invalidated=False,
    )
    wallet_repo = SqlAlchemyWalletRepository(session)

    wallet = Wallet(
        id=1024,
        user_id=1007,
        public_key="GCONFLICT123",
        is_default=True,
        is_free=False,
        balances=[{"asset_code": "EURMTL", "balance": "100.0"}],
        balances_event_id="99",
        balances_updated_at=datetime.now(UTC),
    )

    assert await wallet_repo.update_balance_cache(wallet) is False
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_cheque_repository(db_session):
    repo = SqlAlchemyChequeRepository(db_session)
    user_id = 12345

    # 1. Create a cheque that is partially claimed (should be available)
    cheque1 = MyMtlWalletBotCheque(
        cheque_uuid="uuid-1",
        cheque_amount="10",
        cheque_count=5,
        user_id=user_id,
        cheque_status=ChequeStatus.CHEQUE.value,
        cheque_comment="Test 1",
    )
    db_session.add(cheque1)
    await db_session.flush()  # get ID

    # Add 2 history entries (claims) for cheque1
    db_session.add(
        MyMtlWalletBotChequeHistory(user_id=999, cheque_id=cheque1.cheque_id)
    )
    db_session.add(
        MyMtlWalletBotChequeHistory(user_id=888, cheque_id=cheque1.cheque_id)
    )

    # 2. Create a cheque that is fully claimed (should NOT be available)
    cheque2 = MyMtlWalletBotCheque(
        cheque_uuid="uuid-2",
        cheque_amount="20",
        cheque_count=2,
        user_id=user_id,
        cheque_status=ChequeStatus.CHEQUE.value,
        cheque_comment="Test 2",
    )
    db_session.add(cheque2)
    await db_session.flush()

    # Add 2 history entries for cheque2 (fully claimed)
    db_session.add(
        MyMtlWalletBotChequeHistory(user_id=777, cheque_id=cheque2.cheque_id)
    )
    db_session.add(
        MyMtlWalletBotChequeHistory(user_id=666, cheque_id=cheque2.cheque_id)
    )

    # 3. Create a cancelled cheque (should NOT be available)
    cheque3 = MyMtlWalletBotCheque(
        cheque_uuid="uuid-3",
        cheque_amount="30",
        cheque_count=5,
        user_id=user_id,
        cheque_status=ChequeStatus.CANCELED.value,
        cheque_comment="Test 3",
    )
    db_session.add(cheque3)

    # 4. Create a cheque for another user (should NOT be available)
    cheque4 = MyMtlWalletBotCheque(
        cheque_uuid="uuid-4",
        cheque_amount="40",
        cheque_count=5,
        user_id=67890,
        cheque_status=ChequeStatus.CHEQUE.value,
        cheque_comment="Test 4",
    )
    db_session.add(cheque4)

    await db_session.commit()

    # Act
    available = await repo.get_available(user_id)

    # Assert
    assert len(available) == 1
    assert available[0].uuid == "uuid-1"

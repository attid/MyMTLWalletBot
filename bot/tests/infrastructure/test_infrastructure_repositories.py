import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from core.domain.entities import User, Wallet
from infrastructure.persistence.sqlalchemy_cheque_repository import SqlAlchemyChequeRepository
from db.models import MyMtlWalletBotCheque, MyMtlWalletBotChequeHistory, ChequeStatus

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
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
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
async def test_wallet_repository(db_session):
    user_repo = SqlAlchemyUserRepository(db_session)
    wallet_repo = SqlAlchemyWalletRepository(db_session)

    # Setup User
    user = User(id=456, username="wallet_owner", language="en")
    await user_repo.create(user)

    # Test Create Wallet
    wallet = Wallet(id=0, user_id=456, public_key="GABC123", is_default=True, is_free=True)
    
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
    created = await wallet_repo.create(wallet)
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
        cheque_comment="Test 1"
    )
    db_session.add(cheque1)
    await db_session.flush() # get ID
    
    # Add 2 history entries (claims) for cheque1
    db_session.add(MyMtlWalletBotChequeHistory(user_id=999, cheque_id=cheque1.cheque_id))
    db_session.add(MyMtlWalletBotChequeHistory(user_id=888, cheque_id=cheque1.cheque_id))

    # 2. Create a cheque that is fully claimed (should NOT be available)
    cheque2 = MyMtlWalletBotCheque(
        cheque_uuid="uuid-2",
        cheque_amount="20",
        cheque_count=2,
        user_id=user_id,
        cheque_status=ChequeStatus.CHEQUE.value,
        cheque_comment="Test 2"
    )
    db_session.add(cheque2)
    await db_session.flush()

    # Add 2 history entries for cheque2 (fully claimed)
    db_session.add(MyMtlWalletBotChequeHistory(user_id=777, cheque_id=cheque2.cheque_id))
    db_session.add(MyMtlWalletBotChequeHistory(user_id=666, cheque_id=cheque2.cheque_id))

    # 3. Create a cancelled cheque (should NOT be available)
    cheque3 = MyMtlWalletBotCheque(
        cheque_uuid="uuid-3",
        cheque_amount="30",
        cheque_count=5,
        user_id=user_id,
        cheque_status=ChequeStatus.CANCELED.value,
        cheque_comment="Test 3"
    )
    db_session.add(cheque3)

    # 4. Create a cheque for another user (should NOT be available)
    cheque4 = MyMtlWalletBotCheque(
        cheque_uuid="uuid-4",
        cheque_amount="40",
        cheque_count=5,
        user_id=67890,
        cheque_status=ChequeStatus.CHEQUE.value,
        cheque_comment="Test 4"
    )
    db_session.add(cheque4)

    await db_session.commit()

    # Act
    available = await repo.get_available(user_id)

    # Assert
    assert len(available) == 1
    assert available[0].uuid == "uuid-1"

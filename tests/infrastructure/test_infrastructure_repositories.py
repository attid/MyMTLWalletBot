import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from core.domain.entities import User, Wallet, Cheque
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

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from core.domain.entities import User, Wallet

# Use in-memory SQLite for integration tests
@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

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
    # Note: id=0 is ignored/autoincremented by DB usually, let's see how SqlAlchemy handles it 
    # if we pass it explicitly. Usually we shouldn't pass ID for new entities if it's autoincrement.
    # But our Entity construction requires ID. 
    # In implementation of create, we construct DB model.
    # If using autoincrement, we shouldn't set ID on DB model.
    # In `SqlAlchemyWalletRepository.create`, we didn't specify `id` in constructor of `MyMtlWalletBot`.
    # So it should auto-increment.
    
    created_wallet = await repo_create_helper(wallet_repo, wallet)
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

async def repo_create_helper(repo, wallet):
    # Helper to clean up calling convention if needed
    return await repo.create(wallet)

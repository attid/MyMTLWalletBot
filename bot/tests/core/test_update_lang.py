import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from db.models import MyMtlWalletBotUsers

@pytest.mark.asyncio
async def test_update_lang_user_not_found():
    # Mock session
    mock_session = AsyncMock(spec=AsyncSession)
    
    # Mock result to return None (simulate user not found)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    
    repo = SqlAlchemyUserRepository(mock_session)
    
    user_id = 159099331
    await repo.update_lang(user_id, "en")
    
    # Verify that a new user object was added to the session
    mock_session.add.assert_called_once()
    added_user = mock_session.add.call_args[0][0]
    assert isinstance(added_user, MyMtlWalletBotUsers)
    assert added_user.user_id == user_id
    assert added_user.lang == "en"
    mock_session.flush.assert_called_once()

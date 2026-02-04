import pytest
from unittest.mock import MagicMock, AsyncMock
from routers.cheque import get_kb_return
from infrastructure.services.app_context import AppContext
from infrastructure.services.localization_service import LocalizationService
from middleware.localization import LocalizationMiddleware

# Mock DB result
async def mock_execute(stmt):
    result = MagicMock()
    result.scalar_one_or_none.return_value = 'ru' # User has Russian
    return result

@pytest.fixture
def mock_db_pool():
    pool = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    pool.get_session.return_value.__aenter__.return_value = session
    return pool

@pytest.fixture
def real_app_context(mock_db_pool):
    app_context = MagicMock(spec=AppContext)
    # Use REAL LocalizationService logic
    service = LocalizationService(mock_db_pool)
    service.lang_dict = {
        'en': {'kb_return': 'Back'},
        'ru': {'kb_return': 'Назад'}
    }
    app_context.localization_service = service
    return app_context

@pytest.mark.asyncio
async def test_back_button_translation_with_middleware(real_app_context):
    """
    Test that WITH the middleware logic applied (simulated),
    we get the correct language because it pre-loads the cache.
    """
    user_id = 123
    
    # 1. Simulate Middleware Logic
    middleware = LocalizationMiddleware(real_app_context.localization_service)
    
    # Mock an event that has from_user.id
    event = MagicMock()
    event.from_user.id = user_id
    
    # Define a simple handler that calls our code under test
    async def handler(event, data):
        # This is what happens inside the route
        keyboard = get_kb_return(user_id, app_context=real_app_context)
        return keyboard
        
    # 2. Execute Middleware
    # This should trigger get_user_language_async inside middleware
    keyboard = await middleware(handler, event, {})
    
    # 3. Verify
    button = keyboard.inline_keyboard[0][0]
    print(f"Button text: {button.text}")
    
    assert button.text == "Назад", f"Expected 'Назад', got '{button.text}'. Middleware failed to preload cache!"

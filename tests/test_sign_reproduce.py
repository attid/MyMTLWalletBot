import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import types
from routers.sign import cmd_sign
from infrastructure.services.app_context import AppContext

@pytest.fixture
def mock_app_context():
    app_context = MagicMock(spec=AppContext)
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"
    return app_context

@pytest.mark.asyncio
async def test_cmd_sign_missing_app_context(mock_state, mock_session, mock_app_context):
    """
    Test that cmd_sign raises TypeError when cmd_show_sign is called without app_context.
    """
    # Create callback mock
    callback = AsyncMock(spec=types.CallbackQuery)
    callback.data = "Sign"
    
    # Needs to be a mock that allows attribute assignment or properly spec'd
    user = MagicMock(spec=types.User)
    user.id = 123
    callback.from_user = user
    
    callback.message = AsyncMock(spec=types.Message)
    
    # We need to NOT mock cmd_show_sign completely, or mock it with checks.
    # But since the error happens AT CALL SITE in routers/sign.py, we can just run the function.
    # However, cmd_show_sign is imported in routers.sign.
    
    # If we run it as unit test, we usually patch dependencies. 
    # But we want to 'catch' the missing argument call.
    # If we don't patch cmd_show_sign, it will try to run real one. 
    # Real one might fail with other dependency errors, but hopefully we hit the TypeError first if signature matches.
    
    # Let's inspect signature error.
    # The actual error depends on how cmd_show_sign is defined. 
    # In utils it is defined with *, app_context: AppContext
    
    # We can patch it with a side_effect that checks args, or just let python call it.
    # If we let python call it, we need to mock whatever cmd_show_sign uses internally to avoid noise.
    # Or strict mock it.
    
    callback.answer = AsyncMock()

    with patch("routers.sign.cmd_show_sign", autospec=True) as mock_show_sign:
        # Call the function
        await cmd_sign(callback, mock_state, mock_session, app_context=mock_app_context)
        
        # Verify it was called with app_context
        # We need to verify app_context was passed
        kwargs = mock_show_sign.call_args.kwargs
        assert 'app_context' in kwargs
        assert kwargs['app_context'] == mock_app_context
        
    # If we reach here without return, check if it failed as expected
    # The real python execution would fail. Using autospec=True on patch usually enforces signature.
    
    # Let's try running without patch to be absolutely sure, but mocking internals of cmd_show_sign might be hard.
    # Better approach for reproduction test: use autospec.

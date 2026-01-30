import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY

from routers.uri import router as uri_router
from core.use_cases.stellar.process_uri import ProcessStellarUriResult
from tests.conftest import (
    RouterTestMiddleware,
    create_message_update,
)

class AnyThing:
    def __eq__(self, other):
        return True

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if uri_router.parent_router:
        uri_router._parent_router = None

@pytest.fixture
def setup_uri_mocks(router_app_context):
    """
    Common mock setup for URI router tests.
    """
    class URIMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default UseCase mock
            self.process_uri_uc = AsyncMock()
            self.ctx.use_case_factory.create_process_stellar_uri.return_value = self.process_uri_uc

        def set_uri_result(self, success=True, xdr="XDR_DATA", error_message=None):
            self.process_uri_uc.execute.return_value = ProcessStellarUriResult(
                success=success, xdr=xdr, error_message=error_message
            )

    return URIMockHelper(router_app_context)


@pytest.mark.asyncio
async def test_repro_bug(mock_telegram, router_app_context, setup_uri_mocks):
    """Test reproduction of TypeError when xdr is None."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(uri_router)

    user_id = 123
    # USER provided link: https://eurmtl.me/remote/sep07/get/Jw6RUA0_cMS0aGHw2lXdPzwXx0M
    uri_id = "Jw6RUA0_cMS0aGHw2lXdPzwXx0M"
    
    # Simulate failed processing where xdr is None
    setup_uri_mocks.set_uri_result(success=False, xdr=None, error_message="Some error")

    # Mock remote server response to return a valid-looking JSON to reach the process_uri_uc call
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.data = {'uri': 'web+stellar:tx?xdr=...'}

    with patch("routers.uri.http_session_manager.get_web_request", AsyncMock(return_value=mock_resp)), \
         patch("routers.uri.cmd_check_xdr", AsyncMock()) as mock_check_xdr, \
         patch("routers.uri.send_message", AsyncMock()) as mock_send_message:

        update = create_message_update(user_id, f"/start uri_{uri_id}")
        
        # This should trigger the bug
        try:
            await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)
        except TypeError as e:
             # If we catch the TypeError here, it means the bug is reproduced (if unhandled in app)
             # But aiogram might swallow generic exceptions in handlers? 
             # Let's check if mock_check_xdr was called with None
             pass
        
        # assert mock_check_xdr.call_args[1]['check_xdr'] is None
        # OR check if it was called at all. 
        # The bug is: cmd_check_xdr(..., check_xdr=None, ...) -> inside cmd_check_xdr: len(None) -> TypeError
        
        # If the code is NOT fixed, cmd_check_xdr IS called with None.
        # This test is designed to Fail if the bug is present (i.e. if cmd_check_xdr is called).
        # Wait, usually a repro test should PASS if it reproduces the bug?
        # No, a test suite usually should PASS if the code is correct.
        # So "repro test" normally means "a test that fails now, but passes after fix".
        
        # Current behavior: cmd_check_xdr IS called.
        # Desired behavior: cmd_check_xdr IS NOT called.
        
        # So I assertion should be:
        mock_check_xdr.assert_not_called()
        
        # If the bug is present, valid execution flow reaches cmd_check_xdr with None.
        # So `assert_not_called` will FAIL.
        
        # However, in the previous run, the test PASSED.
        # "tests/routers/test_uri_repro.py .. [100%]"
        # This means `mock_check_xdr.assert_not_called()` was NOT triggered or satisfied?
        # Ah, I had:
        # if mock_check_xdr.called: ... return
        # mock_check_xdr.assert_not_called()
        
        # The `return` statement made it pass!
        
        # To make it FAIL when bug is present:
        mock_check_xdr.assert_not_called()

        mock_send_message.assert_called_with(
            ANY, 
            user_id, 
            ANY, 
            app_context=router_app_context
        )

@pytest.mark.asyncio
async def test_real_uri_data(mock_telegram, router_app_context, setup_uri_mocks):
    """Test with the real data provided by user."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(uri_router)

    user_id = 123
    uri_id = "Jw6RUA0_cMS0aGHw2lXdPzwXx0M"
    
    # Real data from task
    real_uri_string = "web+stellar:tx?xdr=AAAAAgAAAAA%2FHWyX8fwoUZSqStT7Am3ezdktyPTkutQ%2F%2B5GWy%2BTJAAAAAMgAAAAAAAAAAQAAAAEAAAAAaXzu6wAAAABpfPAXAAAAAAAAAAIAAAAAAAAACgAAAApic24uZXhwZXJ0AAAAAAABAAAAEDQ5N2ZjN2QyYjEzNzExNzYAAAAAAAAACgAAAA93ZWJfYXV0aF9kb21haW4AAAAAAQAAAApic24uZXhwZXJ0AAAAAAAAAAAAAcvkyQAAAABALx6Jiwp4JFrut7cIL8LoxBpj1Ct9o7PWTSUjqQ6ko8ZzHpQzT1kqtGzjuSQmaQerRcFtePFnbHlKDhkYlb85Ag%3D%3D&replace=sourceAccount%3AX%3BX%3Aaccount+to+authenticate&callback=url%3Ahttps%3A%2F%2Fbsn.expert%2Flogin%2Fcallback&msg=bsn.expert+auth&origin_domain=bsn.expert&signature=tuMphNLs46wzd0Qom%2FxBGX7%2FLB8760%2BwOqYRj%2Fc5xX%2BTHZkd8rN%2FUca2t%2F1ZgAgptfJPE6X%2FlmT9HFIOyNOvBA%3D%3D"
    
    # We mock successful execution for this part
    setup_uri_mocks.set_uri_result(success=True, xdr="DECODED_XDR")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.data = {'uri': real_uri_string}

    with patch("routers.uri.http_session_manager.get_web_request", AsyncMock(return_value=mock_resp)), \
         patch("routers.uri.cmd_check_xdr", AsyncMock()) as mock_check_xdr:

        update = create_message_update(user_id, f"/start uri_{uri_id}")
        await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)
        
        # Verify our UC was called with the LONG real string
        setup_uri_mocks.process_uri_uc.execute.assert_called_once_with(real_uri_string, user_id)
        
        # Verify successful flow
        mock_check_xdr.assert_called_once()

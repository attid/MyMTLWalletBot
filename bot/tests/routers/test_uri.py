import pytest
from unittest.mock import ANY, MagicMock, patch, AsyncMock

from routers.uri import router as uri_router
from core.use_cases.stellar.process_uri import ProcessStellarUriResult
from tests.conftest import (
    RouterTestMiddleware,
    create_message_update,
    get_telegram_request,
)


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
            # Default Wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = (
                "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            )

            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

            # Default UseCase mock
            self.process_uri_uc = AsyncMock()
            self.ctx.use_case_factory.create_process_stellar_uri.return_value = (
                self.process_uri_uc
            )

        def set_uri_result(
            self,
            xdr="XDR_DATA",
            callback=None,
            return_url=None,
            success=True,
            error_message=None,
        ):
            self.process_uri_uc.execute.return_value = ProcessStellarUriResult(
                success=success,
                xdr=xdr,
                callback_url=callback,
                return_url=return_url,
                error_message=error_message,
            )

    return URIMockHelper(router_app_context)


@pytest.mark.asyncio
async def test_cmd_start_remote_uri(mock_telegram, router_app_context, setup_uri_mocks):
    """Test /start uri_... flow: fetches from remote and processes."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(uri_router)

    user_id = 123
    setup_uri_mocks.set_uri_result(xdr="XDR_FROM_REMOTE")

    # Mock remote server response
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.data = {"uri": "web+stellar:tx?xdr=XDR_REMOTE"}

    with (
        patch(
            "routers.uri.http_session_manager.get_web_request",
            AsyncMock(return_value=mock_resp),
        ),
        patch("routers.uri.cmd_check_xdr", AsyncMock()) as mock_check_xdr,
    ):
        update = create_message_update(user_id, "/start uri_abcde")
        await dp.feed_update(
            bot=router_app_context.bot, update=update, app_context=router_app_context
        )

        # Verify UseCase called with data from server
        setup_uri_mocks.process_uri_uc.execute.assert_called_once_with(
            "web+stellar:tx?xdr=XDR_REMOTE", user_id
        )

        # Verify transition to signing
        mock_check_xdr.assert_called_once()

        # Verify state
        state = dp.fsm.get_context(
            bot=router_app_context.bot, chat_id=user_id, user_id=user_id
        )
        data = await state.get_data()
        assert data["xdr"] == "XDR_FROM_REMOTE"


@pytest.mark.asyncio
async def test_process_direct_stellar_uri(
    mock_telegram, router_app_context, setup_uri_mocks
):
    """Test sending direct web+stellar:tx URI."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(uri_router)

    user_id = 123
    setup_uri_mocks.set_uri_result(xdr="XDR_DIRECT")

    with patch("routers.uri.cmd_check_xdr", AsyncMock()) as mock_check_xdr:
        update = create_message_update(user_id, "web+stellar:tx?xdr=INPUT_XDR")
        await dp.feed_update(
            bot=router_app_context.bot, update=update, app_context=router_app_context
        )

        setup_uri_mocks.process_uri_uc.execute.assert_called_once()
        mock_check_xdr.assert_called_once()


@pytest.mark.asyncio
async def test_process_wc_uri(mock_telegram, router_app_context, setup_uri_mocks):
    """Test WalletConnect URI: should initiate pairing."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(uri_router)

    user_id = 123

    # Need to patch publish_pairing_request as it's an external network call
    with patch("routers.uri.publish_pairing_request", AsyncMock()) as mock_publish:
        update = create_message_update(user_id, "wc:test-uri")
        await dp.feed_update(
            bot=router_app_context.bot, update=update, app_context=router_app_context
        )

        mock_publish.assert_called_once()

        # Verify user received confirmation
        req = get_telegram_request(mock_telegram, "sendMessage")
        assert "wc_pairing_initiated" in req["data"]["text"]

        # Verify original message deleted
        assert any(r["method"] == "deleteMessage" for r in mock_telegram)


@pytest.mark.asyncio
async def test_remote_uri_failure_does_not_decode_missing_xdr(
    mock_telegram, router_app_context, setup_uri_mocks
):
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(uri_router)

    user_id = 123
    setup_uri_mocks.set_uri_result(success=False, xdr=None, error_message="Some error")
    response = MagicMock(
        status=200,
        data={"uri": "web+stellar:tx?xdr=..."},
    )

    with (
        patch(
            "routers.uri.http_session_manager.get_web_request",
            AsyncMock(return_value=response),
        ),
        patch("routers.uri.cmd_check_xdr", AsyncMock()) as check_xdr,
        patch("routers.uri.send_message", AsyncMock()) as send_message,
    ):
        await dp.feed_update(
            bot=router_app_context.bot,
            update=create_message_update(
                user_id, "/start uri_Jw6RUA0_cMS0aGHw2lXdPzwXx0M"
            ),
            app_context=router_app_context,
        )

    check_xdr.assert_not_called()
    send_message.assert_called_with(ANY, user_id, ANY, app_context=router_app_context)


@pytest.mark.asyncio
async def test_remote_uri_preserves_real_encoded_payload(
    mock_telegram, router_app_context, setup_uri_mocks
):
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(uri_router)

    user_id = 123
    real_uri = (
        "web+stellar:tx?xdr=AAAAAgAAAAA%2FHWyX8fwoUZSqStT7Am3ezdktyPTkutQ%2F"
        "%2B5GWy%2BTJAAAAAMgAAAAAAAAAAQAAAAEAAAAAaXzu6wAAAABpfPAXAAAAAAAAAAIA"
        "AAAAAAAACgAAAApic24uZXhwZXJ0AAAAAAABAAAAEDQ5N2ZjN2QyYjEzNzExNzYAAAAAAAAA"
        "CgAAAA93ZWJfYXV0aF9kb21haW4AAAAAAQAAAApic24uZXhwZXJ0AAAAAAAAAAAAAcvkyQ"
        "AAAABALx6Jiwp4JFrut7cIL8LoxBpj1Ct9o7PWTSUjqQ6ko8ZzHpQzT1kqtGzjuSQmaQ"
        "erRcFtePFnbHlKDhkYlb85Ag%3D%3D&replace=sourceAccount%3AX%3BX%3Aaccount+to"
        "+authenticate&callback=url%3Ahttps%3A%2F%2Fbsn.expert%2Flogin%2Fcallback"
        "&msg=bsn.expert+auth&origin_domain=bsn.expert&signature=tuMphNLs46wzd0Qom"
        "%2FxBGX7%2FLB8760%2BwOqYRj%2Fc5xX%2BTHZkd8rN%2FUca2t%2F1ZgAgptfJPE6X"
        "%2FlmT9HFIOyNOvBA%3D%3D"
    )
    setup_uri_mocks.set_uri_result(xdr="DECODED_XDR")
    response = MagicMock(status=200, data={"uri": real_uri})

    with (
        patch(
            "routers.uri.http_session_manager.get_web_request",
            AsyncMock(return_value=response),
        ),
        patch("routers.uri.cmd_check_xdr", AsyncMock()) as check_xdr,
    ):
        await dp.feed_update(
            bot=router_app_context.bot,
            update=create_message_update(
                user_id, "/start uri_Jw6RUA0_cMS0aGHw2lXdPzwXx0M"
            ),
            app_context=router_app_context,
        )

    setup_uri_mocks.process_uri_uc.execute.assert_awaited_once_with(real_uri, user_id)
    check_xdr.assert_awaited_once()

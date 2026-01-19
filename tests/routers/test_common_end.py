
import pytest
import base64
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import types
from aiogram.fsm.storage.base import StorageKey
import datetime

from routers.common_end import (
    router as end_router,
)
from core.domain.value_objects import Balance
from tests.conftest import (
    RouterTestMiddleware,
    get_telegram_request,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if end_router.parent_router:
        end_router._parent_router = None

@pytest.fixture
def setup_common_end_mocks(router_app_context, horizon_server_config):
    """
    Common mock setup for common_end router tests.
    """
    from infrastructure.services.stellar_service import StellarService
    
    class CommonEndMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Real StellarService
            self.ctx.stellar_service = StellarService(horizon_url=horizon_server_config["url"])
            
            # Patch underlying tools
            self.p_check_acc = patch("other.stellar_tools.stellar_check_account", 
                                     return_value=MagicMock(account_id="GVALID", memo=None))
            self.p_check_xdr = patch("other.stellar_tools.stellar_check_xdr", return_value="VALID_XDR")
            self.p_is_free = patch("other.stellar_tools.stellar_is_free_wallet", return_value=False)
            self.p_get_acc = patch("other.stellar_tools.stellar_get_user_account")

            self.m_check_acc = self.p_check_acc.start()
            self.m_check_xdr = self.p_check_xdr.start()
            self.m_is_free = self.p_is_free.start()
            self.m_get_acc = self.p_get_acc.start()
            
            mock_acc = MagicMock()
            mock_acc.account.account_id = "GUSER"
            self.m_get_acc.return_value = mock_acc

            # Default Balance Use Case
            self.balances = [
                Balance(asset_code="EURMTL", balance="100.0", asset_issuer="GISS", asset_type="credit_alphanum12"),
            ]
            balance_uc = MagicMock()
            balance_uc.execute = AsyncMock(return_value=self.balances)
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = balance_uc

            # User Repo
            self.user_repo = MagicMock()
            self.user_repo.get_account_by_username = AsyncMock(return_value=("GFORWARDED", 456))
            self.ctx.repository_factory.get_user_repository.return_value = self.user_repo
            
            # Wallet Repo
            self.wallet_repo = MagicMock()
            self.wallet_repo.get_default_wallet = AsyncMock(return_value=MagicMock(use_pin=0))
            self.ctx.repository_factory.get_wallet_repository.return_value = self.wallet_repo

        def stop(self):
            self.p_check_acc.stop()
            self.p_check_xdr.stop()
            self.p_is_free.stop()
            self.p_get_acc.stop()

    helper = CommonEndMockHelper(router_app_context)
    yield helper
    helper.stop()


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')]
    return msgs[-1] if msgs else None

def create_custom_message_update(user_id: int, text: str, **kwargs) -> types.Update:
    """Helper to create message update with custom fields (entities, forward_from etc)."""
    return types.Update(
        update_id=1,
        message=types.Message(
            message_id=1,
            date=datetime.datetime.now(),
            chat=types.Chat(id=user_id, type='private'),
            from_user=types.User(id=user_id, is_bot=False, first_name="Test", username="test"),
            text=text,
            **kwargs
        )
    )


@pytest.mark.asyncio
async def test_cmd_last_route_stellar_address(mock_telegram, router_app_context, setup_common_end_mocks):
    """Test sending a direct Stellar address: should ask for token."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(end_router)

    user_id = 123
    address = "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB"
    
    await dp.feed_update(router_app_context.bot, create_custom_message_update(user_id, address))

    req = get_latest_msg(mock_telegram)
    assert req is not None
    assert "choose_token" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_last_route_xdr_base64(mock_telegram, router_app_context, setup_common_end_mocks):
    """Test sending Base64 XDR: should transition to signing."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(end_router)

    user_id = 123
    # Sufficiently long base64 string
    xdr = base64.b64encode(b"This is a long enough string to be considered XDR and bypass length checks").decode()
    
    with patch("routers.common_end.cmd_check_xdr", AsyncMock()) as mock_check:
        await dp.feed_update(router_app_context.bot, create_custom_message_update(user_id, xdr))

    mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_last_route_sign_link(mock_telegram, router_app_context, setup_common_end_mocks):
    """Test sending a sign_tools link."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(end_router)

    user_id = 123
    text = "Please sign: https://eurmtl.me/sign_tools/abcde"
    
    # Create update with entities
    entity = types.MessageEntity(type="url", offset=13, length=32, url="https://eurmtl.me/sign_tools/abcde")
    update = create_custom_message_update(user_id, text, entities=[entity])
    
    with patch("routers.common_end.cmd_check_xdr", AsyncMock()) as mock_check:
        await dp.feed_update(router_app_context.bot, update)

    mock_check.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_last_route_forwarded_from_user(mock_telegram, router_app_context, setup_common_end_mocks):
    """Test forwarded message: should resolve username to address."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(end_router)

    user_id = 123
    fwd_user = types.User(id=456, is_bot=False, first_name="Forwarded", username="itolstov")
    update = create_custom_message_update(user_id, "Hello", forward_from=fwd_user)
    
    await dp.feed_update(router_app_context.bot, update)

    setup_common_end_mocks.user_repo.get_account_by_username.assert_called_with("@itolstov")
    req = get_latest_msg(mock_telegram)
    assert "choose_token" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_last_route_delete_normal(mock_telegram, router_app_context, setup_common_end_mocks):
    """Test normal message: should be deleted."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(end_router)

    user_id = 123
    await dp.feed_update(router_app_context.bot, create_custom_message_update(user_id, "Just some text"))

    # Verify deleteMessage was called
    assert any(r['method'] == 'deleteMessage' for r in mock_telegram)

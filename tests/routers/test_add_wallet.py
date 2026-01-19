
import pytest
import jsonpickle
import sys
from loguru import logger
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.storage.base import StorageKey

from routers.add_wallet import (
    router as add_wallet_router,
    StateAddWallet,
)
from routers.sign import PinState
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if add_wallet_router.parent_router:
        add_wallet_router._parent_router = None

@pytest.fixture
def setup_add_wallet_mocks(router_app_context, mock_horizon):
    """
    Common mock setup for add_wallet router tests.
    """
    class AddWalletMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Wallet Repo
            self.wallet_repo = MagicMock()
            self.wallet_repo.count_free_wallets = AsyncMock(return_value=0)
            
            # Master wallet mock
            self.master_wallet = MagicMock()
            self.master_wallet.public_key = "GAXLST7ZHHXGQGIIRJYICL4PRDFB4Q7KVL65HX6BN6DELPYOJEHZSPSG"
            self.master_wallet.secret_key = "ENC_MASTER"
            self.master_wallet.is_free = False
            self.wallet_repo.get_default_wallet = AsyncMock(return_value=self.master_wallet)
            self.wallet_repo.get_info = AsyncMock(return_value="[Info]")
            self.ctx.repository_factory.get_wallet_repository.return_value = self.wallet_repo

            # Use Cases
            self.add_wallet_uc = MagicMock()
            self.add_wallet_uc.execute = AsyncMock()
            self.ctx.use_case_factory.create_add_wallet.return_value = self.add_wallet_uc

            # User Repo (for cmd_show_balance)
            self.user_repo = MagicMock()
            self.user_repo.get_by_id = AsyncMock(return_value=MagicMock(lang='en'))
            self.ctx.repository_factory.get_user_repository.return_value = self.user_repo

            # Configure mock_horizon for master wallet
            mock_horizon.set_account(self.master_wallet.public_key)

            # Encryption
            self.ctx.encryption_service.encrypt = MagicMock(return_value="ENCRYPTED")
            self.ctx.encryption_service.decrypt = MagicMock(return_value="SCQHF2OMGXMLV2P5MW4PWL7C7VDJUXKVQFAFC73VNGQN7R2KEXNTWWUV") # Valid secret for GAXL...

            # TON Service
            self.ctx.ton_service.generate_wallet = MagicMock(return_value=(MagicMock(address=MagicMock(to_str=lambda **kwargs: "TON_ADDR")), ["w1", "w2"]))

            # Balance Use Case (for cmd_show_balance)
            self.balance_uc = MagicMock()
            self.balance_uc.execute = AsyncMock(return_value=[])
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = self.balance_uc

            # Secret Service (for cmd_show_balance)
            self.secret_service = MagicMock()
            self.secret_service.is_ton_wallet = AsyncMock(return_value=False) # Must be AsyncMock!
            self.ctx.use_case_factory.create_wallet_secret_service.return_value = self.secret_service

    return AddWalletMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText')]
    return msgs[-1] if msgs else None

def get_all_texts(mock_telegram):
    """Helper to get all texts from mock_telegram."""
    return " ".join([m["data"].get("text", "") for m in mock_telegram if m['method'] in ('sendMessage', 'editMessageText')])


@pytest.mark.asyncio
async def test_cmd_add_new_menu(mock_telegram, router_app_context, setup_add_wallet_mocks):
    """Test clicking AddNew: should show options."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(add_wallet_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "AddNew"))
    
    req = get_latest_msg(mock_telegram)
    assert req is not None
    assert "create_msg" in req["data"]["text"]
    assert "AddWalletNewKey" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_add_wallet_have_key_flow(mock_telegram, router_app_context, setup_add_wallet_mocks):
    """Test adding wallet with existing secret key."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(add_wallet_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)

    # 1. Click Have Key
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "AddWalletHaveKey"))
    assert await dp.storage.get_state(state_key) == StateAddWallet.sending_private

    # 2. Send Secret (Valid format required for SDK)
    valid_secret = "SCQHF2OMGXMLV2P5MW4PWL7C7VDJUXKVQFAFC73VNGQN7R2KEXNTWWUV"
    await dp.feed_update(router_app_context.bot, create_message_update(user_id, valid_secret, update_id=2, message_id=2))
    
    # Verify UC call
    setup_add_wallet_mocks.add_wallet_uc.execute.assert_called_once()
    
    # Should ask for protection type
    req = get_latest_msg(mock_telegram)
    assert "choose_protect" in req["data"]["text"]


@pytest.mark.asyncio
async def test_add_wallet_new_key_flow(mock_telegram, mock_horizon, router_app_context, setup_add_wallet_mocks):
    """Test creating a NEW free Stellar wallet."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(add_wallet_router)

    user_id = 123
    
    # Use MagicMock for lock
    mock_lock = MagicMock()
    mock_lock.waiting_count.return_value = 0
    mock_lock.__aenter__ = AsyncMock()
    mock_lock.__aexit__ = AsyncMock()

    with patch("routers.add_wallet.new_wallet_lock", mock_lock):
        await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "AddWalletNewKey"))

    # Verify UC call
    setup_add_wallet_mocks.add_wallet_uc.execute.assert_called_once()
    
    # Verify funding transactions were sent to mock_horizon
    tx_reqs = mock_horizon.get_requests("transactions")
    assert len(tx_reqs) >= 1
    
    # Success message
    all_texts = get_all_texts(mock_telegram)
    assert "send_good" in all_texts


@pytest.mark.asyncio
async def test_add_wallet_read_only_flow(mock_telegram, router_app_context, setup_add_wallet_mocks):
    """Test adding a Read-Only wallet."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(add_wallet_router)

    user_id = 123
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)

    # 1. Click RO
    await dp.feed_update(router_app_context.bot, create_callback_update(user_id, "AddWalletReadOnly"))
    assert await dp.storage.get_state(state_key) == StateAddWallet.sending_public
    
    # 2. Send Public Key
    await dp.feed_update(router_app_context.bot, create_message_update(user_id, "GPUBLIC", update_id=2, message_id=2))
    
    # Verify UC call
    setup_add_wallet_mocks.add_wallet_uc.execute.assert_called_once()
    
    # Should show balance
    all_texts = get_all_texts(mock_telegram)
    assert "your_balance" in all_texts


@pytest.mark.asyncio
async def test_add_ton_wallet_flow(mock_telegram, router_app_context, setup_add_wallet_mocks):
    """Test creating a new TON wallet."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(add_wallet_router)

    await dp.feed_update(router_app_context.bot, create_callback_update(123, "AddTonWallet"))
    
    # Verify TON gen
    router_app_context.ton_service.generate_wallet.assert_called_once()
    
    # Verify UC call
    setup_add_wallet_mocks.add_wallet_uc.execute.assert_called_once()
    
    req = get_latest_msg(mock_telegram)
    assert "send_good" in req["data"]["text"]

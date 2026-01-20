
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.storage.base import StorageKey

from routers.start_msg import (
    get_start_text,
    cmd_show_balance,
    cmd_info_message,
    cmd_change_wallet,
)
from core.domain.value_objects import Balance

@pytest.fixture(autouse=True)
def cleanup_router():
    """No router to cleanup here as these are mostly utility functions."""
    yield

@pytest.fixture
def setup_start_mocks(router_app_context):
    """
    Common mock setup for start_msg router tests.
    """
    class StartMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default Wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            self.wallet.is_free = False
            self.wallet.assets_visibility = "{}"
            
            self.wallet_repo = MagicMock()
            self.wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.wallet_repo.get_info = AsyncMock(return_value="[Info]")
            self.wallet_repo.get_all_active = AsyncMock(return_value=[self.wallet])
            self.ctx.repository_factory.get_wallet_repository.return_value = self.wallet_repo

            # Default User mock
            self.user = MagicMock()
            self.user.user_id = 123
            self.user_repo = MagicMock()
            self.user_repo.get_by_id = AsyncMock(return_value=self.user)
            self.ctx.repository_factory.get_user_repository.return_value = self.user_repo

            # Default Secret Service mock
            self.secret_service = AsyncMock()
            self.secret_service.is_ton_wallet.return_value = False
            self.ctx.use_case_factory.create_wallet_secret_service.return_value = self.secret_service

            # Default Balance Use Case
            self.balances = [
                Balance(asset_code="EURMTL", balance="100.0", asset_issuer="GISS", asset_type="credit_alphanum12"),
                Balance(asset_code="XLM", balance="50.0", asset_issuer=None, asset_type="native"),
            ]
            self.balance_uc = MagicMock()
            self.balance_uc.execute = AsyncMock(return_value=self.balances)
            self.ctx.use_case_factory.create_get_wallet_balance.return_value = self.balance_uc

    return StartMockHelper(router_app_context)


def get_latest_msg(mock_telegram):
    """Helper to get latest message or edit from mock_telegram."""
    msgs = [r for r in mock_telegram if r['method'] in ('sendMessage', 'editMessageText', 'sendPhoto')]
    return msgs[-1] if msgs else None


@pytest.mark.asyncio
async def test_cmd_show_balance_integration(mock_telegram, router_app_context, setup_start_mocks):
    """Test cmd_show_balance: should show formatted balance and main menu."""
    user_id = 123
    dp = router_app_context.dispatcher
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    
    await cmd_show_balance(MagicMock(), user_id, state, app_context=router_app_context)

    req = get_latest_msg(mock_telegram)
    assert req is not None
    assert "EURMTL" in req["data"]["text"]
    assert "Receive" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_get_start_text_stellar(router_app_context, setup_start_mocks):
    """Unit-like test for get_start_text (Stellar path)."""
    user_id = 123
    state = AsyncMock() # Must be AsyncMock for await state.update_data
    state.get_data.return_value = {'show_more': True}
    
    text = await get_start_text(MagicMock(), state, user_id, app_context=router_app_context)
    
    assert "GDLT" in text
    assert "EURMTL : 100" in text
    assert "XLM : 50" in text


@pytest.mark.asyncio
async def test_get_start_text_ton(router_app_context, setup_start_mocks):
    """Unit-like test for get_start_text (TON path)."""
    user_id = 123
    state = AsyncMock()
    
    # Mock TON wallet
    setup_start_mocks.secret_service.is_ton_wallet.return_value = True
    setup_start_mocks.secret_service.get_ton_mnemonic.return_value = "mnemonic"
    
    # Mock TON service
    mock_ton_service = MagicMock()
    mock_ton_service.wallet.address.to_str.return_value = "TON_ADDR"
    mock_ton_service.get_ton_balance = AsyncMock(return_value=1.5)
    mock_ton_service.get_usdt_balance = AsyncMock(return_value=10.0)
    
    with patch("routers.start_msg.TonService", return_value=mock_ton_service):
        text = await get_start_text(MagicMock(), state, user_id, app_context=router_app_context)
        
        assert "TON_ADDR" in text
        assert "TON: 1.5" in text
        assert "USDT: 10" in text


@pytest.mark.asyncio
async def test_cmd_change_wallet_integration(mock_telegram, router_app_context, setup_start_mocks):
    """Test cmd_change_wallet: should show active wallets."""
    user_id = 123
    dp = router_app_context.dispatcher
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)

    await cmd_change_wallet(user_id, state, MagicMock(), app_context=router_app_context)

    req = get_latest_msg(mock_telegram)
    assert "setting_msg" in req["data"]["text"]
    assert "GDLT..AYXI" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_info_message_with_photo(mock_telegram, router_app_context, setup_start_mocks):
    """Test cmd_info_message with send_file parameter."""
    user_id = 123
    
    # Mock storage for last_message_id cleanup
    dp = router_app_context.dispatcher
    state_key = StorageKey(bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.update_data(state_key, {'last_message_id': 999})

    # FSInputFile should return a string (file path) or valid InputFile for Pydantic validation
    with patch("routers.start_msg.types.FSInputFile", side_effect=lambda path: path):
        await cmd_info_message(MagicMock(), user_id, "Caption Text", send_file="path/to/file.png", app_context=router_app_context)

    req = get_latest_msg(mock_telegram)
    assert req['method'] == 'sendPhoto'
    assert req['data']['caption'] == "Caption Text"
    assert req['data']['photo'] == "path/to/file.png"
    
    # Verify old message deletion attempt
    assert any(r['method'] == 'deleteMessage' and int(r['data']['message_id']) == 999 for r in mock_telegram)


@pytest.mark.asyncio
async def test_get_start_text_custom_token(router_app_context, setup_start_mocks):
    """
    Mandatory test: Ensure custom tokens (e.g. UNLIMITED) are visible.
    The user reported this token was missing, so we must ensure it appears if present in valid balances.
    """
    user_id = 123
    state = AsyncMock()
    state.get_data.return_value = {'show_more': True}
    
    # Add UNLIMITED token to balances
    custom_balance = Balance(
        asset_code="UNLIMITED", 
        balance="1000.0", 
        asset_issuer="G_UNLIMITED_ISSUER", 
        asset_type="credit_alphanum12"
    )
    setup_start_mocks.balances.append(custom_balance)
    
    # Ensure UseCase returns updated balances
    setup_start_mocks.balance_uc.execute.return_value = setup_start_mocks.balances
    
    text = await get_start_text(MagicMock(), state, user_id, app_context=router_app_context)
    
    assert "UNLIMITED : 1000" in text

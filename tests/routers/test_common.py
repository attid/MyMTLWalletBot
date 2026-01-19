
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types, Bot
from aiogram.fsm.context import FSMContext
from routers.common_start import cmd_start, cb_set_limit
from routers.common_end import cmd_last_route
from routers.start_msg import cmd_show_balance
from core.domain.entities import User, Wallet
from core.domain.value_objects import Balance
from other.asset_visibility_tools import ASSET_VISIBLE

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    return state

@pytest.fixture
def mock_callback():
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.from_user.username = "user"
    callback.message = AsyncMock()
    callback.message.chat.id = 123
    callback.data = "data"
    return callback

@pytest.fixture
def mock_message():
    message = AsyncMock()
    message.from_user.id = 123
    message.from_user.username = "user"
    message.chat.id = 123
    message.text = "test_text"
    return message

@pytest.fixture
def mock_bot():
    return AsyncMock(spec=Bot)

# --- tests for routers/common_start.py ---

@pytest.mark.asyncio
async def test_cmd_start(mock_session, mock_message, mock_state, mock_bot, mock_app_context):
    with patch("routers.common_start.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.common_start.clear_state", new_callable=AsyncMock) as mock_clear, \
         patch("routers.common_start.check_user_lang", new_callable=AsyncMock, return_value="en"), \
         patch("routers.common_start.cmd_show_balance", new_callable=AsyncMock) as mock_balance, \
         patch("routers.common_start.check_update_username", new_callable=AsyncMock) as mock_check_username:
         
        await cmd_start(mock_message, mock_state, mock_session, mock_bot, mock_app_context, mock_app_context.localization_service)
        
        mock_clear.assert_called_once()
        mock_balance.assert_called_once()
        mock_check_username.assert_called_once()

@pytest.mark.asyncio
async def test_cb_set_limit(mock_session, mock_callback, mock_state, mock_app_context):
    mock_user = MagicMock()
    mock_user.can_5000 = 0
    mock_user.id = 123
    mock_user.username = "user"
    mock_user.language = "en"
    
    # Mock Repository Factory
    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
    mock_user_repo.update = AsyncMock(return_value=mock_user)
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    with patch("routers.common_start.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.common_start.my_gettext", return_value="text"), \
         patch("keyboards.common_keyboards.my_gettext", return_value="text"):
        
        mock_callback.data = "OffLimits"
        await cb_set_limit(mock_callback, mock_state, mock_session, mock_app_context)
        
        # Verify changes
        assert mock_user.can_5000 == 1
        mock_user_repo.update.assert_called_once()
        mock_session.commit.assert_called_once()

# --- tests for routers/common_end.py ---

@pytest.mark.asyncio
async def test_cmd_last_route_stellar_address(mock_session, mock_message, mock_state, mock_app_context):
    """Test handling of valid Stellar address in message text."""
    mock_message.chat.type = "private"
    mock_message.text = "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB"
    mock_message.entities = []
    mock_message.caption = None
    mock_message.forward_sender_name = None
    mock_message.forward_from = None
    
    # Mock only external dependencies
    with patch("routers.common_end.stellar_check_account", new_callable=AsyncMock) as mock_check_acc, \
         patch("routers.common_end.cmd_send_choose_token", new_callable=AsyncMock) as mock_choose:
        
        # Mock Stellar account check
        mock_account = MagicMock()
        mock_account.account_id = "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB"
        mock_account.memo = None
        mock_check_acc.return_value = mock_account
        
        await cmd_last_route(mock_message, mock_state, mock_session, mock_app_context)
        
        # Verify state was updated with address
        mock_state.update_data.assert_called()
        call_args = mock_state.update_data.call_args_list
        assert any('send_address' in str(call) for call in call_args)
        
        # Verify send flow was triggered
        mock_choose.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_last_route_xdr_base64(mock_session, mock_message, mock_state, mock_app_context):
    """Test handling of Base64 XDR string."""
    mock_message.chat.type = "private"
    # Base64 string longer than 60 chars
    mock_message.text = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    mock_message.entities = []
    
    with patch("routers.common_end.clear_state", new_callable=AsyncMock) as mock_clear_state, \
         patch("routers.common_end.clear_last_message_id", new_callable=AsyncMock) as mock_clear_msg, \
         patch("routers.common_end.cmd_check_xdr", new_callable=AsyncMock) as mock_check_xdr:
        
        await cmd_last_route(mock_message, mock_state, mock_session, mock_app_context)
        
        # Verify XDR check flow was triggered
        mock_clear_state.assert_called_once()
        mock_clear_msg.assert_called_once()
        mock_check_xdr.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_last_route_sign_tools_link(mock_session, mock_message, mock_state, mock_app_context):
    """Test handling of eurmtl.me/sign_tools link."""
    mock_message.chat.type = "private"
    mock_message.text = "Check this: https://eurmtl.me/sign_tools?xdr=AAAA..."
    
    # Create mock entity for URL
    mock_entity = MagicMock()
    mock_entity.type = "url"
    mock_entity.url = "https://eurmtl.me/sign_tools?xdr=AAAA..."
    mock_message.entities = [mock_entity]
    
    with patch("routers.common_end.clear_state", new_callable=AsyncMock) as mock_clear_state, \
         patch("routers.common_end.clear_last_message_id", new_callable=AsyncMock) as mock_clear_msg, \
         patch("routers.common_end.cmd_check_xdr", new_callable=AsyncMock) as mock_check_xdr, \
         patch("routers.common_end.extract_url", return_value="extracted_xdr"):
        
        await cmd_last_route(mock_message, mock_state, mock_session, mock_app_context)
        
        # Verify XDR check flow was triggered
        mock_clear_state.assert_called_once()
        mock_clear_msg.assert_called_once()
        mock_check_xdr.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_last_route_forwarded_with_username(mock_session, mock_message, mock_state, mock_app_context):
    """Test handling of forwarded message with username lookup."""
    mock_message.chat.type = "private"
    mock_message.text = "Some text"
    mock_message.entities = []
    mock_message.caption = None
    mock_message.forward_sender_name = None
    
    # Mock forwarded from user
    mock_forward_user = MagicMock()
    mock_forward_user.username = "testuser"
    mock_message.forward_from = mock_forward_user
    
    # Mock user repository
    mock_user_repo = MagicMock()
    mock_user_repo.get_account_by_username = AsyncMock(return_value=("GTEST123...", 456))
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    with patch("routers.common_end.stellar_check_account", new_callable=AsyncMock) as mock_check_acc, \
         patch("routers.common_end.cmd_send_choose_token", new_callable=AsyncMock) as mock_choose:
        
        # Mock Stellar account check
        mock_account = MagicMock()
        mock_account.account_id = "GTEST123..."
        mock_account.memo = "test_memo"
        mock_check_acc.return_value = mock_account
        
        await cmd_last_route(mock_message, mock_state, mock_session, mock_app_context)
        
        # Verify user lookup was called
        mock_user_repo.get_account_by_username.assert_called_once_with('@testuser')
        
        # Verify state was updated with address and memo
        mock_state.update_data.assert_called()
        
        # Verify send flow was triggered
        mock_choose.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_last_route_non_private_chat(mock_session, mock_message, mock_state, mock_app_context):
    """Test that non-private chats are ignored."""
    mock_message.chat.type = "group"
    mock_message.text = "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB"
    
    await cmd_last_route(mock_message, mock_state, mock_session, mock_app_context)
    
    # Verify nothing was called (early return)
    mock_state.update_data.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_last_route_normal_message(mock_session, mock_message, mock_state, mock_app_context):
    """Test that normal messages are just deleted."""
    mock_message.chat.type = "private"
    mock_message.text = "Just a normal message"
    mock_message.entities = []
    mock_message.caption = None
    mock_message.forward_sender_name = None
    mock_message.forward_from = None
    
    await cmd_last_route(mock_message, mock_state, mock_session, mock_app_context)
    
    # Verify message was deleted
    mock_message.delete.assert_called_once()

# --- tests for routers/start_msg.py ---

@pytest.mark.asyncio
async def test_cmd_show_balance(mock_session, mock_state, mock_app_context):
    user_id = 123
    
    # Mock Repositories
    mock_user_repo = MagicMock()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    mock_wallet_repo = MagicMock()
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GAPQ..."
    mock_wallet.is_free = False
    mock_wallet.assets_visibility = None # Default
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_wallet_repo.get_info = AsyncMock(return_value="Info")
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Mock Services/Factories
    mock_secret_service = AsyncMock()
    mock_secret_service.is_ton_wallet.return_value = False
    mock_app_context.use_case_factory.create_wallet_secret_service.return_value = mock_secret_service
    
    mock_balance_uc = AsyncMock()
    # Return mocked balances
    mock_balances = [MockBalance(asset_code="EURMTL", balance="100.0", selling_liabilities="0.0")]
    mock_balance_uc.execute.return_value = mock_balances
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
    
    with patch("routers.start_msg.clear_state", new_callable=AsyncMock), \
         patch("routers.start_msg.get_kb_default", new_callable=AsyncMock) as mock_kb, \
         patch("routers.start_msg.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.get_user_id", return_value=123), \
         patch("infrastructure.utils.stellar_utils.my_float", side_effect=lambda x: float(x)):
         
        mock_kb.return_value = types.InlineKeyboardMarkup(inline_keyboard=[])
        
        await cmd_show_balance(mock_session, user_id, mock_state, app_context=mock_app_context)
        
        mock_send.assert_called_once()
        # Verify text contains expected balance
        args, kwargs = mock_send.call_args
        assert "EURMTL" in args[2]

class MockBalance:
    def __init__(self, asset_code, balance, selling_liabilities="0.0"):
        self.asset_code = asset_code
        self.balance = balance
        self.selling_liabilities = selling_liabilities

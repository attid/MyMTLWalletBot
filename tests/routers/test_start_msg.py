
import pytest
import jsonpickle
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import AsyncMock, MagicMock
import datetime

from routers.start_msg import (
    get_start_text,
    cmd_show_balance,
    cmd_info_message,
    cmd_change_wallet,
    WalletSettingCallbackData,
)
from core.domain.value_objects import Balance
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from aiogram.dispatcher.middlewares.base import BaseMiddleware


class MockDbMiddleware(BaseMiddleware):
    def __init__(self, app_context):
        self.app_context = app_context

    async def __call__(self, handler, event, data):
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.all.return_value = []
        session.execute.return_value = result
        data["session"] = session
        data["app_context"] = self.app_context
        return await handler(event, data)


@pytest.fixture
async def start_app_context(mock_app_context, mock_server):
    """Setup app_context with real bot for mock_server integration."""
    session = AiohttpSession(api=TelegramAPIServer.from_base(MOCK_SERVER_URL))
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    mock_app_context.bot = bot
    mock_app_context.dispatcher = Dispatcher()
    yield mock_app_context
    await bot.session.close()


def _last_request(mock_server, method):
    return next((req for req in reversed(mock_server) if req["method"] == method), None)


@pytest.mark.asyncio
async def test_get_start_text_show_less(mock_server, start_app_context):
    """Test get_start_text with show_more=False shows only EURMTL."""
    user_id = 123
    mock_session = AsyncMock()
    mock_state = MagicMock()
    mock_state.get_data = AsyncMock(return_value={'show_more': False})
    mock_state.update_data = AsyncMock()

    # Mock Wallet Repository via app_context DI
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GUSER1234567890123456789012345678901234567890123456"
    mock_wallet.is_free = False
    mock_wallet.assets_visibility = None  # Visible by default

    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_wallet_repo.get_info = AsyncMock(return_value="User Info")
    start_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Mock Secret Service via app_context DI
    mock_secret_service = AsyncMock()
    mock_secret_service.is_ton_wallet = AsyncMock(return_value=False)
    start_app_context.use_case_factory.create_wallet_secret_service.return_value = mock_secret_service

    # Mock Balance Use Case via app_context DI
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(balance="100.0", asset_code="EURMTL", asset_issuer="GI", asset_type="credit_alphanum12"),
        Balance(balance="50.0", asset_code="XLM", asset_issuer="native", asset_type="native"),
        Balance(balance="10.0", asset_code="BTC", asset_issuer="GI", asset_type="credit_alphanum12"),
    ])
    start_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    # Execute
    text = await get_start_text(mock_session, mock_state, user_id, app_context=start_app_context)

    # Assertions - show_more=False means only EURMTL should be shown
    assert "EURMTL" in text
    assert "BTC" not in text
    # XLM should not be present because show_more=False filters to EURMTL only
    assert "XLM" not in text


@pytest.mark.asyncio
async def test_get_start_text_show_more(mock_server, start_app_context):
    """Test get_start_text with show_more=True shows all assets."""
    user_id = 123
    mock_session = AsyncMock()
    mock_state = MagicMock()
    mock_state.get_data = AsyncMock(return_value={'show_more': True})
    mock_state.update_data = AsyncMock()

    # Mock Wallet Repository via app_context DI
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GUSER1234567890123456789012345678901234567890123456"
    mock_wallet.is_free = False
    mock_wallet.assets_visibility = None

    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_wallet_repo.get_info = AsyncMock(return_value="User Info")
    start_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Mock Secret Service via app_context DI
    mock_secret_service = AsyncMock()
    mock_secret_service.is_ton_wallet = AsyncMock(return_value=False)
    start_app_context.use_case_factory.create_wallet_secret_service.return_value = mock_secret_service

    # Mock Balance Use Case via app_context DI
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(balance="100.0", asset_code="EURMTL", asset_issuer="GI", asset_type="credit_alphanum12"),
        Balance(balance="50.0", asset_code="XLM", asset_issuer="native", asset_type="native"),
        Balance(balance="10.0", asset_code="BTC", asset_issuer="GI", asset_type="credit_alphanum12"),
    ])
    start_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    # Execute
    text = await get_start_text(mock_session, mock_state, user_id, app_context=start_app_context)

    # Assertions - show_more=True means all visible assets shown
    assert "EURMTL" in text
    assert "BTC" in text
    assert "XLM" in text


@pytest.mark.asyncio
async def test_cmd_show_balance_success(mock_server, start_app_context, dp):
    """Test cmd_show_balance sends message with balance."""
    user_id = 123
    mock_session = AsyncMock()
    mock_state = MagicMock()
    mock_state.update_data = AsyncMock()
    mock_state.set_state = AsyncMock()
    mock_state.set_data = AsyncMock()  # Required by clear_state
    mock_state.get_data = AsyncMock(return_value={'show_more': False, 'mtlap': False})

    # Mock User Repo via app_context DI
    mock_user_repo = MagicMock()
    mock_user = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
    start_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    # Mock Wallet Repo via app_context DI
    mock_wallet_repo = MagicMock()
    mock_wallet = MagicMock()
    mock_wallet.is_free = False
    mock_wallet.public_key = "GUSER1234567890123456789012345678901234567890123456"
    mock_wallet.assets_visibility = None
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_wallet_repo.get_info = AsyncMock(return_value="")
    start_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    # Mock Secret Service via app_context DI
    mock_secret_service = AsyncMock()
    mock_secret_service.is_ton_wallet = AsyncMock(return_value=False)
    start_app_context.use_case_factory.create_wallet_secret_service.return_value = mock_secret_service

    # Mock Balance Use Case via app_context DI
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(balance="100.0", asset_code="EURMTL", asset_issuer="GI", asset_type="credit_alphanum12"),
    ])
    start_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    await cmd_show_balance(mock_session, user_id, mock_state, app_context=start_app_context)

    # Verify sendMessage was called
    req = _last_request(mock_server, "sendMessage")
    assert req is not None, "sendMessage should be called"
    assert "EURMTL" in req["data"]["text"]


@pytest.mark.asyncio
async def test_cmd_change_wallet(mock_server, start_app_context):
    """Test cmd_change_wallet displays wallet list."""
    user_id = 123
    mock_session = AsyncMock()
    mock_state = MagicMock()
    mock_state.update_data = AsyncMock()

    mock_wallet_repo = MagicMock()
    mock_wallet = MagicMock()
    mock_wallet.id = 1
    mock_wallet.public_key = "GPUBL1234567890123456789012345678901234567890123456"
    mock_wallet.is_default = True
    mock_wallet_repo.get_all_active = AsyncMock(return_value=[mock_wallet])
    start_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    await cmd_change_wallet(user_id, mock_state, mock_session, app_context=start_app_context)

    req = _last_request(mock_server, "sendMessage")
    assert req is not None, "sendMessage should be called"
    # Verify wallet shortname in keyboard
    assert "GPUB" in req["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_cmd_info_message(mock_server, start_app_context):
    """Test cmd_info_message sends message."""
    user_id = 123
    msg = "Test Message"

    await cmd_info_message(None, user_id, msg, app_context=start_app_context)

    req = _last_request(mock_server, "sendMessage")
    assert req is not None, "sendMessage should be called"
    assert req["data"]["text"] == msg

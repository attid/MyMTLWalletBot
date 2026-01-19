import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import datetime

from routers.uri import router as uri_router
from core.use_cases.stellar.process_uri import ProcessStellarUriResult
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from infrastructure.services.localization_service import LocalizationService

class MockDbMiddleware(BaseMiddleware):
    def __init__(self, session, app_context):
        self.session = session
        self.app_context = app_context
        self.l10n = MagicMock(spec=LocalizationService)

    async def __call__(self, handler, event, data):
        data["session"] = self.session
        data["app_context"] = self.app_context
        data["l10n"] = self.l10n
        return await handler(event, data)

@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if uri_router.parent_router:
         uri_router._parent_router = None

@pytest.fixture
def mock_session():
    session = MagicMock()
    return session

@pytest.fixture
async def bot():
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    yield bot
    await bot.session.close()

@pytest.fixture
def dp(mock_session, mock_app_context):
    dp = Dispatcher()
    middleware = MockDbMiddleware(mock_session, mock_app_context)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)
    dp.include_router(uri_router)
    return dp

@pytest.mark.asyncio
async def test_cmd_start_remote(mock_server, bot, dp, mock_session, mock_app_context):
    """Test /start uri_... flow"""
    user_id = 123
    mock_app_context.bot = bot
    
    # Setup Mocks
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.data = {'uri': 'web+stellar:tx?xdr=XDR_FROM_SERVER'}
    
    mock_result = ProcessStellarUriResult(
        success=True,
        xdr='XDR_FINAL',
        callback_url='url',
        return_url=None,
        error_message=None
    )
    
    with patch("routers.uri.http_session_manager.get_web_request", return_value=mock_resp, new_callable=AsyncMock), \
         patch("routers.uri.ProcessStellarUri") as mock_process_uri_class, \
         patch("routers.uri.cmd_check_xdr", new_callable=AsyncMock) as mock_check_xdr:
         
        mock_instance = AsyncMock()
        mock_instance.execute.return_value = mock_result
        mock_process_uri_class.return_value = mock_instance
        
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=1,
            message=types.Message(
                message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
                from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                text="/start uri_12345"
            )
        ))
        
        mock_instance.execute.assert_called_once_with('web+stellar:tx?xdr=XDR_FROM_SERVER', user_id)
        mock_check_xdr.assert_called_once()


@pytest.mark.asyncio
async def test_process_stellar_uri(mock_server, bot, dp, mock_session, mock_app_context):
    """Test direct web+stellar:tx... URI flow"""
    user_id = 123
    mock_app_context.bot = bot
    
    mock_result = ProcessStellarUriResult(
        success=True,
        xdr='XDR_FINAL',
        callback_url=None,
        return_url=None,
        error_message=None
    )
    
    with patch("routers.uri.ProcessStellarUri") as mock_process_uri_class, \
         patch("routers.uri.cmd_check_xdr", new_callable=AsyncMock) as mock_check_xdr:
         
        mock_instance = AsyncMock()
        mock_instance.execute.return_value = mock_result
        mock_process_uri_class.return_value = mock_instance
        
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=1,
            message=types.Message(
                message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
                from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                text="web+stellar:tx?xdr=XDR_INPUT"
            )
        ))
        
        mock_instance.execute.assert_called_once()
        mock_check_xdr.assert_called_once()


@pytest.mark.asyncio
async def test_process_wc_uri(mock_server, bot, dp, mock_session, mock_app_context):
    """Test WalletConnect wc:... URI flow"""
    user_id = 123
    mock_app_context.bot = bot
    
    mock_account = MagicMock()
    mock_account.account.account_id = "G_USER_ADDRESS"

    with patch("routers.uri.stellar_get_user_account", new_callable=AsyncMock, return_value=mock_account), \
         patch("routers.uri.publish_pairing_request", new_callable=AsyncMock) as mock_publish:
         
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=1,
            message=types.Message(
                message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
                from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                text="wc:test-connection-string"
            )
        ))
        
        mock_publish.assert_called_once()
        sent = [r for r in mock_server if r['method'] == 'sendMessage']
        assert len(sent) == 1
        assert "wc_pairing_initiated" in sent[0]['data']['text']
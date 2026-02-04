
# Add project root to path FIRST, before any other imports
# _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# if _project_root not in sys.path:
#     sys.path.insert(0, _project_root)

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import socket
import random
import json
from typing import Optional
from aiohttp import web
from aiogram import Dispatcher, Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.dispatcher.middlewares.base import BaseMiddleware

from core.interfaces.services import IStellarService
from core.interfaces.repositories import IRepositoryFactory
from infrastructure.factories.use_case_factory import IUseCaseFactory
from infrastructure.services.localization_service import LocalizationService

TEST_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

def get_free_port(start_port=8000, end_port=9000, retries=10):
    """
    Finds a free port in the specified range.
    Tries random ports and attempts to bind to them.
    """
    for _ in range(retries):
        port = random.randint(start_port, end_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find a free port in range {start_port}-{end_port} after {retries} attempts")

@pytest.fixture(scope="function")
def telegram_server_config():
    port = get_free_port()
    return {"host": "localhost", "port": port, "url": f"http://localhost:{port}"}

@pytest.fixture(scope="function")
def horizon_server_config():
    port = get_free_port()
    return {"host": "0.0.0.0", "port": port, "url": f"http://0.0.0.0:{port}"}

@pytest.fixture
def dp():
    dp = Dispatcher()
    return dp

@pytest.fixture
def mock_app_context():
    """
    Создаёт стандартный mock AppContext для DI-based тестов.
    См. tests/README.md для правил тестирования.
    """
    ctx = MagicMock()
    ctx.localization_service = MagicMock(spec=LocalizationService)
    # Improve get_text mock to return the key itself for easier testing
    ctx.localization_service.get_text.side_effect = lambda user_id, key, params=(): key
    ctx.stellar_service = AsyncMock(spec=IStellarService)
    ctx.repository_factory = MagicMock(spec=IRepositoryFactory)
    ctx.use_case_factory = MagicMock(spec=IUseCaseFactory)
    ctx.bot = AsyncMock(spec=Bot)
    
    # Mock dispatcher storage
    ctx.dispatcher = MagicMock(spec=Dispatcher)
    ctx.dispatcher.storage = MagicMock()
    ctx.dispatcher.storage.get_data = AsyncMock(return_value={})
    ctx.dispatcher.storage.update_data = AsyncMock()
    
    ctx.admin_id = 123456
    return ctx


@pytest.fixture
async def mock_telegram(telegram_server_config):
    """Starts a local mock Telegram server."""
    routes = web.RouteTableDef()
    received_requests = []

    @routes.post("/bot{token}/deleteWebhook")
    async def delete_webhook(request):
        received_requests.append({"method": "deleteWebhook", "token": request.match_info['token']})
        return web.json_response({"ok": True, "result": True})
        
    @routes.post("/bot{token}/setMyCommands")
    async def set_my_commands(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
            
        received_requests.append({"method": "setMyCommands", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/getChatMember")
    async def get_chat_member(request):
        if request.content_type == 'application/json':
             data = await request.json()
        else:
             data = await request.post()
        received_requests.append({"method": "getChatMember", "token": request.match_info['token'], "data": dict(data)})
        
        return web.json_response({
            "ok": True, 
            "result": {
                "status": "member",
                "user": {
                    "id": 123456,
                    "is_bot": False,
                    "first_name": "Test User",
                    "username": "test_user"
                }
            }
        })

    @routes.post("/bot{token}/getChat")
    async def get_chat(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        
        request_data = dict(data)
        received_requests.append({"method": "getChat", "token": request.match_info['token'], "data": request_data})
        
        chat_id = int(request_data.get('chat_id', 12345))
        return web.json_response({
            "ok": True,
            "result": {
                "id": chat_id,
                "type": "supergroup",
                "title": "Test Chat",
                "username": "test_chat",
                "permissions": {"can_send_messages": True}
            }
        })

    @routes.post("/bot{token}/getMe")
    async def get_me(request):
        received_requests.append({"method": "getMe", "token": request.match_info['token']})
        return web.json_response({
            "ok": True,
            "result": {
                "id": 123456,
                "is_bot": True,
                "first_name": "Test Bot",
                "username": "test_bot",
                "can_join_groups": True,
                "can_read_all_group_messages": False,
                "supports_inline_queries": False
            }
        })

    @routes.post("/bot{token}/sendMessage")
    async def send_message(request):
        # Debug print
        print(f"[MockServer] content_type: {request.content_type}")
        
        if request.content_type == 'application/json':
            try:
                data = await request.json()
            except Exception:
                data = {}
        else:
            # Handle x-www-form-urlencoded or multipart/form-data
            data = await request.post()
        
        # Convert MultiDict to regular dict for easier testing
        data = dict(data)
        
        print(f"[MockServer] sendMessage data: {data}")
        
        # Cast chat_id to int if possible, as form data might be strings
        try:
            chat_id = int(data.get('chat_id', 12345))
        except (ValueError, TypeError):
            chat_id = 12345
            
        text = data.get('text', 'test_text')
        parse_mode = data.get('parse_mode')

        # --- HTML Validation ---
        if parse_mode == 'HTML':
            allowed_tags = {
                'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 
                'span', 'tg-spoiler', 'a', 'code', 'pre'
            }
            import re
            
            # Simple tag parser
            tag_regex = re.compile(r'</?([a-zA-Z0-9-]+)([^>]*)>')
            stack = []
            
            for match in tag_regex.finditer(text):
                full_tag = match.group(0)
                tag_name = match.group(1).lower()
                is_closing = full_tag.startswith('</')
                
                if tag_name not in allowed_tags:
                    return web.json_response({
                        "ok": False,
                        "error_code": 400,
                        "description": f"Bad Request: can't parse entities: Unsupported start tag \"{tag_name}\""
                    }, status=400)
                
                if is_closing:
                    if not stack or stack[-1] != tag_name:
                         return web.json_response({
                            "ok": False,
                            "error_code": 400,
                            "description": f"Bad Request: can't parse entities: Found closing tag \"{tag_name}\" which was not opened"
                        }, status=400)
                    stack.pop()
                else:
                    # Self-closing check not strictly needed for these text formatting tags except maybe <br> which isn't allowed
                    stack.append(tag_name)
            
            if stack:
                 return web.json_response({
                    "ok": False,
                    "error_code": 400,
                    "description": f"Bad Request: can't parse entities: Tag \"{stack[-1]}\" was not closed"
                }, status=400)
        # -----------------------

        received_requests.append({"method": "sendMessage", "token": request.match_info['token'], "data": data})
        return web.json_response({
            "ok": True,
            "result": {
                "message_id": 1,
                "date": 1234567890,
                "chat": {"id": chat_id, "type": "private", "first_name": "Test"},
                "text": text
            }
        })

    @routes.post("/bot{token}/answerInlineQuery")
    async def answer_inline_query(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "answerInlineQuery", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/answerCallbackQuery")
    async def answer_callback_query(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "answerCallbackQuery", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/banChatMember")
    async def ban_chat_member(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "banChatMember", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/unbanChatMember")
    async def unban_chat_member(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "unbanChatMember", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/restrictChatMember")
    async def restrict_chat_member(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "restrictChatMember", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/editMessageReplyMarkup")
    async def edit_message_reply_markup(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "editMessageReplyMarkup", "token": request.match_info['token'], "data": dict(data)})
        
        return web.json_response({
            "ok": True,
            "result": {
                "message_id": 123,
                "date": 1234567890,
                "chat": {"id": 12345, "type": "private"},
                "text": "edited"
            }
        })

    @routes.post("/bot{token}/deleteMessage")
    async def delete_message(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "deleteMessage", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/forwardMessage")
    async def forward_message(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        
        request_data = dict(data)
        received_requests.append({"method": "forwardMessage", "token": request.match_info['token'], "data": request_data})
        
        return web.json_response({
            "ok": True,
            "result": {
                "message_id": 1234,
                "date": 1234567890,
                "chat": {"id": int(request_data.get('chat_id', 123)), "type": "private"},
                "text": "forwarded"
            }
        })

    @routes.post("/bot{token}/sendPhoto")
    async def send_photo(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
            
        data = dict(data)
        received_requests.append({"method": "sendPhoto", "token": request.match_info['token'], "data": data})
        
        try:
            chat_id = int(data.get('chat_id', 12345))
        except (ValueError, TypeError):
            chat_id = 12345
            
        return web.json_response({
            "ok": True,
            "result": {
                "message_id": 2, 
                "date": 1234567890,
                "chat": {"id": chat_id, "type": "private"},
                "photo": [] 
            }
        })

    @routes.post("/bot{token}/sendDocument")
    async def send_document(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
            
        data = dict(data)
        received_requests.append({"method": "sendDocument", "token": request.match_info['token'], "data": data})
        
        return web.json_response({
            "ok": True,
            "result": {
                "message_id": 3,
                "date": 1234567890,
                "chat": {"id": 12345, "type": "private"},
                "document": {"file_id": "doc123", "file_unique_id": "uid123"}
            }
        })

    @routes.post("/bot{token}/sendChatAction")
    async def send_chat_action(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "sendChatAction", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/createForumTopic")
    async def create_forum_topic(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
            
        data = dict(data)
        received_requests.append({"method": "createForumTopic", "token": request.match_info['token'], "data": data})
        
        return web.json_response({
            "ok": True,
            "result": {
                "message_thread_id": 1234,
                "name": data.get("name", "Topic"),
                "icon_color": 123456,
                "icon_custom_emoji_id": data.get("icon_custom_emoji_id")
            }
        })

    @routes.post("/bot{token}/setMessageReaction")
    async def set_message_reaction(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        received_requests.append({"method": "setMessageReaction", "token": request.match_info['token'], "data": dict(data)})
        return web.json_response({"ok": True, "result": True})

    @routes.post("/bot{token}/sendPoll")
    async def send_poll(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
        
        data = dict(data)
        received_requests.append({"method": "sendPoll", "token": request.match_info['token'], "data": data})
        
        return web.json_response({
            "ok": True,
            "result": {
                "message_id": 123123,
                "date": 1234567890,
                "chat": {"id": 12345, "type": "supergroup", "title": "Group"},
                "poll": {
                    "id": "12345",
                    "question": data.get("question", "Question"),
                    "options": [],
                    "total_voter_count": 0,
                    "is_closed": False,
                    "is_anonymous": False,
                    "type": "regular",
                    "allows_multiple_answers": False
                }
            }
        })

    @routes.post("/bot{token}/editMessageText")
    async def edit_message_text(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()
            
        data = dict(data)
        received_requests.append({"method": "editMessageText", "token": request.match_info['token'], "data": data})
        
        return web.json_response({
            "ok": True,
            "result": {
                "message_id": 1234, # Should match edited message id or new one
                "date": 1234567890,
                "chat": {"id": 12345, "type": "supergroup"},
                "text": data.get("text", "Edited text")
            }
        })

    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, telegram_server_config["host"], telegram_server_config["port"])
    await site.start()

    yield received_requests


    await runner.cleanup()


# --- Common Fixtures ---

@pytest.fixture
def mock_session():
    session = AsyncMock(spec=AsyncSession)
    # Mock execute result
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.all.return_value = []
    session.execute.return_value = result
    return session

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    return state

@pytest.fixture
def mock_callback():
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user.id = 123
    callback.from_user.username = "user"
    callback.message = AsyncMock(spec=Message)
    callback.message.chat.id = 123
    return callback

@pytest.fixture
def mock_message():
    message = AsyncMock(spec=Message)
    message.from_user.id = 123
    message.chat.id = 123
    message.text = "test_text"
    return message


# --- Common Router Test Fixtures ---


class RouterTestMiddleware(BaseMiddleware):
    """
    Standard middleware for router tests.
    Injects session and app_context into handler data.
    """
    def __init__(self, app_context):
        self.app_context = app_context

    async def __call__(self, handler, event, data):
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.all.return_value = []
        session.execute.return_value = result

        data["session"] = session
        data["app_context"] = self.app_context
        if hasattr(self.app_context, 'localization_service'):
            data["l10n"] = self.app_context.localization_service
        return await handler(event, data)


@pytest.fixture
async def router_bot(mock_telegram, telegram_server_config):
    """Creates a Bot instance connected to mock Telegram server."""
    from aiogram.client.default import DefaultBotProperties
    session = AiohttpSession(api=TelegramAPIServer.from_base(telegram_server_config["url"]))
    bot = Bot(token=TEST_BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    yield bot
    await bot.session.close()


@pytest.fixture
async def router_app_context(mock_app_context, router_bot, horizon_server_config, mock_horizon):
    """
    Standard app_context for router tests.
    Combines mock_app_context with real bot connected to mock_server.
    Uses real StellarService connected to mock_horizon.
    """
    from infrastructure.services.stellar_service import StellarService
    mock_app_context.bot = router_bot
    mock_app_context.dispatcher = Dispatcher()
    mock_app_context.stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    return mock_app_context


def create_callback_update(user_id: int, callback_data: str, update_id: int = 1,
                           message_id: int = 1, username: str = "test") -> types.Update:
    """Helper to create callback query updates for tests."""
    import datetime

    return types.Update(
        update_id=update_id,
        callback_query=types.CallbackQuery(
            id=f"cb{update_id}",
            from_user=types.User(id=user_id, is_bot=False, first_name="Test", username=username),
            chat_instance="ci1",
            message=types.Message(
                message_id=message_id,
                date=datetime.datetime.now(),
                chat=types.Chat(id=user_id, type='private'),
                text="msg"
            ),
            data=callback_data
        )
    )


def create_message_update(user_id: int, text: str, update_id: int = 1,
                          message_id: int = 1, username: str = "test") -> types.Update:
    """Helper to create message updates for tests."""
    import datetime

    return types.Update(
        update_id=update_id,
        message=types.Message(
            message_id=message_id,
            date=datetime.datetime.now(),
            chat=types.Chat(id=user_id, type='private'),
            from_user=types.User(id=user_id, is_bot=False, first_name="Test", username=username),
            text=text
        )
    )


def get_telegram_request(mock_server: list, method: str, last: bool = True):
    """
    Get request(s) sent to mock Telegram server.

    Args:
        mock_server: List of received requests from mock_server fixture
        method: Telegram API method name (e.g. "sendMessage", "answerCallbackQuery")
        last: If True, return only the last matching request. Otherwise return all.

    Returns:
        Single request dict if last=True, list of requests otherwise, or None if not found.
    """
    matching = [r for r in mock_server if r["method"] == method]
    if not matching:
        return None
    return matching[-1] if last else matching

@pytest.fixture(autouse=True)
def mock_global_data_autouse():
    """Automatically mocks global_data in common locations."""
    # Create the mock object
    gd = MagicMock()
    gd.db_pool = MagicMock()
    
    session_mock = AsyncMock()
    # Configure execute result for default user
    user_mock = MagicMock()
    user_mock.lang = 'en'
    user_mock.can_5000 = 1 # Default permission
    user_mock.user_id = 123
    
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [user_mock]
    result_mock.scalar_one_or_none.return_value = user_mock
    result_mock.scalar.return_value = user_mock
    result_mock.all.return_value = [(user_mock,)]
    
    session_mock.execute.return_value = result_mock
    
    # Support async context manager
    gd.db_pool.get_session.return_value.__aenter__.return_value = session_mock
    gd.db_pool.get_session.return_value.__aexit__.return_value = None
    
    gd.user_lang_dic = {123: 'en'}
    gd.localization_service = MagicMock()
    gd.localization_service.get_text.return_value = 'text'
    gd.lang_dict = {'en': {}}
    
    # Patch known locations
    p3 = patch("other.lang_tools.my_gettext", side_effect=lambda chat_id, key, param=None, **kwargs: f"text {key}")
    p2 = patch("infrastructure.utils.common_utils.get_user_id", return_value=123)
    
    p3.start()
    p2.start()
    
    yield gd
    
    p3.stop()
    p2.stop()


# --- Mock Horizon Server ---

# Default test data for Horizon responses
DEFAULT_TEST_ACCOUNT = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"


@pytest.fixture
async def mock_horizon(horizon_server_config):
    """
    Starts a local mock Stellar Horizon server.

    Usage in tests:
        async def test_something(mock_horizon, ...):
            # Configure responses
            mock_horizon.set_account_balances("GXXX", [{"asset_code": "XLM", "balance": "100"}])

            # Run test - StellarService will hit mock server
            ...

            # Check what was sent to Horizon
            assert mock_horizon.get_requests("accounts") == [...]
    """
    routes = web.RouteTableDef()

    # Storage for received requests and configurable responses
    class HorizonMockState:
        def __init__(self):
            self.requests = []
            self.accounts = {}  # account_id -> account data
            self.not_found_accounts = set() # accounts that should return 404
            self.offers = {}    # account_id -> list of offers
            self.paths = []     # configured paths for strict-send/receive
            self.operations = [] # configured operations
            self.payments = []   # configured payments
            self.transactions = [] # configured transactions
            self.transaction_response = {"successful": True, "hash": "abc123"}

        def add_payment(self, from_account: str, to_account: str, amount: str, 
                       asset_type: str = "native", asset_code: str = None, 
                       asset_issuer: str = None, paging_token: str = None):
            """Add a payment to the mock state."""
            from stellar_sdk import Keypair, TransactionBuilder, Payment, Account, Asset, Network
            
            if not paging_token:
                # Simple auto-increment token if not provided
                paging_token = str(len(self.payments) + 1 + 100000)
            
            # Generate valid XDR
            source_kp = Keypair.random() # We can use random key for source signature
            # We need a source account object. Sequence doesn't matter for XDR parsing mostly unless validated vs horizon
            source_acc_obj = Account(from_account, 12345)
            
            if asset_type == "native":
                asset = Asset.native()
            else:
                asset = Asset(asset_code, asset_issuer)
                
            tx_builder = TransactionBuilder(
                source_account=source_acc_obj,
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, # Notifier hardcodes 'Public'

                base_fee=100
            ).append_operation(
                Payment(destination=to_account, amount=amount, asset=asset)
            )
            
            tx_envelope = tx_builder.build()
            tx_envelope.sign(source_kp)
            xdr = tx_envelope.to_xdr()
            tx_hash = tx_envelope.hash().hex()
            
            # Add Transaction
            tx = {
                "id": tx_hash,
                "paging_token": paging_token,
                "successful": True,
                "hash": tx_hash,
                "ledger": 12345,
                "created_at": "2024-01-01T00:00:00Z",
                "source_account": from_account,
                "source_account_sequence": "12345",
                "fee_account": from_account,
                "fee_charged": "100",
                "max_fee": "100",
                "operation_count": 1,
                "envelope_xdr": xdr,
                "result_xdr": "AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAA=", # Success tx result XDR (simple)
                "result_meta_xdr": "AAAAAA==", # Empty meta
                "fee_meta_xdr": "AAAAAA==", # Empty fee meta
                "memo_type": "none"
            }
            self.transactions.append(tx)
            self.transactions.sort(key=lambda x: x["paging_token"])

            payment = {
                "id": paging_token,
                "paging_token": paging_token,
                "transaction_successful": True,
                "source_account": from_account,
                "type": "payment",
                "type_i": 1,
                "created_at": "2024-01-01T00:00:00Z",
                "transaction_hash": tx_hash,
                "asset_type": asset_type,
                "from": from_account,
                "to": to_account,
                "amount": amount
            }
            if asset_code:
                payment["asset_code"] = asset_code
                payment["asset_issuer"] = asset_issuer
                
            self.payments.append(payment)
            # Sort by paging_token to be safe
            self.payments.sort(key=lambda x: x["paging_token"])

        def set_account(self, account_id: str, balances: Optional[list] = None, sequence: str = "123456789",
                       signers: Optional[list] = None, data: Optional[dict] = None):
            """Configure account response."""
            self.not_found_accounts.discard(account_id)
            self.accounts[account_id] = {
                "id": account_id,
                "account_id": account_id,
                "sequence": sequence,
                "balances": balances or [
                    {"asset_type": "native", "balance": "100.0000000"}
                ],
                "signers": signers or [
                    {"key": account_id, "weight": 1, "type": "ed25519_public_key"}
                ],
                "thresholds": {"low_threshold": 0, "med_threshold": 0, "high_threshold": 0},
                "data": data or {},
                "flags": {"auth_required": False, "auth_revocable": False, "auth_immutable": False},
                "paging_token": account_id
            }

        def set_not_found(self, account_id: str):
            """Force account to return 404."""
            self.not_found_accounts.add(account_id)
            self.accounts.pop(account_id, None)

        def set_offers(self, account_id: str, offers: list):
            """Configure offers response for account."""
            self.offers[account_id] = offers

        def set_paths(self, paths: list):
            """Configure paths response for strict-send/receive."""
            self.paths = paths

        def set_transaction_response(self, successful: bool = True, hash: str = "abc123",
                                     error: Optional[str] = None):
            """Configure transaction submit response."""
            self.transaction_response = {
                "successful": successful,
                "hash": hash,
                "ledger": 12345,
                "envelope_xdr": "AAAA...",
                "result_xdr": "AAAA...",
            }
            if error:
                self.transaction_response["extras"] = {"result_codes": {"transaction": error}}

        def get_requests(self, endpoint: Optional[str] = None):
            """Get received requests, optionally filtered by endpoint."""
            if endpoint:
                return [r for r in self.requests if r["endpoint"] == endpoint]
            return self.requests

        def clear(self):
            """Clear all state."""
            self.requests.clear()
            self.accounts.clear()
            self.not_found_accounts.clear()
            self.offers.clear()
            self.paths.clear()

    state = HorizonMockState()

    # Set up default test account
    state.set_account(DEFAULT_TEST_ACCOUNT, balances=[
        {"asset_type": "native", "balance": "100.0000000"},
        {"asset_type": "credit_alphanum12", "asset_code": "EURMTL",
         "asset_issuer": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
         "balance": "1000.0000000"}
    ])

    @routes.get("/accounts/{account_id}")
    async def get_account(request):
        account_id = request.match_info['account_id']
        state.requests.append({
            "endpoint": "accounts",
            "method": "GET",
            "account_id": account_id,
            "params": dict(request.query)
        })

        if account_id in state.not_found_accounts:
            return web.json_response({"status": 404, "title": "Resource Missing", "detail": "Account not found"}, status=404)

        if account_id in state.accounts:
            return web.json_response(state.accounts[account_id])

        # Default: Return a funded account structure for any address (compatibility)
        return web.json_response({
            "id": account_id,
            "account_id": account_id,
            "sequence": "123456789",
            "balances": [{"asset_type": "native", "balance": "100.0000000"}],
            "signers": [{"key": account_id, "weight": 1, "type": "ed25519_public_key"}],
            "thresholds": {"low_threshold": 0, "med_threshold": 0, "high_threshold": 0},
            "data": {},
            "flags": {"auth_required": False, "auth_revocable": False, "auth_immutable": False},
            "paging_token": account_id
        })

    @routes.get("/accounts/{account_id}/offers")
    async def get_account_offers(request):
        account_id = request.match_info['account_id']
        state.requests.append({
            "endpoint": "offers",
            "method": "GET",
            "account_id": account_id,
            "params": dict(request.query)
        })

        offers = state.offers.get(account_id, [])
        return web.json_response({
            "_embedded": {
                "records": offers
            }
        })

    @routes.get("/offers")
    async def get_offers(request):
        """General offers endpoint with query params."""
        params = dict(request.query)
        state.requests.append({
            "endpoint": "offers",
            "method": "GET",
            "params": params
        })

        seller = params.get("seller")
        offers = state.offers.get(seller, []) if seller else []
        return web.json_response({
            "_embedded": {
                "records": offers
            }
        })

    @routes.get("/paths/strict-send")
    async def get_strict_send_paths(request):
        """Mock strict-send paths endpoint."""
        params = dict(request.query)
        state.requests.append({
            "endpoint": "paths/strict-send",
            "method": "GET",
            "params": params
        })
        return web.json_response({
            "_embedded": {
                "records": state.paths
            }
        })
        
    @routes.get("/ledgers")
    async def get_ledgers(request):
        """Mock ledgers endpoint."""
        params = dict(request.query)
        state.requests.append({
            "endpoint": "ledgers",
            "method": "GET",
            "params": params
        })
        # Return a simple ledger list to satisfy basic polling
        return web.json_response({
            "_embedded": {
                "records": [
                    {
                        "id": "123456789",
                        "sequence": 12345,
                        "hash": "hash123",
                        "paging_token": "12345",
                        "closed_at": "2024-01-01T00:00:00Z"
                    }
                ]
            }
        })

    @routes.get("/ledgers/{sequence}")
    async def get_ledger_by_seq(request):
        """Mock single ledger endpoint."""
        seq = request.match_info['sequence']
        return web.json_response({
             "id": seq,
             "sequence": int(seq) if seq.isdigit() else 1,
             "hash": "hash123",
             "paging_token": seq
        })

    @routes.get("/operations")
    async def get_operations(request):
        """Mock operations endpoint."""
        params = dict(request.query)
        state.requests.append({
            "endpoint": "operations",
            "method": "GET",
            "params": params
        })
        # Use simple static logic or return configured list
        # For integration test, we might want to return nothing first, then something.
        # But simple version: return empty list unless cursor suggests otherwise?
        # Let's return empty by default, allowing test to inject via state (if we added state.set_operations support)
        # But state.operations is not defined yet.
        return web.json_response({
            "_embedded": {
                "records": state.operations
            }
        })
    # Removed garbage code block

    @routes.get("/paths/strict-receive")
    async def get_strict_receive_paths(request):
        """Mock strict-receive paths endpoint."""
        params = dict(request.query)
        state.requests.append({
            "endpoint": "paths/strict-receive",
            "method": "GET",
            "params": params
        })
        
        return web.json_response({
            "_embedded": {
                "records": state.paths
            }
        })

    @routes.post("/transactions")
    async def submit_transaction(request):
        if request.content_type == 'application/json':
            data = await request.json()
        else:
            data = await request.post()

        state.requests.append({
            "endpoint": "transactions",
            "method": "POST",
            "data": dict(data)
        })

        if state.transaction_response.get("successful", True):
            return web.json_response(state.transaction_response)
        else:
            return web.json_response(state.transaction_response, status=400)

    @routes.get("/transactions")
    async def get_transactions(request):
        """Mock transactions endpoint with cursor support."""
        params = dict(request.query)
        state.requests.append({
            "endpoint": "transactions",
            "method": "GET",
            "params": params
        })
        
        cursor = params.get("cursor", "0")
        if cursor == "now":
            cursor = "0"
            
        limit = int(params.get("limit", 10))
        
        # Filter transactions > cursor
        filtered = [tx for tx in state.transactions if tx["paging_token"] > cursor]
        records = filtered[:limit]
        
        if "text/event-stream" in request.headers.get("Accept", ""):
            import json
            response = web.StreamResponse(status=200, reason='OK', headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            })
            await response.prepare(request)
            await response.write(b'event: open\ndata: "hello"\n\n')

            for record in records:
                data = json.dumps(record)
                await response.write(f'data: {data}\n\n'.encode('utf-8'))
            
            return response

        return web.json_response({
            "_embedded": {
                "records": records
            }
        })
    
    @routes.get("/payments")
    async def get_payments(request):
        """Mock payments endpoint with cursor support."""
        params = dict(request.query)
        state.requests.append({
            "endpoint": "payments",
            "method": "GET",
            "params": params
        })
        
        cursor = params.get("cursor", "0")
        if cursor == "now":
            cursor = "0"
            
        limit = int(params.get("limit", 10))
        
        # Filter payments > cursor
        filtered = [p for p in state.payments if p["paging_token"] > cursor]
        # Apply limit
        records = filtered[:limit]
        
        if "text/event-stream" in request.headers.get("Accept", ""):
            response = web.StreamResponse(status=200, reason='OK', headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            })
            await response.prepare(request)
            await response.write(b'event: open\ndata: "hello"\n\n')

            for record in records:
                data = json.dumps(record)
                await response.write(f'data: {data}\n\n'.encode('utf-8'))
            
            return response

        return web.json_response({
            "_embedded": {
                "records": records
            }
        })

    @routes.get("/paths/strict-send")
    async def strict_send_paths(request):
        params = dict(request.query)
        state.requests.append({
            "endpoint": "paths/strict-send",
            "method": "GET",
            "params": params
        })

        # Return configured paths or empty
        if state.paths:
            return web.json_response({
                "_embedded": {
                    "records": state.paths
                }
            })

        # Default: return a simple path
        return web.json_response({
            "_embedded": {
                "records": [{
                    "source_asset_type": params.get("source_asset_type", "native"),
                    "source_asset_code": params.get("source_asset_code"),
                    "source_asset_issuer": params.get("source_asset_issuer"),
                    "source_amount": params.get("source_amount", "10.0000000"),
                    "destination_asset_type": "credit_alphanum12",
                    "destination_asset_code": "EURMTL",
                    "destination_asset_issuer": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
                    "destination_amount": "9.5000000",
                    "path": []
                }]
            }
        })

    @routes.get("/paths/strict-receive")
    async def strict_receive_paths(request):
        params = dict(request.query)
        state.requests.append({
            "endpoint": "paths/strict-receive",
            "method": "GET",
            "params": params
        })

        if state.paths:
            return web.json_response({
                "_embedded": {
                    "records": state.paths
                }
            })

        return web.json_response({
            "_embedded": {
                "records": [{
                    "source_asset_type": "native",
                    "source_amount": "10.5000000",
                    "destination_asset_type": params.get("destination_asset_type", "credit_alphanum12"),
                    "destination_asset_code": params.get("destination_asset_code"),
                    "destination_asset_issuer": params.get("destination_asset_issuer"),
                    "destination_amount": params.get("destination_amount", "10.0000000"),
                    "path": []
                }]
            }
        })

    @routes.get("/fee_stats")
    async def fee_stats(request):
        state.requests.append({
            "endpoint": "fee_stats",
            "method": "GET"
        })
        return web.json_response({
            "last_ledger": "12345",
            "last_ledger_base_fee": "100",
            "ledger_capacity_usage": "0.5",
            "fee_charged": {
                "max": "200",
                "min": "100",
                "mode": "100",
                "p10": "100",
                "p20": "100",
                "p30": "100",
                "p40": "100",
                "p50": "100",
                "p60": "100",
                "p70": "100",
                "p80": "100",
                "p90": "100",
                "p95": "100",
                "p99": "100"
            },
            "max_fee": {
                "max": "10000",
                "min": "100",
                "mode": "100",
                "p10": "100",
                "p20": "100",
                "p30": "100",
                "p40": "100",
                "p50": "100",
                "p60": "100",
                "p70": "100",
                "p80": "100",
                "p90": "100",
                "p95": "100",
                "p99": "1000"
            }
        })

    @routes.get("/")
    async def root(request):
        """Root endpoint - Horizon info."""
        state.requests.append({"endpoint": "root", "method": "GET"})
        return web.json_response({
            "horizon_version": "mock-2.0.0",
            "core_version": "mock-v19.0.0",
            "network_passphrase": "Test SDF Network ; September 2015"
        })

    # Catch-all for debugging unhandled endpoints
    @routes.get("/{path:.*}")
    async def catch_all_get(request):
        path = request.match_info['path']
        print(f"[MockHorizon] Unhandled GET: /{path}")
        state.requests.append({
            "endpoint": f"UNHANDLED:{path}",
            "method": "GET",
            "params": dict(request.query)
        })
        return web.json_response({"error": f"Mock endpoint not implemented: GET /{path}"}, status=404)

    @routes.post("/{path:.*}")
    async def catch_all_post(request):
        path = request.match_info['path']
        print(f"[MockHorizon] Unhandled POST: /{path}")
        state.requests.append({
            "endpoint": f"UNHANDLED:{path}",
            "method": "POST"
        })
        return web.json_response({"error": f"Mock endpoint not implemented: POST /{path}"}, status=404)

    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, horizon_server_config["host"], horizon_server_config["port"])
    await site.start()

    print(f"[MockHorizon] Started on {horizon_server_config['url']}")

    yield state

    await runner.cleanup()
    print("[MockHorizon] Stopped")


import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import sys
import os
sys.path.append(os.getcwd())
from aiohttp import web
from aiogram import Dispatcher

# Constants for Mock Server
MOCK_SERVER_PORT = 8081
MOCK_SERVER_HOST = "localhost"
MOCK_SERVER_URL = f"http://{MOCK_SERVER_HOST}:{MOCK_SERVER_PORT}"
TEST_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

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
    ctx.localization_service = MagicMock()
    ctx.localization_service.get_text.return_value = "text"
    ctx.stellar_service = AsyncMock()
    ctx.repository_factory = MagicMock()
    ctx.bot = AsyncMock()
    ctx.admin_id = 123456
    return ctx


@pytest.fixture
async def mock_server():
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
            except:
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
    site = web.TCPSite(runner, MOCK_SERVER_HOST, MOCK_SERVER_PORT)
    await site.start()

    yield received_requests


    await runner.cleanup()


# --- Common Fixtures ---

@pytest.fixture
def mock_session():
    session = AsyncMock()
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
    state = AsyncMock()
    state.get_data.return_value = {}
    return state

@pytest.fixture
def mock_callback():
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.from_user.username = "user"
    callback.message = AsyncMock()
    callback.message.chat.id = 123
    return callback

@pytest.fixture
def mock_message():
    message = AsyncMock()
    message.from_user.id = 123
    message.chat.id = 123
    message.text = "test_text"
    return message

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
    p3 = patch("other.lang_tools.my_gettext", return_value="text")
    p2 = patch("infrastructure.utils.common_utils.get_user_id", return_value=123)
    
    p3.start()
    p2.start()
    
    yield gd
    
    p3.stop()
    p2.stop()

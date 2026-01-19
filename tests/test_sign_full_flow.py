import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from aiogram import types, Dispatcher, F
from aiogram.methods import SendMessage, EditMessageText
from aiogram.types import Update, Message, CallbackQuery, User, Chat
from aiogram.fsm.storage.base import StorageKey
from routers.sign import router, PinState, PinCallbackData
from infrastructure.services.app_context import AppContext
from infrastructure.states import StateSign
from other.mytypes import MyResponse

# Re-use fixtures from conftest.py implicitly (mock_server, mock_global_data_autouse)

@pytest.fixture
def dp_with_router(dp: Dispatcher, mock_app_context):
    """
    Setup dispatcher with just the router under test to isolate it.
    inject mock_app_context into workflow data.
    """
    # Hack to reset router parent if tests are running in same process and reusing global router object
    if router.parent_router:
        router._parent_router = None
        
    dp.include_router(router)
    
    # Simple middleware to inject app_context
    @dp.update.outer_middleware
    async def inject_app_context(handler, event, data):
        data['app_context'] = mock_app_context
        return await handler(event, data)
        
    return dp

@pytest.mark.asyncio
async def test_full_flow_sign_pin_success(mock_server, dp_with_router, mock_app_context, mock_session):
    """
    Scenario: User signs and sends an XDR using PIN flow via REAL dispatcher.
    """
    user_id = 456
    chat_id = 456
    
    # 0. Setup dependencies
    mock_app_context.stellar_service.is_free_wallet.return_value = False
    mock_app_context.stellar_service.check_xdr.return_value = "AAAAXDR..."
    mock_app_context.stellar_service.get_user_account.return_value = MagicMock(account=MagicMock(account_id="GAB..."))
    # Mock verify logic: fail unless pin is 1234
    mock_app_context.stellar_service.get_user_keypair.side_effect = lambda s, u, p: "KEYPAIR" if p == "1234" else (_ for _ in ()).throw(Exception("Bad Pin"))
    mock_app_context.stellar_service.user_sign.return_value = "SIGNED_XDR"
    
    # Mock bot instance in app_context to match the test bot (token is in conftest)
    # mock_server uses '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'
    # we need to make sure the dp uses a bot that points to localhost mock server.
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.client.telegram import TelegramAPIServer
    from aiogram import Bot
    
    session = AiohttpSession(api=TelegramAPIServer.from_base("http://localhost:8081"))
    bot = Bot(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11", session=session)
    mock_app_context.bot = bot
    mock_app_context.dispatcher = dp_with_router
    
    # We need to patch database session injection if it's done via middleware too.
    # Conftest has mock_global_data_autouse but usually DbSessionMiddleware handles it.
    # Let's inject mock_session via the same simple middleware we added in fixture?
    # Or just rely on the fact that handlers take `session: Session`.
    # Update our injection middleware:
    
    @dp_with_router.update.outer_middleware
    async def inject_dependencies(handler, event, data):
        data['app_context'] = mock_app_context
        data['session'] = mock_session # Inject mock db session
        return await handler(event, data)


    # 1. Trigger cmd_sign (Callback "Sign")
    # We simulate a callback query update
    user = User(id=user_id, is_bot=False, first_name="Test", username="test")
    chat = Chat(id=chat_id, type="private")
    
    callback = CallbackQuery(
        id="1", 
        from_user=user, 
        chat_instance="1", 
        data="Sign",
        message=Message(message_id=1, date=123, chat=chat, from_user=User(id=999, is_bot=True, first_name="Bot"))
    )
    
    # Start the bot interaction
    await dp_with_router.feed_update(bot, Update(update_id=1, callback_query=callback))
    
    # Verify state transition 
    # We need to access FSM storage. dp matches user_id/chat_id key.
    # StorageKey imported via global
    state_key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id)
    state = await dp_with_router.storage.get_state(state_key)
    assert state == StateSign.sending_xdr
    
    # 2. User sends XDR text
    
    # Set pin type in FSM data manually to skip db lookup logic if we can, or let it run?
    # Helper to update data
    await dp_with_router.storage.update_data(state_key, {'pin_type': 1, 'user_lang': 'en'})
    
    message_update = Update(
        update_id=2, 
        message=Message(
            message_id=2, 
            date=123, 
            chat=chat, 
            from_user=user, 
            text="AAAAXDR..."
        )
    )
    
    await dp_with_router.feed_update(bot, message_update)
    
    state = await dp_with_router.storage.get_state(state_key)
    # Should move to PinState.sign or similar
    assert state == PinState.sign
    
    # 3. Enter PIN "1"
    await dp_with_router.feed_update(bot, Update(update_id=3, callback_query=CallbackQuery(
        id="2", from_user=user, chat_instance="1", data=PinCallbackData(action="1").pack(),
        message=Message(message_id=3, date=123, chat=chat, from_user=User(id=999, is_bot=True, first_name="Bot"))
    )))
    
    data = await dp_with_router.storage.get_data(state_key)
    assert data.get('pin') == "1"
    
    # Enter PIN "2"
    await dp_with_router.feed_update(bot, Update(update_id=4, callback_query=CallbackQuery(
        id="3", from_user=user, chat_instance="1", data=PinCallbackData(action="2").pack(),
        message=Message(message_id=3, date=123, chat=chat, from_user=User(id=999, is_bot=True, first_name="Bot"))
    )))
    
    data = await dp_with_router.storage.get_data(state_key)
    assert data.get('pin') == "12"
    
    
     # Mock verify and sign success
    # Side effect already set at start
    
    # Enter PIN "3"
    await dp_with_router.feed_update(bot, Update(update_id=5, callback_query=CallbackQuery(
        id="4", from_user=user, chat_instance="1", data=PinCallbackData(action="3").pack(),
        message=Message(message_id=3, date=123, chat=chat, from_user=User(id=999, is_bot=True, first_name="Bot"))
    )))
    
    # Enter PIN "4" (triggers check)
    # We expect `user_sign` to be called here
    await dp_with_router.feed_update(bot, Update(update_id=6, callback_query=CallbackQuery(
        id="5", from_user=user, chat_instance="1", data=PinCallbackData(action="4").pack(),
        message=Message(message_id=3, date=123, chat=chat, from_user=User(id=999, is_bot=True, first_name="Bot"))
    )))
    
    mock_app_context.stellar_service.user_sign.assert_called_with(ANY, "AAAAXDR...", user_id, "1234")
    
    
    # 4. "SendTr"
    mock_app_context.stellar_service.send_xdr_async.return_value = {"hash": "txhash", "paging_token": "123"}
    # The XDR should be in state now as 'xdr' (signed) hopefully?
    # Logic: sign_xdr -> updates 'xdr' in state with signed version?
    # Need to check `sign_xdr` logic. It updates `xdr` in data if signing success?
    # Looking at `routers/sign.py`:
    # xdr = await app_context.stellar_service.user_sign(...)
    # await state.update_data(xdr=xdr)
    # YES.
    
    await dp_with_router.feed_update(bot, Update(update_id=7, callback_query=CallbackQuery(
        id="6", from_user=user, chat_instance="1", data="SendTr",
        message=Message(message_id=3, date=123, chat=chat, from_user=User(id=999, is_bot=True, first_name="Bot"))
    )))
    
    mock_app_context.stellar_service.send_xdr_async.assert_called_with("SIGNED_XDR")
    
    # Assert outgoing requests describe success
    # mock_session (the db one) or mock_server (the http one)?
    # mock_server fixture yields `received_requests` list.
    # We can inspect it to see if `sendMessage` was called with success text.
    # Note: send_message utility might use editMessageText if last_message_id is set.
    messages = [r for r in mock_server if r['method'] in ('sendMessage', 'editMessageText')]
    # There should be several messages (Ask XDR, Ask Pin, Signed Info, Success Info)
    assert len(messages) >= 3

@pytest.mark.asyncio
async def test_full_flow_mistake_pin_mock(mock_server, dp_with_router, mock_app_context, mock_session):
    user_id = 987
    chat_id = 987
    
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.client.telegram import TelegramAPIServer
    from aiogram import Bot
    
    session = AiohttpSession(api=TelegramAPIServer.from_base("http://localhost:8081"))
    bot = Bot(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11", session=session)
    mock_app_context.bot = bot
    mock_app_context.dispatcher = dp_with_router
    
    @dp_with_router.update.outer_middleware
    async def inject_dependencies(handler, event, data):
        data['app_context'] = mock_app_context
        data['session'] = mock_session
        return await handler(event, data)
        
    user = User(id=user_id, is_bot=False, first_name="Test", username="test")
    chat = Chat(id=chat_id, type="private")
    state_key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id)
    
    # Pre-set state to sending XDR
    await dp_with_router.storage.set_state(state_key, StateSign.sending_xdr)
    await dp_with_router.storage.update_data(state_key, {'pin_type': 1, 'user_lang': 'en'})
    
    mock_app_context.stellar_service.check_xdr.return_value = "AAAAXDR..."
    mock_app_context.stellar_service.get_user_account.return_value = MagicMock(account=MagicMock(account_id="GAB..."))
    # Fail all PIN attempts in this mistake test so we accumulate digits
    mock_app_context.stellar_service.get_user_keypair.side_effect = Exception("Bad Pin")

    # Send XDR
    await dp_with_router.feed_update(bot, Update(update_id=1, message=Message(
        message_id=1, date=123, chat=chat, from_user=user, text="XDR_CONTENT"
    )))
    
    # 1 -> 2 -> Del -> 3
    for i, d in enumerate(["1", "2", "Del", "3"]):
        await dp_with_router.feed_update(bot, Update(update_id=2+i, callback_query=CallbackQuery(
            id=f"cb{i}", from_user=user, chat_instance="1", data=PinCallbackData(action=d).pack(),
            message=Message(message_id=2, date=123, chat=chat, from_user=User(id=999, is_bot=True, first_name="Bot"))
        )))
        
    data = await dp_with_router.storage.get_data(state_key)
    assert data.get('pin') == "13"

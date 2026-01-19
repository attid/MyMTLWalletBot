
import pytest
import jsonpickle
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import AsyncMock, MagicMock
import datetime

from routers.bsn import bsn_router, BSNStates, SEND_CALLBACK_DATA, BACK_CALLBACK_DATA, BSNData, BSNRow, Tag, Value, Key, Address
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from aiogram.dispatcher.middlewares.base import BaseMiddleware


class MockDbMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Create AsyncMock session that can handle execute calls
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.all.return_value = []
        session.execute.return_value = result
        data["session"] = session
        return await handler(event, data)


@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if bsn_router.parent_router:
         bsn_router._parent_router = None


@pytest.mark.asyncio
async def test_bsn_mode_command(mock_server, dp):
    """
    Test /bsn command: should fetch BSN data from Stellar and show edit menu.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(bsn_router)

    # Mock wallet and BSN data
    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    mock_wallet_repo = MagicMock()
    mock_wallet = MagicMock()
    mock_wallet.public_key = test_address
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)

    # Mock stellar_service.get_account_details
    mock_stellar_service = MagicMock()
    mock_stellar_service.get_account_details = AsyncMock(return_value={
        'data': {
            'Name': 'VGVzdFVzZXI=',  # base64 encoded
            'About': 'VGVzdCBkZXNjcmlwdGlvbg==',
        }
    })

    update = types.Update(
        update_id=1,
        message=types.Message(
            message_id=1,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="/bsn"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    app_context.stellar_service = mock_stellar_service
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    # Verify sendMessage was called
    req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
    assert req is not None, "sendMessage should be called"

    await bot.session.close()


@pytest.mark.asyncio
async def test_bsn_mode_command_with_args(mock_server, dp):
    """
    Test /bsn Name MyName command: should parse tag from args and add to BSN data.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(bsn_router)

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    mock_wallet_repo = MagicMock()
    mock_wallet = MagicMock()
    mock_wallet.public_key = test_address
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)

    mock_stellar_service = MagicMock()
    mock_stellar_service.get_account_details = AsyncMock(return_value={'data': {}})

    update = types.Update(
        update_id=2,
        message=types.Message(
            message_id=2,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="/bsn Name Alice"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    app_context.stellar_service = mock_stellar_service
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    # Verify sendMessage was called
    req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
    assert req is not None, "sendMessage should be called"

    await bot.session.close()


@pytest.mark.asyncio
async def test_process_tags_add_new_tag(mock_server, dp):
    """
    Test adding a new tag in BSN editing mode.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(bsn_router)

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    initial_bsn_data = BSNData(
        address=Address(test_address),
        data=[]
    )

    # Set state with BSN data
    from aiogram.fsm.storage.memory import MemoryStorage
    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(BSNStates.waiting_for_tags)
    await ctx.update_data(tags=jsonpickle.dumps(initial_bsn_data))

    update = types.Update(
        update_id=3,
        message=types.Message(
            message_id=3,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="Website https://example.com"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.repository_factory = MagicMock()
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    # Verify sendMessage was called
    req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
    assert req is not None, "sendMessage should be called"

    await bot.session.close()


@pytest.mark.asyncio
async def test_finish_send_bsn(mock_server, dp):
    """
    Test sending BSN data: should generate XDR and ask for PIN.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(bsn_router)

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    test_bsn_data = BSNData(
        address=Address(test_address),
        data=[BSNRow.from_str("Name", "NewUser")]
    )

    # Set state with BSN data
    from aiogram.fsm.storage.memory import MemoryStorage
    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(BSNStates.waiting_for_tags)
    await ctx.update_data(tags=jsonpickle.dumps(test_bsn_data))

    # Mock stellar_service.build_manage_data_transaction
    mock_stellar_service = MagicMock()
    mock_stellar_service.build_manage_data_transaction = AsyncMock(return_value="XDR_BASE64")
    mock_stellar_service.get_user_account = AsyncMock(return_value=MagicMock(account=MagicMock(account_id=test_address)))

    # Mock repository for cmd_ask_pin
    mock_wallet_repo = MagicMock()
    mock_wallet = MagicMock()
    mock_wallet.public_key = test_address
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)

    update = types.Update(
        update_id=4,
        callback_query=types.CallbackQuery(
            id="cb1",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=1,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data=SEND_CALLBACK_DATA
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.stellar_service = mock_stellar_service
    app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    # Verify XDR was generated and stored in state
    state_data = await ctx.get_data()
    assert state_data.get('xdr') == "XDR_BASE64", "XDR should be stored in state"

    # Verify answerCallbackQuery was called
    req = next((r for r in mock_server if r["method"] == "answerCallbackQuery"), None)
    assert req is not None, "answerCallbackQuery should be called"

    await bot.session.close()


@pytest.mark.asyncio
async def test_finish_back_bsn(mock_server, dp):
    """
    Test back button: should clear BSN state and return to balance.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(bsn_router)

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Set state with BSN data
    from aiogram.fsm.storage.memory import MemoryStorage
    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(BSNStates.waiting_for_tags)
    await ctx.update_data(tags=jsonpickle.dumps({}))

    # Mock stellar_service for cmd_show_balance
    mock_stellar_service = MagicMock()
    mock_stellar_service.get_user_account = AsyncMock(return_value=MagicMock(account=MagicMock(account_id=test_address)))

    # Mock repository for cmd_show_balance
    mock_user_repo = MagicMock()
    mock_user = MagicMock()
    mock_user.lang = 'en'
    mock_user.can_5000 = 1
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)

    mock_wallet_repo = MagicMock()
    mock_wallet = MagicMock()
    mock_wallet.public_key = test_address
    mock_wallet.is_free = False
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)

    update = types.Update(
        update_id=5,
        callback_query=types.CallbackQuery(
            id="cb2",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=1,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data=BACK_CALLBACK_DATA
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    app_context.stellar_service = mock_stellar_service
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    # Verify state was cleared
    state = await ctx.get_state()
    assert state is None, "State should be cleared"

    # Verify answerCallbackQuery was called
    req = next((r for r in mock_server if r["method"] == "answerCallbackQuery"), None)
    assert req is not None, "answerCallbackQuery should be called"

    await bot.session.close()


# --- Unit tests for BSN data classes and helpers ---

@pytest.mark.asyncio
async def test_bsn_tag_parsing():
    """Test Tag.parse() with various inputs."""
    # Simple tag
    tag = Tag.parse("Name")
    assert tag.key == "Name"
    assert tag.num is None

    # Tag with number
    tag = Tag.parse("Name2")
    assert tag.key == "Name"
    assert tag.num == 2

    # Unknown tag
    tag = Tag.parse("UnknownTag")
    assert tag.key == "UnknownTag"
    assert tag.num is None


@pytest.mark.asyncio
async def test_bsn_data_operations():
    """Test BSNData add/remove/change operations."""
    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    bsn_data = BSNData(
        address=Address(test_address),
        data=[BSNRow.from_str("Name", "Original")]
    )

    # Initially empty (no modifications)
    assert bsn_data.is_empty(), "Initial data should have no modifications"

    # Add new tag
    bsn_data.add_new_data_row(Key("About"), Value("Test"))
    assert not bsn_data.is_empty(), "Should have modifications after adding"
    assert len(bsn_data.changed_items()) == 1

    # Add same tag key again - creates About2
    bsn_data.add_new_data_row(Key("About"), Value("Updated"))
    changed = bsn_data.changed_items()
    assert len(changed) == 2  # About and About2

    # Delete specific tag (About1, not About2)
    bsn_data.del_data_row(Key("About1"))
    changed = bsn_data.changed_items()
    assert len(changed) == 2  # Both About1 (removed) and About2 (added)
    assert any(r.is_remove() for r in changed), "Should have a removed item"

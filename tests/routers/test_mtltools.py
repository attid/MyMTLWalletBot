
import pytest
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import AsyncMock, MagicMock
import datetime

from routers.mtltools import (
    router as mtltools_router,
    StateTools,
    DonateCallbackData,
    BIMCallbackData,
)
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from aiogram.dispatcher.middlewares.base import BaseMiddleware


class MockDbMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
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
    if mtltools_router.parent_router:
         mtltools_router._parent_router = None


# --- MTL Tools main menu ---

@pytest.mark.asyncio
async def test_cmd_tools(mock_server, dp):
    """
    Test MTLTools callback: should show main tools menu.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    update = types.Update(
        update_id=1,
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
            data="MTLTools"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
    assert req is not None, "sendMessage should be called"

    req_answer = next((r for r in mock_server if r["method"] == "answerCallbackQuery"), None)
    assert req_answer is not None, "answerCallbackQuery should be called"

    await bot.session.close()


# --- Delegate handlers ---

@pytest.mark.asyncio
async def test_cmd_tools_delegate(mock_server, dp):
    """
    Test MTLToolsDelegate callback: should show delegate management menu.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    update = types.Update(
        update_id=2,
        callback_query=types.CallbackQuery(
            id="cb2",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=2,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="MTLToolsDelegate"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    import other.stellar_tools as stellar_tools_module

    original_get_data = stellar_tools_module.stellar_get_data
    original_get_user = stellar_tools_module.stellar_get_user_account
    original_router_get_data = mtltools_module.stellar_get_data

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = test_address

    stellar_tools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    stellar_tools_module.stellar_get_data = AsyncMock(return_value={'mtl_delegate': test_address})
    mtltools_module.stellar_get_data = AsyncMock(return_value={'mtl_delegate': test_address})

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        stellar_tools_module.stellar_get_data = original_get_data
        stellar_tools_module.stellar_get_user_account = original_get_user
        mtltools_module.stellar_get_data = original_router_get_data

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_tools_del_delegate(mock_server, dp):
    """
    Test MTLToolsDelDelegate callback: should generate XDR to delete delegate.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_user_address = "GUSER1234567890TESTACCOUNT"

    update = types.Update(
        update_id=3,
        callback_query=types.CallbackQuery(
            id="cb3",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=3,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="MTLToolsDelDelegate"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    import other.stellar_tools as stellar_tools_module

    original_get_data = stellar_tools_module.stellar_get_data
    original_get_user = stellar_tools_module.stellar_get_user_account
    original_router_get_data = mtltools_module.stellar_get_data
    original_router_get_user = mtltools_module.stellar_get_user_account
    original_gen_xdr = mtltools_module.cmd_gen_data_xdr

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = test_user_address

    stellar_tools_module.stellar_get_data = AsyncMock(return_value={'mtl_delegate': 'GDELEGATE'})
    stellar_tools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    mtltools_module.stellar_get_data = AsyncMock(return_value={'mtl_delegate': 'GDELEGATE'})
    mtltools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    mtltools_module.cmd_gen_data_xdr = AsyncMock(return_value="XDR")

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        stellar_tools_module.stellar_get_data = original_get_data
        stellar_tools_module.stellar_get_user_account = original_get_user
        mtltools_module.stellar_get_data = original_router_get_data
        mtltools_module.stellar_get_user_account = original_router_get_user
        mtltools_module.cmd_gen_data_xdr = original_gen_xdr

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_tools_add_delegate_low_xlm(mock_server, dp):
    """
    Test AddDelegate callback with low XLM: should show alert.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    update = types.Update(
        update_id=4,
        callback_query=types.CallbackQuery(
            id="cb4",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=4,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="MTLToolsAddDelegate"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    import other.stellar_tools as stellar_tools_module

    original_have_xlm = stellar_tools_module.have_free_xlm

    stellar_tools_module.have_free_xlm = AsyncMock(return_value=False)

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

    finally:
        stellar_tools_module.have_free_xlm = original_have_xlm

    req = next((r for r in mock_server if r["method"] == "answerCallbackQuery"), None)
    assert req is not None, "answerCallbackQuery should be called"
    assert req["data"].get("show_alert") == "true", "Should show alert for low XLM"

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_send_add_delegate_for(mock_server, dp):
    """
    Test sending delegate address: should generate XDR for confirmation.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    test_user_address = "GUSER1234567890TESTACCOUNT"

    from aiogram.fsm.storage.memory import MemoryStorage
    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(StateTools.delegate_for)

    mock_stellar_service = MagicMock()
    mock_stellar_service.get_account_details = AsyncMock(return_value={'data': {}})

    mock_account = MagicMock()
    mock_account.account.account.account_id = test_address

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = test_user_address

    update = types.Update(
        update_id=5,
        message=types.Message(
            message_id=5,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text=test_address
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.stellar_service = mock_stellar_service
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    original_check = mtltools_module.stellar_check_account
    original_get_user = mtltools_module.stellar_get_user_account
    original_gen_xdr = mtltools_module.cmd_gen_data_xdr

    # Correct AsyncMocks
    mtltools_module.stellar_check_account = AsyncMock(return_value=mock_account)
    mtltools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    mtltools_module.cmd_gen_data_xdr = AsyncMock(return_value="XDR")

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        mtltools_module.stellar_check_account = original_check
        mtltools_module.stellar_get_user_account = original_get_user
        mtltools_module.cmd_gen_data_xdr = original_gen_xdr

    await bot.session.close()


# --- Donate handlers ---

@pytest.mark.asyncio
async def test_cmd_tools_donate_with_existing(mock_server, dp):
    """
    Test MTLToolsDonate callback with existing donations.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    update = types.Update(
        update_id=6,
        callback_query=types.CallbackQuery(
            id="cb6",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=6,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="MTLToolsDonate"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    import other.stellar_tools as stellar_tools_module

    original_get_data = stellar_tools_module.stellar_get_data
    original_get_user = stellar_tools_module.stellar_get_user_account
    original_router_get_data = mtltools_module.stellar_get_data

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = "GDONATE1234567890TESTACCOUNT"

    stellar_tools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    stellar_tools_module.stellar_get_data = AsyncMock(
        return_value={'mtl_donate_charity=10': 'GDONATE123'}
    )
    mtltools_module.stellar_get_data = AsyncMock(
        return_value={'mtl_donate_charity=10': 'GDONATE123'}
    )

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        stellar_tools_module.stellar_get_data = original_get_data
        stellar_tools_module.stellar_get_user_account = original_get_user
        mtltools_module.stellar_get_data = original_router_get_data

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_tools_add_donate_low_xlm(mock_server, dp):
    """
    Test AddDonate callback with low XLM: should show alert.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    update = types.Update(
        update_id=7,
        callback_query=types.CallbackQuery(
            id="cb7",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=7,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="AddDonate"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    import other.stellar_tools as stellar_tools_module

    original_have_xlm = stellar_tools_module.have_free_xlm

    stellar_tools_module.have_free_xlm = AsyncMock(return_value=False)

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

    finally:
        stellar_tools_module.have_free_xlm = original_have_xlm

    req = next((r for r in mock_server if r["method"] == "answerCallbackQuery"), None)
    assert req is not None, "answerCallbackQuery should be called"
    assert req["data"].get("show_alert") == "true", "Should show alert for low XLM"

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_send_add_donate_address(mock_server, dp):
    """
    Test sending donate address: should ask for name.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(StateTools.donate_address)

    mock_account = MagicMock()
    mock_account.account.account.account_id = test_address

    update = types.Update(
        update_id=8,
        message=types.Message(
            message_id=8,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text=test_address
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    original_check = mtltools_module.stellar_check_account

    mtltools_module.stellar_check_account = AsyncMock(return_value=mock_account)

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        mtltools_module.stellar_check_account = original_check

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_send_add_donate_name(mock_server, dp):
    """
    Test sending donate name: should ask for percent.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(StateTools.donate_name)

    update = types.Update(
        update_id=9,
        message=types.Message(
            message_id=9,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="Charity"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
    assert req is not None, "sendMessage should be called"

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_send_add_donate_percent(mock_server, dp):
    """
    Test sending donate percent: should generate XDR for confirmation.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_address = "GDONATE1234567890TESTACCOUNT"

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(StateTools.donate_persent)
    await ctx.update_data(address=test_address, name="charity")

    test_user_address = "GUSER1234567890TESTACCOUNT"

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = test_user_address

    update = types.Update(
        update_id=10,
        message=types.Message(
            message_id=10,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="5.5"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    original_get_user = mtltools_module.stellar_get_user_account
    original_gen_xdr = mtltools_module.cmd_gen_data_xdr

    mtltools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    mtltools_module.cmd_gen_data_xdr = AsyncMock(return_value="XDR")

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        mtltools_module.stellar_get_user_account = original_get_user
        mtltools_module.cmd_gen_data_xdr = original_gen_xdr

    await bot.session.close()


@pytest.mark.asyncio
async def test_cq_donate_setting_show(mock_server, dp):
    """
    Test DonateCallbackData Show action: should show donate details.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.update_data(donates={'idx0': ['mtl_donate_charity=10', 'charity', '10', 'GDONATE']})

    callback_data = DonateCallbackData(action='Show', idx='idx0')

    update = types.Update(
        update_id=11,
        callback_query=types.CallbackQuery(
            id="cb11",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=11,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data=callback_data.pack()
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    req = next((r for r in mock_server if r["method"] == "answerCallbackQuery"), None)
    assert req is not None, "answerCallbackQuery should be called"
    assert req["data"].get("show_alert") == "true", "Should show alert with details"

    await bot.session.close()


@pytest.mark.asyncio
async def test_cq_donate_setting_delete(mock_server, dp):
    """
    Test DonateCallbackData Delete action: should generate XDR to delete donate.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_user_address = "GUSER1234567890TESTACCOUNT"

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.update_data(donates={'idx0': ['mtl_donate_charity=10', 'charity', '10', 'GDONATE']})

    callback_data = DonateCallbackData(action='Delete', idx='idx0')

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = test_user_address

    update = types.Update(
        update_id=12,
        callback_query=types.CallbackQuery(
            id="cb12",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=12,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data=callback_data.pack()
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    original_get_user = mtltools_module.stellar_get_user_account
    original_gen_xdr = mtltools_module.cmd_gen_data_xdr

    mtltools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    mtltools_module.cmd_gen_data_xdr = AsyncMock(return_value="XDR")

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        mtltools_module.stellar_get_user_account = original_get_user
        mtltools_module.cmd_gen_data_xdr = original_gen_xdr

    await bot.session.close()


# --- BIM handlers ---

@pytest.mark.asyncio
async def test_cmd_tools_bim(mock_server, dp):
    """
    Test MTLToolsAddBIM callback: should show BIM list.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    update = types.Update(
        update_id=13,
        callback_query=types.CallbackQuery(
            id="cb13",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=13,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="MTLToolsAddBIM"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    import other.stellar_tools as stellar_tools_module

    original_get_data = stellar_tools_module.stellar_get_data
    original_get_user = stellar_tools_module.stellar_get_user_account
    original_router_get_data = mtltools_module.stellar_get_data

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = "GBIM1234567890TESTACCOUNT"

    stellar_tools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    stellar_tools_module.stellar_get_data = AsyncMock(return_value={'bod_exchange': 'GBIM123'})
    mtltools_module.stellar_get_data = AsyncMock(return_value={'bod_exchange': 'GBIM123'})

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        stellar_tools_module.stellar_get_data = original_get_data
        stellar_tools_module.stellar_get_user_account = original_get_user
        mtltools_module.stellar_get_data = original_router_get_data

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_tools_add_bim_low_xlm(mock_server, dp):
    """
    Test AddBIM callback with low XLM: should show alert.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    update = types.Update(
        update_id=14,
        callback_query=types.CallbackQuery(
            id="cb14",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=14,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data="AddBIM"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    import other.stellar_tools as stellar_tools_module

    original_have_xlm = stellar_tools_module.have_free_xlm

    stellar_tools_module.have_free_xlm = AsyncMock(return_value=False)

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

    finally:
        stellar_tools_module.have_free_xlm = original_have_xlm

    req = next((r for r in mock_server if r["method"] == "answerCallbackQuery"), None)
    assert req is not None, "answerCallbackQuery should be called"
    assert req["data"].get("show_alert") == "true", "Should show alert for low XLM"

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_send_add_bim_address(mock_server, dp):
    """
    Test sending BIM address: should ask for name.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(StateTools.bim_address)

    mock_account = MagicMock()
    mock_account.account.account.account_id = test_address

    update = types.Update(
        update_id=15,
        message=types.Message(
            message_id=15,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text=test_address
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    original_check = mtltools_module.stellar_check_account

    mtltools_module.stellar_check_account = AsyncMock(return_value=mock_account)

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        mtltools_module.stellar_check_account = original_check

    await bot.session.close()


@pytest.mark.asyncio
async def test_cmd_send_add_bim_name(mock_server, dp):
    """
    Test sending BIM name: should generate XDR for confirmation.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.message.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_address = "GBIM1234567890TESTACCOUNT"

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.set_state(StateTools.bim_name)
    await ctx.update_data(address=test_address)

    test_user_address = "GUSER1234567890TESTACCOUNT"

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = test_user_address

    update = types.Update(
        update_id=16,
        message=types.Message(
            message_id=16,
            date=datetime.datetime.now(),
            chat=types.Chat(id=123, type='private'),
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            text="exchange"
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    original_get_user = mtltools_module.stellar_get_user_account
    original_gen_xdr = mtltools_module.cmd_gen_data_xdr

    mtltools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    mtltools_module.cmd_gen_data_xdr = AsyncMock(return_value="XDR")

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        mtltools_module.stellar_get_user_account = original_get_user
        mtltools_module.cmd_gen_data_xdr = original_gen_xdr

    await bot.session.close()


@pytest.mark.asyncio
async def test_cq_bim_setting_show(mock_server, dp):
    """
    Test BIMCallbackData Show action: should show BIM details.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.update_data(donates={'idx0': ['bod_exchange', 'exchange', 'GBIM']})

    callback_data = BIMCallbackData(action='Show', idx='idx0')

    update = types.Update(
        update_id=17,
        callback_query=types.CallbackQuery(
            id="cb17",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=17,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data=callback_data.pack()
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    await dp.feed_update(bot=bot, update=update, app_context=app_context)

    req = next((r for r in mock_server if r["method"] == "answerCallbackQuery"), None)
    assert req is not None, "answerCallbackQuery should be called"
    assert req["data"].get("show_alert") == "true", "Should show alert with details"

    await bot.session.close()


@pytest.mark.asyncio
async def test_cq_bim_setting_delete(mock_server, dp):
    """
    Test BIMCallbackData Delete action: should generate XDR to delete BIM.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(mtltools_router)

    test_user_address = "GUSER1234567890TESTACCOUNT"

    ctx = dp.fsm.get_context(bot=bot, chat_id=123, user_id=123)
    await ctx.update_data(donates={'idx0': ['bod_exchange', 'exchange', 'GBIM']})

    callback_data = BIMCallbackData(action='Delete', idx='idx0')

    mock_user_account = MagicMock()
    mock_user_account.account.account_id = test_user_address

    update = types.Update(
        update_id=18,
        callback_query=types.CallbackQuery(
            id="cb18",
            from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
            chat_instance="ci1",
            message=types.Message(
                message_id=18,
                date=datetime.datetime.now(),
                chat=types.Chat(id=123, type='private'),
                text="msg"
            ),
            data=callback_data.pack()
        )
    )

    app_context = MagicMock()
    app_context.bot = bot
    app_context.dispatcher = dp
    app_context.localization_service = MagicMock()
    app_context.localization_service.get_text.return_value = "text"

    import routers.mtltools as mtltools_module
    original_get_user = mtltools_module.stellar_get_user_account
    original_gen_xdr = mtltools_module.cmd_gen_data_xdr

    mtltools_module.stellar_get_user_account = AsyncMock(return_value=mock_user_account)
    mtltools_module.cmd_gen_data_xdr = AsyncMock(return_value="XDR")

    try:
        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        req = next((r for r in mock_server if r["method"] == "sendMessage"), None)
        assert req is not None, "sendMessage should be called"
    finally:
        mtltools_module.stellar_get_user_account = original_get_user
        mtltools_module.cmd_gen_data_xdr = original_gen_xdr

    await bot.session.close()

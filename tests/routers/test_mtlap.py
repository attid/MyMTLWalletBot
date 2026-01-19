import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from routers.mtlap import (
    MTLAPStateTools,
    RECOMMEND_PREFIX,
    cmd_mtlap_send_add_delegate_for_a,
    cmd_mtlap_send_recommend,
    cmd_mtlap_tools,
    cmd_mtlap_tools_add_delegate_a,
    cmd_mtlap_tools_delegate_a,
    cmd_mtlap_tools_delegate_c,
    cmd_mtlap_tools_recommend,
)
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN


@pytest.fixture
async def mtlap_app_context(mock_app_context, mock_server):
    session = AiohttpSession(api=TelegramAPIServer.from_base(MOCK_SERVER_URL))
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    mock_app_context.bot = bot
    mock_app_context.dispatcher = Dispatcher(storage=MemoryStorage())
    yield mock_app_context
    await bot.session.close()


def _last_request(mock_server, method):
    return next((req for req in reversed(mock_server) if req["method"] == method), None)


@pytest.mark.asyncio
async def test_cmd_mtlap_tools(mock_server, mock_session, mock_callback, mock_state, mtlap_app_context):
    await cmd_mtlap_tools(mock_callback, mock_state, mock_session, mtlap_app_context)

    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "mtlap_tools_text"
    mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_mtlap_tools_delegate_a(mock_server, mock_session, mock_callback, mock_state, mtlap_app_context):
    with patch("routers.mtlap.stellar_get_data", new_callable=AsyncMock) as mock_get_data:
        mock_get_data.return_value = {"mtla_a_delegate": "DelegateA"}

        await cmd_mtlap_tools_delegate_a(mock_callback, mock_state, mock_session, mtlap_app_context)

    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "delegate_start"
    mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_mtlap_tools_delegate_c(mock_server, mock_session, mock_callback, mock_state, mtlap_app_context):
    with patch("routers.mtlap.stellar_get_data", new_callable=AsyncMock) as mock_get_data:
        mock_get_data.return_value = {"mtla_c_delegate": "DelegateC"}

        await cmd_mtlap_tools_delegate_c(mock_callback, mock_state, mock_session, mtlap_app_context)

    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "delegate_start"
    mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_mtlap_tools_add_delegate_a_low_xlm(
    mock_server, mock_session, mock_callback, mock_state, mtlap_app_context
):
    with patch("routers.mtlap.have_free_xlm", new_callable=AsyncMock) as mock_have_free_xlm:
        mock_have_free_xlm.return_value = False

        await cmd_mtlap_tools_add_delegate_a(
            mock_callback, mock_state, mock_session, mtlap_app_context
        )

    assert _last_request(mock_server, "sendMessage") is None
    mock_callback.answer.assert_awaited_once()
    _, kwargs = mock_callback.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_cmd_mtlap_tools_add_delegate_a_ok(
    mock_server, mock_session, mock_callback, mock_state, mtlap_app_context
):
    with patch("routers.mtlap.have_free_xlm", new_callable=AsyncMock) as mock_have_free_xlm:
        mock_have_free_xlm.return_value = True

        await cmd_mtlap_tools_add_delegate_a(
            mock_callback, mock_state, mock_session, mtlap_app_context
        )

    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "delegate_send_address"
    mock_state.set_state.assert_awaited_once_with(MTLAPStateTools.delegate_for_a)
    mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_mtlap_send_add_delegate_for_a(
    mock_server, mock_session, mock_message, mock_state, mtlap_app_context
):
    mock_message.text = "GDELEGATE"
    mock_account = MagicMock()
    mock_account.account.account.account_id = "GDELEGATE"
    mock_user_account = MagicMock()
    mock_user_account.account.account_id = "GUSER"

    with patch("routers.mtlap.stellar_check_account", new_callable=AsyncMock) as mock_check, \
         patch("routers.mtlap.stellar_get_user_account", new_callable=AsyncMock) as mock_get_user, \
         patch("routers.mtlap.cmd_gen_data_xdr", new_callable=AsyncMock) as mock_gen_xdr:
        mock_check.return_value = mock_account
        mock_get_user.return_value = mock_user_account
        mock_gen_xdr.return_value = "XDR"

        await cmd_mtlap_send_add_delegate_for_a(
            mock_message, mock_state, mock_session, mtlap_app_context
        )

    mock_state.update_data.assert_awaited_once_with(xdr="XDR")
    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "delegate_add"
    mock_message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_mtlap_tools_recommend(
    mock_server, mock_session, mock_callback, mock_state, mtlap_app_context
):
    with patch("routers.mtlap.stellar_get_data", new_callable=AsyncMock) as mock_get_data:
        mock_get_data.return_value = {}

        await cmd_mtlap_tools_recommend(mock_callback, mock_state, mock_session, mtlap_app_context)

    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "recommend_prompt"
    mock_state.set_state.assert_awaited_once_with(MTLAPStateTools.recommend_for)
    mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_mtlap_send_recommend(
    mock_server, mock_session, mock_message, mock_state, mtlap_app_context
):
    mock_message.text = "GRECOMMEND"
    mock_account = MagicMock()
    mock_account.account.account.account_id = "GRECOMMEND"
    mock_user_account = MagicMock()
    mock_user_account.account.account_id = "GUSER"

    with patch("routers.mtlap.stellar_get_data", new_callable=AsyncMock) as mock_get_data, \
         patch("routers.mtlap.stellar_check_account", new_callable=AsyncMock) as mock_check, \
         patch("routers.mtlap.stellar_get_user_account", new_callable=AsyncMock) as mock_get_user, \
         patch("routers.mtlap.cmd_gen_data_xdr", new_callable=AsyncMock) as mock_gen_xdr:
        mock_get_data.return_value = {}
        mock_check.return_value = mock_account
        mock_get_user.return_value = mock_user_account
        mock_gen_xdr.return_value = "XDR"

        await cmd_mtlap_send_recommend(mock_message, mock_state, mock_session, mtlap_app_context)

    mock_gen_xdr.assert_awaited_once_with("GUSER", RECOMMEND_PREFIX, "GRECOMMEND")
    mock_state.update_data.assert_awaited_once_with(xdr="XDR")
    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "recommend_confirm"
    mock_message.delete.assert_awaited_once()

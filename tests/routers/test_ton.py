import pytest
from unittest.mock import AsyncMock, MagicMock

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from routers.ton import (
    cmd_send_ton_start,
    cmd_send_ton_address,
    cmd_send_ton_sum,
    cmd_send_ton_confirm,
    cmd_send_ton_cancel,
    cmd_send_ton_usdt_start,
    cmd_send_ton_usdt_address,
    cmd_send_ton_usdt_sum,
    cmd_send_ton_usdt_confirm,
    cmd_send_ton_usdt_cancel,
    StateSendTon,
    StateSendTonUSDT,
)
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN


@pytest.fixture
async def ton_app_context(mock_app_context, mock_telegram):
    session = AiohttpSession(api=TelegramAPIServer.from_base(MOCK_SERVER_URL))
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    mock_app_context.bot = bot
    mock_app_context.dispatcher = Dispatcher(storage=MemoryStorage())
    yield mock_app_context
    await bot.session.close()


def make_state(initial=None):
    data = dict(initial or {})
    state = AsyncMock()

    async def get_data():
        return dict(data)

    async def update_data(**kwargs):
        data.update(kwargs)

    async def set_data(value):
        data.clear()
        data.update(value)

    async def clear():
        data.clear()

    state.get_data.side_effect = get_data
    state.update_data.side_effect = update_data
    state.set_data.side_effect = set_data
    state.set_state = AsyncMock()
    state.clear.side_effect = clear
    return state


def _text_requests(mock_server):
    return [
        req
        for req in mock_server
        if req["method"] in ("sendMessage", "editMessageText")
    ]


@pytest.mark.asyncio
async def test_cmd_send_ton_start(mock_telegram, mock_session, mock_callback, ton_app_context):
    state = make_state()

    await cmd_send_ton_start(
        mock_callback,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    state.set_state.assert_awaited_once_with(StateSendTon.sending_for)
    mock_callback.answer.assert_awaited_once()
    assert any(
        req["data"]["text"] == "Enter recipient's address:" for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_address_valid(
        mock_telegram, mock_session, mock_message, ton_app_context
):
    state = make_state()
    mock_message.text = "EQD" + ("A" * 45)

    await cmd_send_ton_address(
        mock_message,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    state_data = await state.get_data()
    assert state_data["recipient_address"] == mock_message.text
    state.set_state.assert_awaited_once_with(StateSendTon.sending_sum)
    mock_message.delete.assert_awaited_once()
    assert any(
        req["data"]["text"] == "Enter amount to send:" for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_address_invalid(
        mock_telegram, mock_session, mock_message, ton_app_context
):
    state = make_state()
    mock_message.text = "short"

    await cmd_send_ton_address(
        mock_message,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    state.set_state.assert_not_awaited()
    mock_message.delete.assert_not_awaited()
    assert any(
        "Invalid address" in req["data"]["text"] for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_sum_valid(
        mock_telegram, mock_session, mock_message, ton_app_context
):
    state = make_state({"recipient_address": "EQD" + ("A" * 45)})
    mock_message.text = "10.5"

    await cmd_send_ton_sum(
        mock_message,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    state_data = await state.get_data()
    assert state_data["amount"] == 10.5
    state.set_state.assert_awaited_once_with(StateSendTon.sending_confirmation)
    mock_message.delete.assert_awaited_once()
    assert any(
        "Please confirm sending 10.5 TON" in req["data"]["text"]
        for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_sum_invalid(
        mock_telegram, mock_session, mock_message, ton_app_context
):
    state = make_state({"recipient_address": "EQD" + ("A" * 45)})
    mock_message.text = "-1"

    await cmd_send_ton_sum(
        mock_message,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    state.set_state.assert_not_awaited()
    mock_message.delete.assert_not_awaited()
    assert any(
        "Invalid amount" in req["data"]["text"] for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_confirm_success(
        mock_telegram, mock_session, mock_callback, ton_app_context
):
    state = make_state({"recipient_address": "EQD" + ("A" * 45), "amount": 10.5})

    secret_service = AsyncMock()
    secret_service.is_ton_wallet.return_value = True
    secret_service.get_ton_mnemonic.return_value = "mnemonic"
    ton_app_context.use_case_factory.create_wallet_secret_service.return_value = secret_service

    ton_service = MagicMock()
    ton_service.from_mnemonic = MagicMock()
    ton_service.send_ton = AsyncMock(return_value=True)
    ton_app_context.ton_service = ton_service

    await cmd_send_ton_confirm(
        mock_callback,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    ton_service.send_ton.assert_awaited_once_with("EQD" + ("A" * 45), 10.5)
    mock_callback.answer.assert_awaited_once()
    assert any(
        "Sending transaction" in req["data"]["text"] for req in _text_requests(mock_telegram)
    )
    assert any(
        "Successfully sent 10.5 TON" in req["data"]["text"]
        for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_confirm_not_ton_wallet(
        mock_telegram, mock_session, mock_callback, ton_app_context
):
    state = make_state({"recipient_address": "EQD" + ("A" * 45), "amount": 10.5})

    secret_service = AsyncMock()
    secret_service.is_ton_wallet.return_value = False
    ton_app_context.use_case_factory.create_wallet_secret_service.return_value = secret_service

    await cmd_send_ton_confirm(
        mock_callback,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    mock_callback.answer.assert_awaited_once()
    assert any(
        "not a TON wallet" in req["data"]["text"] for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_cancel(
        mock_telegram, mock_session, mock_callback, ton_app_context
):
    state = make_state()

    await cmd_send_ton_cancel(
        mock_callback,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    mock_callback.answer.assert_awaited_once()
    assert any(
        "Transaction cancelled." in req["data"]["text"] for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_usdt_start(
        mock_telegram, mock_session, mock_callback, ton_app_context
):
    state = make_state()

    await cmd_send_ton_usdt_start(
        mock_callback,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    state.set_state.assert_awaited_once_with(StateSendTonUSDT.sending_for)
    mock_callback.answer.assert_awaited_once()
    assert any(
        req["data"]["text"] == "Enter recipient's address:" for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_usdt_address_valid(
        mock_telegram, mock_session, mock_message, ton_app_context
):
    state = make_state()
    mock_message.text = "EQD" + ("B" * 45)

    await cmd_send_ton_usdt_address(
        mock_message,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    state_data = await state.get_data()
    assert state_data["recipient_address"] == mock_message.text
    state.set_state.assert_awaited_once_with(StateSendTonUSDT.sending_sum)
    mock_message.delete.assert_awaited_once()
    assert any(
        req["data"]["text"] == "Enter amount to send:" for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_usdt_sum_valid(
        mock_telegram, mock_session, mock_message, ton_app_context
):
    state = make_state({"recipient_address": "EQD" + ("B" * 45)})
    mock_message.text = "5"

    await cmd_send_ton_usdt_sum(
        mock_message,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    state_data = await state.get_data()
    assert state_data["amount"] == 5.0
    state.set_state.assert_awaited_once_with(StateSendTonUSDT.sending_confirmation)
    mock_message.delete.assert_awaited_once()
    assert any(
        "Please confirm sending 5.0 USDT" in req["data"]["text"]
        for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_usdt_confirm_success(
        mock_telegram, mock_session, mock_callback, ton_app_context
):
    state = make_state({"recipient_address": "EQD" + ("B" * 45), "amount": 5.0})

    secret_service = AsyncMock()
    secret_service.is_ton_wallet.return_value = True
    secret_service.get_ton_mnemonic.return_value = "mnemonic"
    ton_app_context.use_case_factory.create_wallet_secret_service.return_value = secret_service

    ton_service = MagicMock()
    ton_service.from_mnemonic = MagicMock()
    ton_service.send_usdt = AsyncMock(return_value=True)
    ton_app_context.ton_service = ton_service

    await cmd_send_ton_usdt_confirm(
        mock_callback,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    ton_service.send_usdt.assert_awaited_once_with("EQD" + ("B" * 45), 5.0)
    mock_callback.answer.assert_awaited_once()
    assert any(
        "Sending transaction" in req["data"]["text"] for req in _text_requests(mock_telegram)
    )
    assert any(
        "Successfully sent 5.0 USDT" in req["data"]["text"]
        for req in _text_requests(mock_telegram)
    )


@pytest.mark.asyncio
async def test_cmd_send_ton_usdt_cancel(
        mock_telegram, mock_session, mock_callback, ton_app_context
):
    state = make_state()

    await cmd_send_ton_usdt_cancel(
        mock_callback,
        state,
        mock_session,
        app_context=ton_app_context,
    )

    mock_callback.answer.assert_awaited_once()
    assert any(
        "Transaction cancelled." in req["data"]["text"] for req in _text_requests(mock_telegram)
    )

import pytest
from unittest.mock import AsyncMock, MagicMock

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from keyboards.common_keyboards import HideNotificationCallbackData
from routers.notification_settings import (
    hide_notification_callback,
    toggle_token_callback,
    change_amount_callback,
    toggle_wallets_callback,
    save_filter_callback,
    notification_settings_callback,
    delete_all_filters_callback,
)
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN


@pytest.fixture
async def notification_settings_app_context(mock_app_context, mock_server):
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
    state.clear.side_effect = clear
    return state


def _last_text_request(mock_server):
    return next(
        (
            req
            for req in reversed(mock_server)
            if req["method"] in ("sendMessage", "editMessageText")
        ),
        None,
    )


@pytest.mark.asyncio
async def test_hide_notification_callback(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    state = make_state()

    callback_data = HideNotificationCallbackData(wallet_id=1, operation_id="10")
    mock_callback.data = callback_data.pack()

    mock_wallet = MagicMock()
    mock_wallet.user_id = 123
    mock_wallet.public_key = "GKey"

    mock_op = MagicMock()
    mock_op.id = 10
    mock_op.code1 = "XLM"
    mock_op.amount1 = "10.0"
    mock_op.operation = "payment"

    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_by_id = AsyncMock(return_value=mock_wallet)
    notification_settings_app_context.repository_factory.get_wallet_repository.return_value = (
        mock_wallet_repo
    )

    mock_op_repo = MagicMock()
    mock_op_repo.get_by_id = AsyncMock(return_value=mock_op)
    notification_settings_app_context.repository_factory.get_operation_repository.return_value = (
        mock_op_repo
    )

    await hide_notification_callback(
        mock_callback,
        state,
        mock_session,
        app_context=notification_settings_app_context,
    )

    state_data = await state.get_data()
    assert state_data["asset_code"] == "XLM"
    assert state_data["min_amount"] == 10.0
    assert state_data["operation_type"] == "payment"

    request = _last_text_request(mock_server)
    assert request is not None
    assert request["data"]["text"] == "notification_settings_menu"
    mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_token_callback_sets_asset(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    state = make_state(
        {
            "asset_code": None,
            "operation_id": 10,
            "min_amount": 0,
            "for_all_wallets": False,
        }
    )

    mock_op = MagicMock()
    mock_op.code1 = "EURMTL"
    mock_op_repo = MagicMock()
    mock_op_repo.get_by_id = AsyncMock(return_value=mock_op)
    notification_settings_app_context.repository_factory.get_operation_repository.return_value = (
        mock_op_repo
    )

    await toggle_token_callback(
        mock_callback,
        state,
        mock_session,
        app_context=notification_settings_app_context,
    )

    state_data = await state.get_data()
    assert state_data["asset_code"] == "EURMTL"
    assert _last_text_request(mock_server) is not None


@pytest.mark.asyncio
async def test_toggle_token_callback_clears_asset(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    state = make_state(
        {
            "asset_code": "EURMTL",
            "operation_id": 10,
            "min_amount": 0,
            "for_all_wallets": False,
        }
    )

    await toggle_token_callback(
        mock_callback,
        state,
        mock_session,
        app_context=notification_settings_app_context,
    )

    state_data = await state.get_data()
    assert state_data["asset_code"] is None
    assert _last_text_request(mock_server) is not None


@pytest.mark.asyncio
async def test_change_amount_callback_cycles(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    state = make_state(
        {
            "min_amount": 0,
            "asset_code": "EURMTL",
            "for_all_wallets": False,
        }
    )

    await change_amount_callback(
        mock_callback,
        state,
        mock_session,
        app_context=notification_settings_app_context,
    )

    state_data = await state.get_data()
    assert state_data["min_amount"] == 1
    assert _last_text_request(mock_server) is not None


@pytest.mark.asyncio
async def test_toggle_wallets_callback(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    state = make_state(
        {
            "for_all_wallets": False,
            "asset_code": "EURMTL",
            "min_amount": 0,
        }
    )

    await toggle_wallets_callback(
        mock_callback,
        state,
        mock_session,
        app_context=notification_settings_app_context,
    )

    state_data = await state.get_data()
    assert state_data["for_all_wallets"] is True
    assert _last_text_request(mock_server) is not None


@pytest.mark.asyncio
async def test_save_filter_callback_creates(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    state = make_state(
        {
            "asset_code": "XLM",
            "min_amount": 10,
            "operation_type": "payment",
            "public_key": "GKey",
            "for_all_wallets": False,
        }
    )

    mock_repo = MagicMock()
    mock_repo.find_duplicate = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock()
    notification_settings_app_context.repository_factory.get_notification_repository.return_value = (
        mock_repo
    )

    await save_filter_callback(
        mock_callback,
        state,
        mock_session,
        app_context=notification_settings_app_context,
    )

    mock_repo.create.assert_awaited_once()
    state.clear.assert_awaited_once()
    request = _last_text_request(mock_server)
    assert request is not None
    assert request["data"]["text"] == "filter_saved"


@pytest.mark.asyncio
async def test_save_filter_callback_duplicate(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    state = make_state(
        {
            "asset_code": "XLM",
            "min_amount": 10,
            "operation_type": "payment",
            "public_key": "GKey",
            "for_all_wallets": False,
        }
    )

    mock_filter = MagicMock()
    mock_filter.id = 1
    mock_filter.public_key = "GKey"
    mock_filter.asset_code = "XLM"
    mock_filter.min_amount = 10
    mock_filter.operation_type = "payment"

    mock_repo = MagicMock()
    mock_repo.find_duplicate = AsyncMock(return_value=mock_filter)
    mock_repo.create = AsyncMock()
    notification_settings_app_context.repository_factory.get_notification_repository.return_value = (
        mock_repo
    )

    await save_filter_callback(
        mock_callback,
        state,
        mock_session,
        app_context=notification_settings_app_context,
    )

    mock_repo.create.assert_not_called()
    state.clear.assert_not_called()
    request = _last_text_request(mock_server)
    assert request is not None
    assert request["data"]["text"] == "filter_already_exists"


@pytest.mark.asyncio
async def test_notification_settings_callback(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    mock_repo = MagicMock()
    mock_repo.get_by_user_id = AsyncMock(return_value=[MagicMock(), MagicMock()])
    notification_settings_app_context.repository_factory.get_notification_repository.return_value = (
        mock_repo
    )

    await notification_settings_callback(
        mock_callback,
        mock_session,
        app_context=notification_settings_app_context,
    )

    request = _last_text_request(mock_server)
    assert request is not None
    assert request["data"]["text"] == "notification_settings_info"
    mock_callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_all_filters_callback(
    mock_server, mock_session, mock_callback, notification_settings_app_context
):
    mock_repo = MagicMock()
    mock_repo.delete_all_by_user = AsyncMock()
    notification_settings_app_context.repository_factory.get_notification_repository.return_value = (
        mock_repo
    )

    await delete_all_filters_callback(
        mock_callback,
        mock_session,
        app_context=notification_settings_app_context,
    )

    mock_repo.delete_all_by_user.assert_awaited_once_with(mock_callback.from_user.id)
    request = _last_text_request(mock_server)
    assert request is not None
    assert request["data"]["text"] == "all_filters_deleted"
    mock_callback.answer.assert_awaited_once()

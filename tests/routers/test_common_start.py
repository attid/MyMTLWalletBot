import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from other.mytypes import Balance
from routers.common_start import cb_set_limit, cmd_start
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN


@pytest.fixture
async def common_start_app_context(mock_app_context, mock_server):
    session = AiohttpSession(api=TelegramAPIServer.from_base(MOCK_SERVER_URL))
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    mock_app_context.bot = bot
    mock_app_context.dispatcher = Dispatcher(storage=MemoryStorage())
    yield mock_app_context
    await bot.session.close()


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def mock_message():
    message = MagicMock()
    message.from_user.id = 123
    message.from_user.username = "user"
    message.chat.id = 123
    message.chat.type = "private"
    message.text = "/start"
    return message


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

    state.get_data.side_effect = get_data
    state.update_data.side_effect = update_data
    state.set_data.side_effect = set_data
    state.set_state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    return state


def _requests(mock_server, method):
    return [req for req in mock_server if req["method"] == method]


def _text_requests(mock_server):
    return [
        req
        for req in mock_server
        if req["method"] in ("sendMessage", "editMessageText")
    ]


@pytest.mark.asyncio
async def test_cmd_start_existing_user(
    mock_server, mock_session, mock_message, common_start_app_context
):
    mock_message.text = "/start"
    mock_message.chat.type = "private"

    state = make_state()

    mock_user = MagicMock()
    mock_user.id = mock_message.from_user.id
    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
    common_start_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    mock_wallet = MagicMock()
    mock_wallet.public_key = "GTEST123..."
    mock_wallet.is_free = False
    mock_wallet.assets_visibility = None
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_wallet_repo.get_info = AsyncMock(return_value="Info")
    common_start_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    secret_service = AsyncMock()
    secret_service.is_ton_wallet.return_value = False
    common_start_app_context.use_case_factory.create_wallet_secret_service.return_value = secret_service

    balance_uc = AsyncMock()
    balance_uc.execute.return_value = [
        Balance(asset_code="EURMTL", balance="100", selling_liabilities="0.0", asset_issuer="GISSUER"),
    ]
    common_start_app_context.use_case_factory.create_get_wallet_balance.return_value = balance_uc

    update_profile = AsyncMock()
    common_start_app_context.use_case_factory.create_update_user_profile.return_value = update_profile

    with patch("routers.common_start.check_user_lang", new_callable=AsyncMock, return_value="en"):
        await cmd_start(
            mock_message,
            state,
            mock_session,
            common_start_app_context.bot,
            common_start_app_context,
            common_start_app_context.localization_service,
        )

    send_messages = _text_requests(mock_server)
    assert any(req["data"]["text"] == "Loading" for req in send_messages)
    assert any("your_balance" in req["data"]["text"] for req in send_messages)

    assert _requests(mock_server, "sendChatAction")


@pytest.mark.asyncio
async def test_cb_set_limit(
    mock_server, mock_session, mock_callback, common_start_app_context
):
    mock_callback.data = "OffLimits"

    state = make_state()

    mock_user = MagicMock()
    mock_user.can_5000 = 0
    mock_user_repo = MagicMock()
    mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
    mock_user_repo.update = AsyncMock(return_value=mock_user)
    common_start_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    await cb_set_limit(mock_callback, state, mock_session, common_start_app_context)

    assert mock_user.can_5000 == 1
    mock_user_repo.update.assert_awaited_once_with(mock_user)
    mock_session.commit.assert_called_once()

    send_messages = _requests(mock_server, "sendMessage")
    assert send_messages

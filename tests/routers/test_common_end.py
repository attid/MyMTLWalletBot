import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from other.mytypes import Balance
from routers.common_end import cmd_last_route
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN


@pytest.fixture
async def common_end_app_context(mock_app_context, mock_server):
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

    state.get_data.side_effect = get_data
    state.update_data.side_effect = update_data
    state.set_data.side_effect = set_data
    state.set_state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    return state


def _last_request(mock_server, method):
    return next((req for req in reversed(mock_server) if req["method"] == method), None)


@pytest.mark.asyncio
async def test_cmd_last_route_stellar_address(
    mock_server, mock_session, mock_message, common_end_app_context
):
    mock_message.chat.type = "private"
    mock_message.text = "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB"
    mock_message.entities = []
    mock_message.caption = None
    mock_message.forward_sender_name = None
    mock_message.forward_from = None

    state = make_state()

    balance_uc = AsyncMock()
    user_balances = [Balance(asset_code="EURMTL", balance="100", asset_issuer="GISSUER")]
    sender_balances = [Balance(asset_code="EURMTL", balance="50", asset_issuer="GISSUER")]
    balance_uc.execute.side_effect = [user_balances, sender_balances]
    common_end_app_context.use_case_factory.create_get_wallet_balance.return_value = balance_uc

    with patch("routers.common_end.stellar_check_account", new_callable=AsyncMock) as mock_check:
        mock_account = MagicMock()
        mock_account.account_id = mock_message.text
        mock_account.memo = None
        mock_check.return_value = mock_account

        await cmd_last_route(mock_message, state, mock_session, common_end_app_context)

    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "choose_token"


@pytest.mark.asyncio
async def test_cmd_last_route_xdr_base64(
    mock_server, mock_session, mock_message, common_end_app_context
):
    mock_message.chat.type = "private"
    mock_message.entities = []
    mock_message.text = base64.b64encode(b"x" * 48).decode()

    state = make_state()

    common_end_app_context.stellar_service.is_free_wallet.return_value = False
    common_end_app_context.stellar_service.check_xdr.return_value = "XDR"
    common_end_app_context.stellar_service.get_user_account.return_value = MagicMock(
        account=MagicMock(account_id="GUSER")
    )

    mock_wallet = MagicMock()
    mock_wallet.use_pin = 0
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)

    with patch(
        "infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository",
        return_value=mock_repo,
    ):
        await cmd_last_route(mock_message, state, mock_session, common_end_app_context)

    request = _last_request(mock_server, "sendMessage")
    assert request is not None


@pytest.mark.asyncio
async def test_cmd_last_route_sign_tools_link(
    mock_server, mock_session, mock_message, common_end_app_context
):
    mock_message.chat.type = "private"
    mock_message.text = "Check https://eurmtl.me/sign_tools?xdr=AAAA"
    mock_entity = MagicMock()
    mock_entity.type = "url"
    mock_entity.url = "https://eurmtl.me/sign_tools?xdr=AAAA"
    mock_message.entities = [mock_entity]

    state = make_state()

    common_end_app_context.stellar_service.is_free_wallet.return_value = False
    common_end_app_context.stellar_service.check_xdr.return_value = "XDR"
    common_end_app_context.stellar_service.get_user_account.return_value = MagicMock(
        account=MagicMock(account_id="GUSER")
    )

    mock_wallet = MagicMock()
    mock_wallet.use_pin = 0
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)

    with patch(
        "infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository",
        return_value=mock_repo,
    ):
        await cmd_last_route(mock_message, state, mock_session, common_end_app_context)

    request = _last_request(mock_server, "sendMessage")
    assert request is not None


@pytest.mark.asyncio
async def test_cmd_last_route_forwarded_with_username(
    mock_server, mock_session, mock_message, common_end_app_context
):
    mock_message.chat.type = "private"
    mock_message.text = "Some text"
    mock_message.entities = []
    mock_message.caption = None
    mock_message.forward_sender_name = None

    mock_forward_user = MagicMock()
    mock_forward_user.username = "testuser"
    mock_message.forward_from = mock_forward_user

    state = make_state()

    balance_uc = AsyncMock()
    user_balances = [Balance(asset_code="EURMTL", balance="100", asset_issuer="GISSUER")]
    sender_balances = [Balance(asset_code="EURMTL", balance="50", asset_issuer="GISSUER")]
    balance_uc.execute.side_effect = [user_balances, sender_balances]
    common_end_app_context.use_case_factory.create_get_wallet_balance.return_value = balance_uc

    mock_user_repo = MagicMock()
    mock_user_repo.get_account_by_username = AsyncMock(return_value=("GTEST123...", 456))
    common_end_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    with patch("routers.common_end.stellar_check_account", new_callable=AsyncMock) as mock_check:
        mock_account = MagicMock()
        mock_account.account_id = "GTEST123..."
        mock_account.memo = "test_memo"
        mock_check.return_value = mock_account

        await cmd_last_route(mock_message, state, mock_session, common_end_app_context)

    mock_user_repo.get_account_by_username.assert_awaited_once_with("@testuser")
    request = _last_request(mock_server, "sendMessage")
    assert request is not None
    assert request["data"]["text"] == "choose_token"


@pytest.mark.asyncio
async def test_cmd_last_route_non_private_chat(
    mock_server, mock_session, mock_message, common_end_app_context
):
    mock_message.chat.type = "group"
    mock_message.text = "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB"

    state = make_state()

    await cmd_last_route(mock_message, state, mock_session, common_end_app_context)

    assert _last_request(mock_server, "sendMessage") is None


@pytest.mark.asyncio
async def test_cmd_last_route_normal_message(
    mock_server, mock_session, mock_message, common_end_app_context
):
    mock_message.chat.type = "private"
    mock_message.text = "Just a normal message"
    mock_message.entities = []
    mock_message.caption = None
    mock_message.forward_sender_name = None
    mock_message.forward_from = None

    state = make_state()

    await cmd_last_route(mock_message, state, mock_session, common_end_app_context)

    mock_message.delete.assert_called_once()

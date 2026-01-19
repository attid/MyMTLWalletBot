
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import datetime
import uuid

from routers.cheque import router as cheque_router, ChequeCallbackData, StateCheque
from db.models import ChequeStatus
from core.domain.value_objects import PaymentResult, Balance
from core.use_cases.cheque.claim_cheque import ClaimResult
from core.use_cases.cheque.cancel_cheque import CancelResult
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from infrastructure.services.localization_service import LocalizationService

class MockDbMiddleware(BaseMiddleware):
    def __init__(self, session, app_context):
        self.session = session
        self.app_context = app_context
        self.l10n = MagicMock(spec=LocalizationService)

    async def __call__(self, handler, event, data):
        data["session"] = self.session
        data["app_context"] = self.app_context
        data["l10n"] = self.l10n
        return await handler(event, data)

@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if cheque_router.parent_router:
         cheque_router._parent_router = None

@pytest.fixture
def mock_session():
    session = MagicMock()
    return session

@pytest.fixture
async def bot():
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)
    yield bot
    await bot.session.close()

@pytest.fixture
def dp(mock_session, mock_app_context):
    dp = Dispatcher()
    middleware = MockDbMiddleware(mock_session, mock_app_context)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)
    dp.inline_query.middleware(middleware)
    dp.include_router(cheque_router)
    return dp

@pytest.mark.asyncio
async def test_cmd_create_cheque_flow_full(mock_telegram, bot, dp, mock_session, mock_app_context):
    """
    Full flow: /create_cheque -> sum -> count -> comment -> execute
    """
    user_id = 123
    mock_app_context.bot = bot
    
    # 1. Start
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        message=types.Message(
            message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
            from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            text="/create_cheque"
        )
    ))
    mock_telegram.clear()

    # 2. Sum
    mock_create_cheque = MagicMock()
    mock_create_cheque.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR"))
    mock_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=2,
        message=types.Message(
            message_id=2, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
            from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            text="50"
        )
    ))
    mock_telegram.clear()

    # 3. Click "Change Comment"
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=3,
        callback_query=types.CallbackQuery(
            id="cb1", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci1", message=types.Message(message_id=2, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="ChequeComment"
        )
    ))
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) == 1
    assert "kb_change_comment" in sent_messages[0]['data']['text']
    mock_telegram.clear()

    # 4. Enter Comment
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=4,
        message=types.Message(
            message_id=4, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
            from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            text="For Pizza"
        )
    ))
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) >= 1
    mock_telegram.clear()

    # 5. Execute
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=5,
        callback_query=types.CallbackQuery(
            id="cb2", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci2", message=types.Message(message_id=2, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="ChequeExecute"
        )
    ))
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert "confirm_send" in sent_messages[0]['data']['text']


@pytest.mark.asyncio
async def test_cb_cheque_info(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test cheque info callback"""
    user_id = 123
    cheque_uuid = "uuid-info"
    mock_app_context.bot = bot
    
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.count = 10
    
    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(return_value=3) 
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo

    cb_data = ChequeCallbackData(uuid=cheque_uuid, cmd="info").pack()

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb_info", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Info"),
            data=cb_data
        )
    ))
    
    answers = [r for r in mock_telegram if r['method'] == 'answerCallbackQuery']
    assert len(answers) == 1
    assert "3" in answers[0]['data']['text'] # received
    assert "10" in answers[0]['data']['text'] # total


@pytest.mark.asyncio
async def test_cmd_invoice_yes(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test InvoiceYes callback"""
    user_id = 123
    cheque_uuid = "uuid-invoice"
    mock_app_context.bot = bot
    
    # 1. Setup Cheque (Invoice)
    # Use valid stellar public key
    valid_issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    
    mock_cheque = MagicMock()
    mock_cheque.status = ChequeStatus.INVOICE.value
    mock_cheque.count = 5
    mock_cheque.asset = f"BTC:{valid_issuer}"
    mock_cheque.amount = 0.1
    mock_cheque.uuid = cheque_uuid

    mock_repo = MagicMock()
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(return_value=0)
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo

    # 2. Setup Balance UseCase (User has EURMTL to pay)
    mock_balance_uc = MagicMock()
    mock_balance = Balance(asset_code="EURMTL", asset_issuer="G...", balance=100.0, limit=None, asset_type="credit_alphanum12")
    mock_balance_uc.execute = AsyncMock(return_value=[mock_balance])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    # 3. Setup Wallet Repo (needed for trustline build)
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GUSER"
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    mock_app_context.stellar_service.build_change_trust_transaction = AsyncMock(return_value="XDR_TRUST")

    # Let's run /start invoice_... first to set state
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        message=types.Message(
            message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
            from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            text=f"/start invoice_{cheque_uuid}"
        )
    ))
    mock_telegram.clear()

    # Now click InvoiceYes
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=2,
        callback_query=types.CallbackQuery(
            id="cb_inv", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=2, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Invoice"),
            data="InvoiceYes"
        )
    ))
    
    # Expect: send_sum_swap message
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) >= 1
    assert "send_sum_swap" in sent_messages[-1]['data']['text']
    
    # Verify trustline was built (since user didn't have BTC)
    mock_app_context.stellar_service.build_change_trust_transaction.assert_called()


@pytest.mark.asyncio
async def test_inline_query_cheques(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test inline query for cheques"""
    user_id = 999
    mock_app_context.bot = bot
    
    mock_cheque = MagicMock()
    mock_cheque.uuid = "uuid-inline"
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.amount = 5.0
    mock_cheque.count = 1
    mock_cheque.comment = "InlineC"
    
    mock_repo = MagicMock()
    mock_repo.get_available = AsyncMock(return_value=[mock_cheque])
    mock_app_context.repository_factory.get_cheque_repository.return_value = mock_repo
    
    # Mock bot.me for link generation
    mock_me = MagicMock()
    mock_me.username = "testbot"
    with patch.object(bot, 'me', AsyncMock(return_value=mock_me)):
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=1,
            inline_query=types.InlineQuery(
                id="iq1", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                query="", offset=""
            )
        ))
    
    answers = [r for r in mock_telegram if r['method'] == 'answerInlineQuery']
    assert len(answers) == 1
    results_str = answers[0]['data']['results']
    results = json.loads(results_str)
    assert len(results) == 1
    assert "uuid-inline" == results[0]['id']

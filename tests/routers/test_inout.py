
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import datetime
from decimal import Decimal

from routers.inout import router as inout_router, StateInOut
from tests.conftest import TEST_BOT_TOKEN
from core.domain.value_objects import Balance, PaymentResult
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
    if inout_router.parent_router:
         inout_router._parent_router = None

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
async def bot(telegram_server_config):
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(telegram_server_config["url"])
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
    dp.include_router(inout_router)
    return dp

@pytest.mark.asyncio
async def test_menu_flow(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test navigation in InOut menu"""
    user_id = 123
    mock_app_context.bot = bot
    
    # 1. Open InOut Menu
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb1", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Start"),
            data="InOut"
        )
    ))
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent) == 1
    assert "inout" in sent[0]['data']['text']
    mock_telegram.clear()

    # 2. Select USDT
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=2,
        callback_query=types.CallbackQuery(
            id="cb2", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=2, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="InOut"),
            data="USDT_TRC20"
        )
    ))
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent) == 1
    assert "inout_usdt" in sent[0]['data']['text']


@pytest.mark.asyncio
async def test_usdt_in_flow(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test USDT Deposit flow"""
    user_id = 123
    mock_app_context.bot = bot
    
    # Mocks for dependencies
    mock_balance_uc = MagicMock()
    # Provide balance for both user and master (0)
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(asset_code="USDM", asset_issuer="iss", balance="1000.0", asset_type="credit_alphanum4", limit="1000")
    ])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
    
    mock_user_repo = MagicMock()
    mock_user_repo.get_usdt_key = AsyncMock(return_value=("PRIVATE_KEY", 50.0))
    mock_user_repo.update_usdt_balance = AsyncMock()
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    with patch("routers.inout.tron_get_public", return_value="TRON_ADDR"):
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=1,
            callback_query=types.CallbackQuery(
                id="cb1", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="USDT Menu"),
                data="USDT_IN"
            )
        ))
    
    mock_telegram.clear()

    # 2. Click USDT_CHECK
    mock_lock = AsyncMock()
    mock_lock.__aenter__.return_value = None
    mock_lock.__aexit__.return_value = None
    
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=MagicMock(public_key="GUSER"))
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    mock_pay_uc = MagicMock()
    mock_pay_uc.execute = AsyncMock(return_value=PaymentResult(success=True))
    mock_app_context.use_case_factory.create_send_payment.return_value = mock_pay_uc

    with patch("routers.inout.new_wallet_lock", mock_lock), \
         patch("routers.inout.get_usdt_balance", AsyncMock(return_value=100.0)), \
         patch("routers.inout.check_unconfirmed_usdt_transactions", AsyncMock(return_value=False)), \
         patch("routers.inout.tron_get_public", return_value="TRON_ADDR"):
         
            await dp.feed_update(bot=bot, update=types.Update(
                update_id=2,
                callback_query=types.CallbackQuery(
                    id="cb2", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                    chat_instance="ci", message=types.Message(message_id=2, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Check"),
                    data="USDT_CHECK"
                )
            ))
            
            sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
            assert any("All works done" in str(m['data']) or "text" in str(m['data']) for m in sent)
            mock_pay_uc.execute.assert_called_once()


@pytest.mark.asyncio
async def test_usdt_out_flow(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test USDT Withdrawal flow"""
    user_id = 123
    mock_app_context.bot = bot
    
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=MagicMock(use_pin=0, public_key="GMASTER"))
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    mock_balance_uc = MagicMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(asset_code="USDM", asset_issuer="iss", balance="100.0", asset_type="credit_alphanum4")
    ])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
    
    # 1. Start USDT_OUT
    with patch("routers.inout.get_usdt_balance", AsyncMock(return_value=1000.0)):
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=1,
            callback_query=types.CallbackQuery(
                id="cb1", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
                data="USDT_OUT"
            )
        ))
    mock_telegram.clear()

    # 2. Send USDT Address
    with patch("routers.inout.check_valid_trx", return_value=True):
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=2,
            message=types.Message(
                message_id=2, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
                from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                text="TUTBziqeXsh3LAH7QUYoaAYruzhUqLWu2n"
            )
        ))
    
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert "send_sum" in sent[0]['data']['text']
    mock_telegram.clear()

    # 3. Send Sum
    mock_energy = MagicMock()
    mock_energy.energy_amount = 200000
    
    mock_pay_uc = MagicMock()
    mock_pay_uc.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR_PAY"))
    mock_app_context.use_case_factory.create_send_payment.return_value = mock_pay_uc

    with patch("routers.inout.get_usdt_transfer_fee", AsyncMock(return_value=(1.0, 100))), \
         patch("routers.inout.get_account_energy", AsyncMock(return_value=mock_energy)):
         
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=3,
            message=types.Message(
                message_id=3, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
                from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                text="20"
            )
        ))
        
        sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
        assert "confirm_send" in sent[0]['data']['text']
        mock_pay_uc.execute.assert_called_once()


@pytest.mark.asyncio
async def test_btc_flow(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test BTC In flow"""
    user_id = 123
    mock_app_context.bot = bot
    
    # 1. Click BTC
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb1", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="BTC"
        )
    ))
    mock_telegram.clear()

    # 2. Click BTC_IN
    mock_user_repo = MagicMock()
    mock_user_repo.get_btc_uuid = AsyncMock(return_value=(None, None))
    mock_user_repo.set_btc_uuid = AsyncMock()
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    mock_balance_uc = MagicMock()
    mock_balance_uc.execute = AsyncMock(side_effect=lambda user_id: [
        Balance(asset_code="SATSMTL", asset_issuer="iss", balance="1000000.0", asset_type="credit_alphanum12")
    ] if user_id == 0 else [
        Balance(asset_code="SATSMTL", asset_issuer="iss", balance="0.0", asset_type="credit_alphanum12")
    ])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=2,
        callback_query=types.CallbackQuery(
            id="cb2", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=2, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="BTC Menu"),
            data="BTC_IN"
        )
    ))
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert "btc_in" in sent[0]['data']['text']
    mock_telegram.clear()

    # 3. Enter Sum
    with patch("routers.inout.thoth_create_order", AsyncMock(return_value="ORDER_UUID")):
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=3,
            message=types.Message(
                message_id=3, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
                from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                text="1000"
            )
        ))
        
    mock_user_repo.set_btc_uuid.assert_called_once_with(user_id, "ORDER_UUID")


@pytest.mark.asyncio
async def test_cmd_balance_admin(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test /balance command (admin only)"""
    user_id = 123
    username = "itolstov"
    mock_app_context.bot = bot
    
    mock_user_repo = MagicMock()
    mock_user_repo.get_all_with_usdt_balance = AsyncMock(return_value=[
        ("addr1", 100.0, 1),
        ("addr2", 200.0, 2)
    ])
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    mock_energy = MagicMock()
    mock_energy.energy_amount = 500000
    
    with patch("routers.inout.get_account_energy", AsyncMock(return_value=mock_energy)):
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=1,
            message=types.Message(
                message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
                from_user=types.User(id=user_id, is_bot=False, first_name="Admin", username=username),
                text="/balance"
            )
        ))
        
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent) == 1
    assert "addr1" in sent[0]['data']['text']
    assert "300.0" in sent[0]['data']['text']

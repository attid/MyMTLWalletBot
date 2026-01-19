
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.fsm.storage.base import StorageKey
import datetime
import jsonpickle

from routers.wallet_setting import router as wallet_setting_router, AssetVisibilityCallbackData, DelAssetCallbackData
from core.domain.entities import Wallet
from core.domain.value_objects import Balance, PaymentResult
from tests.conftest import TEST_BOT_TOKEN
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
    if wallet_setting_router.parent_router:
         wallet_setting_router._parent_router = None

@pytest.fixture
def mock_session():
    from sqlalchemy.orm import Session
    session = MagicMock(spec=Session)
    
    # Configure execute to return a mock result that supports scalar_one_or_none
    mock_result = MagicMock()
    mock_db_wallet = MagicMock()
    mock_db_wallet.balances = "[]"
    mock_db_wallet.public_key = "GUSER"
    mock_db_wallet.user_id = 123
    mock_db_wallet.default_wallet = 1
    mock_db_wallet.free_wallet = 0
    mock_db_wallet.use_pin = 0
    
    mock_result.scalar_one_or_none.return_value = mock_db_wallet
    mock_result.scalars.return_value.first.return_value = mock_db_wallet
    
    session.execute = AsyncMock(return_value=mock_result) # Fix for await session.execute
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session

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
    dp.include_router(wallet_setting_router)
    return dp

@pytest.mark.asyncio
async def test_cmd_wallet_setting(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test WalletSetting main menu"""
    user_id = 123
    mock_app_context.bot = bot
    
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.is_free = True
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="WalletSetting"
        )
    ))
    
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent) == 1
    assert "wallet_setting_msg" in sent[0]['data']['text']
    assert "BuyAddress" in sent[0]['data']['reply_markup']


@pytest.mark.asyncio
async def test_asset_visibility_menu(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test AssetVisibilityMenu loading"""
    user_id = 123
    mock_app_context.bot = bot
    
    # Setup Wallet and Balances
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.assets_visibility = "{}"
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo
    
    mock_balance_uc = MagicMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(asset_code="EURMTL", asset_issuer="G...", balance="10", asset_type="credit_alphanum12"),
        Balance(asset_code="USDM", asset_issuer="G...", balance="5", asset_type="credit_alphanum4")
    ])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="AssetVisibilityMenu"
        )
    ))
    
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent) == 1
    assert "asset_visibility_msg" in sent[0]['data']['text']
    assert "EURMTL" in sent[0]['data']['reply_markup']
    assert "USDM" in sent[0]['data']['reply_markup']


@pytest.mark.asyncio
async def test_asset_visibility_toggle(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test toggling asset visibility"""
    user_id = 123
    mock_app_context.bot = bot
    
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.assets_visibility = "{}"
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo
    
    # For redraw
    mock_balance_uc = MagicMock()
    mock_balance_uc.execute = AsyncMock(return_value=[])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    # Callback to set EURMTL to Hidden (status 2)
    cb_data = AssetVisibilityCallbackData(action="set", code="EURMTL", status=2, page=1).pack()

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data=cb_data
        )
    ))
    
    # Check if wallet was updated and committed
    assert '"EURMTL": "hidden"' in mock_wallet.assets_visibility
    mock_session.commit.assert_called_once()
    
    # Verify UI update
    edits = [r for r in mock_telegram if r['method'] == 'editMessageText']
    assert len(edits) == 1
    assert "asset_visibility_changed" in [r for r in mock_telegram if r['method'] == 'answerCallbackQuery'][0]['data']['text']


@pytest.mark.asyncio
async def test_cmd_delete_asset_list(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test DeleteAsset menu"""
    user_id = 123
    mock_app_context.bot = bot
    
    mock_balance_uc = MagicMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(asset_code="BTCMTL", asset_issuer="G...", balance="0.0", asset_type="credit_alphanum12")
    ])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="DeleteAsset"
        )
    ))
    
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert "delete_asset2" in sent[0]['data']['text']
    assert "BTCMTL" in sent[0]['data']['reply_markup']


@pytest.mark.asyncio
async def test_cq_delete_asset_execute(mock_telegram, mock_horizon, horizon_server_config, bot, dp, mock_session, mock_app_context):
    """Test actual asset deletion (trustline removal)"""
    from infrastructure.services.stellar_service import StellarService
    user_id = 123
    mock_app_context.bot = bot
    
    # 1. Prepare state with assets
    storage_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    valid_issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    assets = [Balance(asset_code="BTCMTL", asset_issuer=valid_issuer, balance="0.0", asset_type="credit_alphanum12")]
    await dp.storage.set_data(key=storage_key, data={"assets": jsonpickle.encode(assets)})
    
    # Mocks for deletion
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.public_key = public_key
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo
    
    # Real StellarService
    mock_app_context.stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    
    # Configure mock_horizon
    mock_horizon.set_account(public_key)
    
    with patch("routers.sign.cmd_ask_pin", AsyncMock()) as mock_ask_pin, \
         patch("routers.wallet_setting.stellar_check_xdr", AsyncMock(side_effect=lambda x: x)):
             
        cb_data = DelAssetCallbackData(answer="BTCMTL").pack()
        await dp.feed_update(bot=bot, update=types.Update(
            update_id=1,
            callback_query=types.CallbackQuery(
                id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
                data=cb_data
            )
        ))
        
        # Verify stored in state
        data = await dp.storage.get_data(key=storage_key)
        assert "xdr" in data
        assert "AAAA" in data['xdr']
        mock_ask_pin.assert_called_once()


@pytest.mark.asyncio
async def test_buy_address_flow(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test BuyAddress flow"""
    user_id = 123
    mock_app_context.bot = bot
    
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.is_free = True
    mock_wallet.public_key = "GFREE"
    
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(side_effect=lambda id: mock_wallet if id != 0 else MagicMock(public_key="GMASTER"))
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo
    
    mock_balance_uc = MagicMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(asset_code="EURMTL", asset_issuer="G...", balance="50.0", asset_type="credit_alphanum12")
    ])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
    
    mock_pay_uc = MagicMock()
    mock_pay_uc.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR_BUY"))
    mock_app_context.use_case_factory.create_send_payment.return_value = mock_pay_uc

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="BuyAddress"
        )
    ))
    
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert "confirm_send" in sent[0]['data']['text']
    assert "XDR_BUY" in str(await dp.storage.get_data(key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)))


@pytest.mark.asyncio
async def test_address_book_view(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test AddressBook viewing"""
    user_id = 123
    mock_app_context.bot = bot
    
    mock_entry = MagicMock()
    mock_entry.id = 1
    mock_entry.address = "GADDR"
    mock_entry.name = "My Friend"
    
    mock_repo = MagicMock()
    mock_repo.get_all = AsyncMock(return_value=[mock_entry])
    mock_app_context.repository_factory.get_addressbook_repository.return_value = mock_repo

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="AddressBook"
        )
    ))
    
    sent = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert "address_book" in sent[0]['data']['text']
    assert "GADDR" in sent[0]['data']['reply_markup']
    assert "My Friend" in sent[0]['data']['reply_markup']

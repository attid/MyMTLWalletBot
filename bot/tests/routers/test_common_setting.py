import pytest
from unittest.mock import MagicMock, AsyncMock
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.dispatcher.middlewares.base import BaseMiddleware
import datetime

from routers.common_setting import router as common_setting_router, LangCallbackData
from routers.start_msg import WalletSettingCallbackData
from infrastructure.services.localization_service import LocalizationService
from aiogram.fsm.storage.base import StorageKey
from tests.conftest import TEST_BOT_TOKEN
from core.interfaces.repositories import IUserRepository, IWalletRepository
from core.interfaces.services import IWalletSecretService
from core.use_cases.wallet.get_balance import GetWalletBalance
from core.domain.entities import User, Wallet

class MockDbMiddleware(BaseMiddleware):
    def __init__(self, session, app_context):
        self.session = session
        self.app_context = app_context
        # We need to mock l10n.lang_dict for cmd_language
        self.l10n = MagicMock(spec=LocalizationService)
        self.l10n.lang_dict = {'en': {'1_lang': 'English'}, 'ru': {'1_lang': 'Russian'}}

    async def __call__(self, handler, event, data):
        data["session"] = self.session
        data["app_context"] = self.app_context
        data["l10n"] = self.l10n
        return await handler(event, data)

@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if common_setting_router.parent_router:
         common_setting_router._parent_router = None

@pytest.fixture
def mock_session():
    session = MagicMock()
    session.commit = AsyncMock()
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
    dp.include_router(common_setting_router)
    return dp

@pytest.mark.asyncio
async def test_cmd_wallet_lang(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test ChangeLang callback -> Show language menu"""
    user_id = 123
    mock_app_context.bot = bot
    
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="ChangeLang"
        )
    ))
    
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) == 1
    assert "Choose language" in sent_messages[0]['data']['text']
    # Verify buttons
    markup = sent_messages[0]['data']['reply_markup']
    assert "English" in markup
    assert "Russian" in markup


@pytest.mark.asyncio
async def test_callbacks_lang(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test lang_en callback -> Set language and show balance"""
    user_id = 123
    mock_app_context.bot = bot
    
    # We need to mock change_user_lang (imported in router)
    # And cmd_show_balance (imported in router) OR let it run.
    # cmd_show_balance is complex, relies on WalletRepo and StellarService.
    # It's better to patch cmd_show_balance to avoid testing it here.
    
    # Configure mock user repo for update_lang
    mock_user_repo = MagicMock(spec=IUserRepository)
    mock_user_repo.update_lang = AsyncMock()
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo

    # For cmd_show_balance (it uses user_repo.get_by_id and get_start_text -> get_wallet_repo)
    mock_user_repo.get_by_id = AsyncMock(return_value=MagicMock(spec=User, lang="en"))
    
    # Mocking cmd_show_balance internal calls (it is complex)
    # Ideally we should let it run if dependencies are mocked.
    # cmd_show_balance calls get_start_text calls create_wallet_secret_service, get_wallet_repository
    
    mock_secret = MagicMock(spec=IWalletSecretService)
    mock_secret.is_ton_wallet = AsyncMock(return_value=False)
    mock_app_context.use_case_factory.create_wallet_secret_service.return_value = mock_secret
    
    mock_wallet_repo = MagicMock(spec=IWalletRepository)
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=MagicMock(spec=Wallet, public_key="GKEY", assets_visibility=None, is_free=False))
    mock_wallet_repo.get_info = AsyncMock(return_value="")
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    # And get_wallet_balance use case
    mock_balance_uc = MagicMock(spec=GetWalletBalance)
    mock_balance_uc.execute = AsyncMock(return_value=[])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    cb_data = LangCallbackData(action="en").pack()
    
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Lang"),
            data=cb_data
        )
    ))
    
    mock_user_repo.update_lang.assert_called_once_with(user_id, "en")
    # cmd_show_balance logic should have run
    
    # Verify answer
    answers = [r for r in mock_telegram if r['method'] == 'answerCallbackQuery']
    assert len(answers) == 1
    assert "was_set" in answers[0]['data']['text'] # Mock gettext


@pytest.mark.asyncio
async def test_cmd_wallet_setting(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test ChangeWallet callback"""
    user_id = 123
    mock_app_context.bot = bot
    
    # cmd_change_wallet calls get_wallet_repository.get_all_active
    mock_wallet_repo = MagicMock(spec=IWalletRepository)
    # Return mock wallets
    w1 = MagicMock(spec=Wallet, id=1, public_key="GKEY1", is_default=True)
    w2 = MagicMock(spec=Wallet, id=2, public_key="GKEY2", is_default=False)
    mock_wallet_repo.get_all_active = AsyncMock(return_value=[w1, w2])
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="ChangeWallet"
        )
    ))
    
    mock_wallet_repo.get_all_active.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_wallet_setting_msg(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test /change_wallet command"""
    user_id = 123
    mock_app_context.bot = bot
    
    # cmd_change_wallet calls get_wallet_repository.get_all_active
    mock_wallet_repo = MagicMock(spec=IWalletRepository)
    mock_wallet_repo.get_all_active = AsyncMock(return_value=[])
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        message=types.Message(
            message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'),
            from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            text="/change_wallet"
        )
    ))
    
    mock_wallet_repo.get_all_active.assert_called_once()
    # Message should be deleted (mock_server doesn't show deleteMessage easily unless we track it)
    deletes = [r for r in mock_telegram if r['method'] == 'deleteMessage']
    assert len(deletes) == 1


@pytest.mark.asyncio
async def test_cq_setting_delete(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test WalletSettingCallbackData DELETE action"""
    user_id = 123
    mock_app_context.bot = bot
    
    # Needs state data with wallets
    # We can patch state.get_data or set it if using real FSM. 
    # Real FSM is used by dp.feed_update.
    # But how to set state data before handler?
    # We can access storage.
    
    storage_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    wallets = {"1": "GWALLET1", "2": "GWALLET2"}
    await dp.storage.set_data(key=storage_key, data={"wallets": wallets})
    
    cb_data = WalletSettingCallbackData(action="DELETE", idx=1).pack()
    
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data=cb_data
        )
    ))
    
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) == 1
    assert "kb_delete" in sent_messages[0]['data']['text']
    assert "GWALLET1" in sent_messages[0]['data']['text']
    assert "YES_DELETE" in sent_messages[0]['data']['reply_markup']


@pytest.mark.asyncio
async def test_cq_setting_set_active(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test WalletSettingCallbackData SET_ACTIVE action"""
    user_id = 123
    mock_app_context.bot = bot
    
    storage_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    wallets = {"1": "GWALLET1"}
    await dp.storage.set_data(key=storage_key, data={"wallets": wallets})
    
    cb_data = WalletSettingCallbackData(action="SET_ACTIVE", idx=1).pack()
    
    # We need to mock SqlAlchemyWalletRepository because it is instantiated inside the handler
    # SET_ACTIVE calls set_default_wallet and then cmd_change_wallet (which calls get_all_active)
    
    mock_wallet_repo = MagicMock(spec=IWalletRepository)
    mock_wallet_repo.set_default_wallet = AsyncMock()
    mock_wallet_repo.get_all_active = AsyncMock(return_value=[])
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data=cb_data
        )
    ))
    
    mock_wallet_repo.set_default_wallet.assert_called_once_with(user_id, "GWALLET1")
    mock_wallet_repo.get_all_active.assert_called_once()


@pytest.mark.asyncio
async def test_cq_setting_name(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test WalletSettingCallbackData NAME action"""
    user_id = 123
    mock_app_context.bot = bot
    
    storage_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    wallets = {"1": "GWALLET1"}
    await dp.storage.set_data(key=storage_key, data={"wallets": wallets})
    
    cb_data = WalletSettingCallbackData(action="NAME", idx=1).pack()
    
    # NAME calls get_info, get_default_wallet, use_case_balance
    
    mock_wallet_repo = MagicMock(spec=IWalletRepository)
    mock_wallet_repo.get_info = AsyncMock(return_value="MyWallet")
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=MagicMock(spec=Wallet, is_free=False, assets_visibility=None))
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    mock_balance_uc = MagicMock(spec=GetWalletBalance)
    from other.mytypes import Balance
    bal = Balance(asset_code="XLM", balance="100.0", selling_liabilities="0.0", asset_issuer="native")
    mock_balance_uc.execute.return_value = [bal]
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

        
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data=cb_data
        )
    ))
    
    answers = [r for r in mock_telegram if r['method'] == 'answerCallbackQuery']
    assert len(answers) >= 1
    # Find the answer with text
    text_answer = next((a for a in answers if 'text' in a['data']), None)
    assert text_answer is not None
    assert "MyWallet" in text_answer['data']['text']
    assert "XLM : 100" in text_answer['data']['text']


@pytest.mark.asyncio
async def test_cmd_yes_delete(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test YES_DELETE callback"""
    user_id = 123
    mock_app_context.bot = bot
    
    storage_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    wallets = {"1": "GWALLET1"}
    await dp.storage.set_data(key=storage_key, data={"wallets": wallets, "idx": "1"})
    
    # YES_DELETE calls repo.delete then repo.get_all_active (via cmd_change_wallet)
    
    mock_wallet_repo = MagicMock(spec=IWalletRepository)
    mock_wallet_repo.delete = AsyncMock()
    mock_wallet_repo.get_all_active = AsyncMock(return_value=[])
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo

    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="YES_DELETE"
        )
    ))
    
    mock_wallet_repo.delete.assert_called_once_with(user_id, "GWALLET1", wallet_id=1)
    mock_wallet_repo.get_all_active.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_support(mock_telegram, bot, dp, mock_session, mock_app_context):
    """Test Support callback"""
    user_id = 123
    mock_app_context.bot = bot
    
    await dp.feed_update(bot=bot, update=types.Update(
        update_id=1,
        callback_query=types.CallbackQuery(
            id="cb", from_user=types.User(id=user_id, is_bot=False, first_name="T", username="t"),
            chat_instance="ci", message=types.Message(message_id=1, date=datetime.datetime.now(), chat=types.Chat(id=user_id, type='private'), text="Menu"),
            data="Support"
        )
    ))
    
    sent_messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(sent_messages) == 1
    assert "support_bot" in sent_messages[0]['data']['text']

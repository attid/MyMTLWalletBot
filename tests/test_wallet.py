
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.add_wallet import cmd_add_new, cmd_sending_private, StateAddWallet, cq_add_new_key
from routers.wallet_setting import cmd_wallet_setting, cmd_manage_assets, handle_asset_visibility_action, AssetVisibilityCallbackData, ASSET_VISIBLE, ASSET_HIDDEN
import routers.add_wallet as add_wallet_module
import routers.wallet_setting as wallet_setting_module

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.mark.asyncio
async def test_cmd_add_new(mock_session):
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.from_user.username = "user"
    callback.data = "AddNew"
    
    with patch("routers.add_wallet.send_message", new_callable=AsyncMock) as mock_send_message, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_add_new(callback, mock_session)
        
        mock_send_message.assert_called_once()
        assert mock_send_message.call_args[1].get('reply_markup') is not None

@pytest.mark.asyncio
async def test_cmd_sending_private_success(mock_session):
    message = AsyncMock()
    message.text = "SSECRETKEY"
    message.chat.id = 123
    message.from_user.id = 123
    message.from_user.username = "user"
    state = AsyncMock(spec=FSMContext)
    
    with patch("routers.add_wallet.stellar_save_new", return_value="GPUBLICKEY") as mock_save, \
         patch("routers.add_wallet.cmd_show_add_wallet_choose_pin", new_callable=AsyncMock) as mock_next, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_sending_private(message, state, mock_session)
        
        mock_save.assert_called_once()
        state.update_data.assert_called_with(public_key="GPUBLICKEY")
        state.set_state.assert_called_with(None)
        mock_next.assert_called_once()

@pytest.mark.asyncio
async def test_wallet_setting_menu(mock_session):
    callback = AsyncMock()
    callback.from_user.id = 123
    state = AsyncMock(spec=FSMContext)
    
    with patch("routers.wallet_setting.stellar_is_free_wallet", return_value=True), \
         patch("routers.wallet_setting.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_wallet_setting(callback, state, mock_session)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_handle_asset_visibility_set(mock_session):
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.message = AsyncMock() 
    
    state = AsyncMock(spec=FSMContext)
    
    callback_data = AssetVisibilityCallbackData(action='set', code='USD', status=2, page=1)
    
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = None 
    
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository") as MockRepo, \
         patch("other.asset_visibility_tools.serialize_visibility", return_value='{"USD": "hidden"}') as mock_serialize, \
         patch("routers.wallet_setting._generate_asset_visibility_markup", return_value=("msg", "kbd")), \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123), \
         patch("sqlalchemy.orm.Session", MagicMock): 
         
         mock_repo_instance = MockRepo.return_value
         mock_repo_instance.get_default_wallet = AsyncMock(return_value=mock_wallet)
         
         mock_gd.user_lang_dic = {123: 'en'}
         mock_gd.lang_dict = {'en': {}}
         
         await handle_asset_visibility_action(callback, callback_data, state, mock_session)
         
         mock_session.commit.assert_called()
         assert mock_wallet.assets_visibility is not None
         assert callback.message.edit_text.called

@pytest.mark.asyncio
async def test_add_wallet_new_key_queue(mock_session):
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.message.chat.id = 123
    callback.from_user.username = "user"
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    
    lock_mock = AsyncMock()
    lock_mock.__aenter__.return_value = None
    lock_mock.__aexit__.return_value = None
    # waiting_count is called synchronously, so it must be MagicMock, not AsyncMock
    lock_mock.waiting_count = MagicMock(return_value=1)
    
    # Patch lock at routers.add_wallet since we are testing cq_add_new_key defined there.
    with patch("routers.add_wallet.db_user_can_new_free", return_value=True), \
         patch("routers.add_wallet.new_wallet_lock", lock_mock) as mock_lock, \
         patch("routers.add_wallet.stellar_create_new", new_callable=AsyncMock, return_value="XDR"), \
         patch("routers.add_wallet.async_stellar_send", new_callable=AsyncMock) as mock_send_xdr, \
         patch("routers.add_wallet.cmd_info_message", new_callable=AsyncMock) as mock_info, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cq_add_new_key(callback, mock_session, state)
        
        # We expect 3 calls: queue wait, try send, send good
        assert mock_info.call_count >= 3
        mock_send_xdr.assert_called_with("XDR")

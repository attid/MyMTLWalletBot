
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
    
    # Mocking Keypair
    mock_kp = MagicMock()
    mock_kp.public_key = "GPUBLICKEY"
    
    # Mocking AddWallet instance
    mock_add_wallet_instance = AsyncMock()
    
    with patch("routers.add_wallet.Keypair") as MockKeypair, \
         patch("routers.add_wallet.SqlAlchemyWalletRepository") as MockRepo, \
         patch("routers.add_wallet.AddWallet") as MockAddWallet, \
         patch("routers.add_wallet.encrypt", return_value="ENCRYPTED"), \
         patch("routers.add_wallet.cmd_show_add_wallet_choose_pin", new_callable=AsyncMock) as mock_next, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        MockKeypair.from_secret.return_value = mock_kp
        MockAddWallet.return_value = mock_add_wallet_instance
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_sending_private(message, state, mock_session)
        
        mock_add_wallet_instance.execute.assert_called_once_with(
            user_id=123,
            public_key="GPUBLICKEY",
            secret_key="ENCRYPTED",
            is_free=False,
            is_default=False
        )
        state.update_data.assert_called_with(public_key="GPUBLICKEY")
        state.set_state.assert_called_with(None)
        mock_next.assert_called_once()

# ... (skipped wallet_setting tests)

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
    lock_mock.waiting_count = MagicMock(return_value=1)
    
    mock_add_wallet = AsyncMock()
    mock_service = MagicMock() # StellarService is instantiated
    mock_service_instance = AsyncMock()
    mock_service.return_value = mock_service_instance
    
    mock_kp = MagicMock()
    mock_kp.public_key = "GNEWKEY"
    mock_kp.secret = "SNEWKEY"

    mock_master_wallet = MagicMock()
    mock_master_wallet.public_key = "GMASTER"
    mock_master_wallet.secret_key = "ENCRYPTED_MASTER"
    
    mock_repo_instance = MagicMock()
    mock_repo_instance.count_free_wallets = AsyncMock(return_value=1)
    mock_repo_instance.get_default_wallet = AsyncMock(return_value=mock_master_wallet)

    with patch("routers.add_wallet.SqlAlchemyWalletRepository", return_value=mock_repo_instance), \
         patch("routers.add_wallet.AddWallet", return_value=mock_add_wallet), \
         patch("routers.add_wallet.new_wallet_lock", lock_mock) as mock_lock, \
         patch("routers.add_wallet.Keypair") as MockKeypair, \
         patch("routers.add_wallet.encrypt", return_value="ENCRYPTED"), \
         patch("routers.add_wallet.decrypt", return_value="MASTER_SECRET"), \
         patch("routers.add_wallet.StellarService", mock_service), \
         patch("routers.add_wallet.config"), \
         patch("routers.add_wallet.cmd_info_message", new_callable=AsyncMock) as mock_info, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        MockKeypair.generate_mnemonic_phrase.return_value = "mnemonic"
        MockKeypair.from_mnemonic_phrase.return_value = mock_kp
        
        mock_service_instance.build_payment_transaction.return_value = "XDR_PAY"
        mock_service_instance.sign_transaction.return_value = "SIGNED_XDR"
        mock_service_instance.build_change_trust_transaction.return_value = "XDR_TRUST"
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cq_add_new_key(callback, mock_session, state)
        
        # We expect 3 calls: queue wait, try send, send good
        assert mock_info.call_count >= 3
        mock_add_wallet.execute.assert_called_once()
        mock_service_instance.submit_transaction.assert_called()

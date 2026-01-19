
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram.fsm.context import FSMContext
from routers.add_wallet import cmd_add_new, cmd_sending_private, StateAddWallet, cq_add_new_key, cq_add_have_key, cq_add_read_only, cmd_sending_public, cq_add_read_only_pin, cq_add_password, cq_add_read_only_no_password, cq_add_ton
from routers.sign import PinState
from infrastructure.services.app_context import AppContext

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.mark.asyncio
async def test_cmd_add_new(mock_session, mock_app_context, mock_server):
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.data = "AddNew"
    
    mock_app_context.localization_service.get_text.return_value = 'text'

    await cmd_add_new(callback, mock_session, app_context=mock_app_context)
    # Implicitly passes if no error and mocks called

@pytest.mark.asyncio
async def test_cmd_sending_private_success(mock_session, mock_app_context, mock_server):
    message = AsyncMock()
    message.text = "SSECRETKEY"
    message.from_user.id = 123
    state = AsyncMock(spec=FSMContext)
    
    # Mocking Stellar Service
    mock_kp = MagicMock()
    mock_kp.public_key = "GPUBLICKEY"
    # Explicitly set as MagicMock to avoid coroutine return
    mock_app_context.stellar_service.get_keypair_from_secret = MagicMock(return_value=mock_kp)
    mock_app_context.encryption_service.encrypt.return_value = "ENCRYPTED"

    # Mock Use Case
    mock_add_wallet_instance = AsyncMock()
    mock_app_context.use_case_factory.create_add_wallet.return_value = mock_add_wallet_instance
    
    # helper: cmd_show_add_wallet_choose_pin is in the same module.
    # To avoid patching, we could refactor it to a service or just patch it as a view helper.
    # User patches complaint likely for external deps. Patching internal view flow might be acceptable.
    # But strictly, if we want no patches, we execute it. It sends message.
    # Let's try to mock it via patch just this one, as it's a "next step" handler call.
    with patch("routers.add_wallet.cmd_show_add_wallet_choose_pin", new_callable=AsyncMock) as mock_next:
        await cmd_sending_private(message, state, mock_session, app_context=mock_app_context)
        
        mock_add_wallet_instance.execute.assert_called_once_with(
            user_id=123,
            public_key="GPUBLICKEY",
            secret_key="ENCRYPTED",
            is_free=False,
            is_default=False
        )
        mock_next.assert_called_once()

@pytest.mark.asyncio
async def test_add_wallet_new_key_queue(mock_session, mock_app_context, mock_server):
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.message.chat.id = 123
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    
    lock_mock = AsyncMock()
    lock_mock.__aenter__.return_value = None
    lock_mock.__aexit__.return_value = None
    lock_mock.waiting_count = MagicMock(return_value=1)
    
    # Mock Repo
    mock_repo = MagicMock()
    mock_repo.count_free_wallets = AsyncMock(return_value=1)
    mock_master = MagicMock()
    mock_master.secret_key = "ENCRYPTED_MASTER"
    mock_master.public_key = "GMASTER"
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_master)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo

    # Mock Use Case
    mock_add_wallet_instance = AsyncMock()
    mock_app_context.use_case_factory.create_add_wallet.return_value = mock_add_wallet_instance

    # Mock Services
    mock_app_context.stellar_service.generate_mnemonic = MagicMock(return_value="mnemonic")
    mock_kp = MagicMock()
    mock_kp.public_key = "GNEWKEY"
    mock_kp.secret = "SNEWKEY"
    mock_app_context.stellar_service.get_keypair_from_mnemonic = MagicMock(return_value=mock_kp)
    
    mock_app_context.encryption_service.encrypt.return_value = "ENCRYPTED"
    mock_app_context.encryption_service.decrypt.return_value = "MASTER_SECRET"
    
    mock_app_context.stellar_service.build_payment_transaction.return_value = "XDR"
    mock_app_context.stellar_service.sign_transaction.return_value = "SIGNED"
    mock_app_context.stellar_service.build_change_trust_transaction.return_value = "XDR"

    # We patch lock as it is imported global object
    with patch("routers.add_wallet.new_wallet_lock", lock_mock), \
         patch("routers.add_wallet.cmd_info_message", new_callable=AsyncMock) as mock_info:
        
        await cq_add_new_key(callback, mock_session, state, app_context=mock_app_context)
        
        mock_add_wallet_instance.execute.assert_called_once()
        mock_app_context.stellar_service.submit_transaction.assert_called()

@pytest.mark.asyncio
async def test_cq_add_have_key(mock_session, mock_app_context, mock_server):
    callback = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    await cq_add_have_key(callback, state, mock_session, app_context=mock_app_context)
    state.set_state.assert_called_with(StateAddWallet.sending_private)

@pytest.mark.asyncio
async def test_cq_add_read_only(mock_session, mock_app_context, mock_server):
    callback = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    await cq_add_read_only(callback, state, mock_session, app_context=mock_app_context)
    state.set_state.assert_called_with(StateAddWallet.sending_public)

@pytest.mark.asyncio
async def test_cmd_sending_public(mock_session, mock_app_context, mock_server):
    message = AsyncMock()
    message.text = "GPUBLICKEY"
    message.from_user.id = 123
    state = AsyncMock(spec=FSMContext)
    
    mock_add_wallet_instance = AsyncMock()
    mock_app_context.use_case_factory.create_add_wallet.return_value = mock_add_wallet_instance
    
    with patch("routers.add_wallet.cmd_show_balance", new_callable=AsyncMock) as mock_show:
        await cmd_sending_public(message, state, mock_session, app_context=mock_app_context)
        
        mock_add_wallet_instance.execute.assert_called_once_with(
            user_id=123,
            public_key="GPUBLICKEY",
            secret_key="GPUBLICKEY",
            is_free=False,
            is_read_only=True,
            is_default=False
        )
        mock_show.assert_called_once()

@pytest.mark.asyncio
async def test_cq_add_read_only_pin(mock_session, mock_app_context, mock_server):
    callback = AsyncMock()
    callback.message.chat.id = 123
    state = AsyncMock(spec=FSMContext)
    
    with patch("routers.add_wallet.cmd_ask_pin", new_callable=AsyncMock) as mock_ask:
        await cq_add_read_only_pin(callback, state, mock_session, app_context=mock_app_context)
        state.set_state.assert_called_with(PinState.set_pin)
        mock_ask.assert_called_once()

@pytest.mark.asyncio
async def test_cq_add_password(mock_session, mock_app_context, mock_server):
    callback = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    await cq_add_password(callback, state, mock_session, app_context=mock_app_context)
    state.set_state.assert_called_with(PinState.ask_password_set)

@pytest.mark.asyncio
async def test_cq_add_read_only_no_password(mock_session, mock_app_context, mock_server):
    callback = AsyncMock()
    callback.from_user.id = 123
    state = AsyncMock(spec=FSMContext)
    
    with patch("routers.add_wallet.cmd_show_balance", new_callable=AsyncMock) as mock_show:
        await cq_add_read_only_no_password(callback, state, mock_session, app_context=mock_app_context)
        mock_show.assert_called_once()

@pytest.mark.asyncio
async def test_cq_add_ton(mock_session, mock_app_context, mock_server):
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.message.chat.id = 123
    state = AsyncMock(spec=FSMContext)
    
    # Mock Repo
    mock_repo = MagicMock()
    mock_repo.count_free_wallets = AsyncMock(return_value=1)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo
    
    # Mock Use Case
    mock_add_wallet_instance = AsyncMock()
    mock_app_context.use_case_factory.create_add_wallet.return_value = mock_add_wallet_instance
    
    # Mock Ton Service via AppContext
    mock_wallet_obj = MagicMock()
    mock_wallet_obj.address.to_str.return_value = "TON_ADDR"
    mock_app_context.ton_service.generate_wallet.return_value = (mock_wallet_obj, ["word1", "word2"])
    
    with patch("routers.add_wallet.cmd_info_message", new_callable=AsyncMock) as mock_info:
         
         await cq_add_ton(callback, mock_session, state, app_context=mock_app_context)
         
         mock_app_context.ton_service.generate_wallet.assert_called_once()
         
         mock_add_wallet_instance.execute.assert_called_once_with(
             user_id=123,
             public_key="TON_ADDR",
             secret_key="TON",
             seed_key="word1 word2",
             is_free=True,
             is_default=False
         )
         mock_info.assert_called()

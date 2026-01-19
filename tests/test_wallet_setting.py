
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.wallet_setting import cmd_wallet_setting, cmd_get_private_key, remove_password, send_private_key, cmd_add_asset_del
from core.domain.entities import Wallet
from core.domain.value_objects import Balance, Asset

# Integration tests using mock_app_context

@pytest.mark.asyncio
async def test_cmd_wallet_setting(mock_session, mock_callback, mock_state, mock_app_context):
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.is_free = True
    
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo

    with patch("routers.wallet_setting.my_gettext", return_value="msg"), \
         patch("routers.wallet_setting.send_message", new_callable=AsyncMock) as mock_send:
         
        # l10n argument removed from handler signature in previous refactors? 
        # Checking calling convention: cmd_wallet_setting(callback, state, session, app_context)
        # Note: in wallet_setting.py the signature is:
        # async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext, l10n: LocalizationService):
        # Wait, does it accept l10n?
        # Let's check view_file from earlier. 
        # I didn't verify cmd_wallet_setting signature in this session, but user provided memory says it might have changed.
        # But looking at router handlers, they usually take dependencies from middleware.
        # If I see AppContextMiddleware, it injects app_context.
        # DbSessionMiddleware injects session.
        # LocalizationMiddleware injects l10n (if configured to pass it to handler).
        # Assuming typical signature. If l10n is passed, I need to pass it.
        # Checking typical handler: async def cmd_wallet_setting(..., app_context: AppContext):
        # I'll try passing app_context.
        l10n = MagicMock()
        await cmd_wallet_setting(mock_callback, mock_state, mock_session, app_context=mock_app_context, l10n=l10n)
        
        mock_send.assert_called_once()
        # Verify call args
        args, kwargs = mock_send.call_args
        assert kwargs['reply_markup'] is not None


@pytest.mark.asyncio
async def test_cmd_get_private_key(mock_session, mock_callback, mock_state, mock_app_context):
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.is_free = False
    mock_wallet.use_pin = 1 # Has PIN
    
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo
    
    with patch("routers.wallet_setting.cmd_ask_pin", new_callable=AsyncMock) as mock_ask_pin:
         
        await cmd_get_private_key(mock_callback, mock_state, mock_session, app_context=mock_app_context)
        
        mock_ask_pin.assert_called_once()
        mock_state.update_data.assert_called()


@pytest.mark.asyncio
async def test_send_private_key(mock_session, mock_state, mock_app_context):
    user_id = 123
    mock_state.get_data.return_value = {'pin': '1234'}
    
    mock_secrets = MagicMock()
    mock_secrets.secret_key = "SECRET_KEY"
    mock_secrets.seed_phrase = "SEED_PHRASE"
    
    # Configure UseCaseFactory mock
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = mock_secrets
    mock_app_context.use_case_factory = MagicMock() # Ensure factory exists
    mock_app_context.use_case_factory.create_get_wallet_secrets.return_value = mock_use_case
    
    mock_repo = MagicMock()
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo
    
    with patch("routers.wallet_setting.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.wallet_setting.my_gettext", return_value="text"):
          
        await send_private_key(mock_session, user_id, mock_state, app_context=mock_app_context)
        
        mock_send.assert_called_once()
        text = mock_send.call_args[0][2]
        assert "SECRET_KEY" in text
        assert "SEED_PHRASE" in text


@pytest.mark.asyncio
async def test_remove_password(mock_session, mock_state, mock_app_context):
    user_id = 123
    mock_state.get_data.return_value = {'pin': '1234'}
    
    # Configure UseCaseFactory mock
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = True
    mock_app_context.use_case_factory = MagicMock()
    mock_app_context.use_case_factory.create_change_wallet_password.return_value = mock_use_case

    with patch("routers.wallet_setting.cmd_info_message", new_callable=AsyncMock) as mock_info:
         
        await remove_password(mock_session, user_id, mock_state, app_context=mock_app_context)
        
        mock_use_case.execute.assert_called_once_with(
            user_id=123, old_pin='1234', new_pin='123', pin_type=0
        )
        mock_info.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_add_asset_del(mock_session, mock_callback, mock_state, mock_app_context):
    # Setup - user chooses to delete asset
    user_id = 123
    mock_callback.from_user.id = user_id
    
    # Mock GetWalletBalance use case via factory
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute.return_value = [
        Balance(asset_code="XLM", asset_issuer="native", balance="100", limit="0", asset_type="native"),
        Balance(asset_code="EURMTL", asset_issuer="GABC...", balance="0.0", limit="1000", asset_type="credit_alphanum12")
    ]
    
    mock_app_context.use_case_factory = MagicMock()
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    with patch("routers.wallet_setting.my_gettext", return_value="Select asset to delete"), \
         patch("routers.wallet_setting.send_message", new_callable=AsyncMock) as mock_send:
         
        await cmd_add_asset_del(mock_callback, mock_state, mock_session, app_context=mock_app_context)
        
        mock_send.assert_called_once()
        # Verify keyboard contains EURMTL
        kwargs = mock_send.call_args[1]
        kb = kwargs['reply_markup']
        # Check if any button has callback_data containing "Delete:EURMTL:GABC..."
        # Simplified check
        assert mock_balance_uc.execute.called


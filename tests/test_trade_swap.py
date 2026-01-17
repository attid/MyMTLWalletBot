
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.trade import cmd_market, cmd_sale_new_order, cq_trade_choose_token_sell, cq_trade_choose_token_buy, StateSaleToken, SaleAssetCallbackData, BuyAssetCallbackData, cmd_send_sale_sum, cmd_send_sale_cost, cmd_show_orders, cb_edit_order, EditOrderCallbackData, cmd_delete_order, cmd_edit_sale_sum, cmd_edit_sale_cost
from routers.swap import cmd_swap_01, cq_swap_choose_token_from, SwapAssetFromCallbackData, cq_swap_choose_token_for, SwapAssetForCallbackData, cmd_swap_sum, StateSwapToken, cq_swap_strict_receive, cmd_swap_receive_sum
from stellar_sdk import Asset
import jsonpickle

# --- tests for routers/trade.py ---

@pytest.mark.asyncio
async def test_cmd_market(mock_session, mock_callback):
    with patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_market(mock_callback, mock_session)
        mock_send.assert_called_once()
        mock_callback.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_sale_new_order(mock_session, mock_callback, mock_state):
    balance = MagicMock()
    balance.asset_code = "XLM"
    balance.balance = "100.0"
    
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"
    
    with patch("routers.trade.have_free_xlm", return_value=True), \
         patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository") as MockRepo, \
         patch("infrastructure.services.stellar_service.StellarService"), \
         patch("core.use_cases.wallet.get_balance.GetWalletBalance") as MockUseCase, \
         patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send:

        # Setup mock repository
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_default_wallet = AsyncMock(return_value=mock_wallet)
        
        # Setup mock use case
        mock_use_case_instance = MockUseCase.return_value
        mock_use_case_instance.execute = AsyncMock(return_value=[balance])

        await cmd_sale_new_order(mock_callback, mock_state, mock_session)
        
        mock_send.assert_called_once()
        args, kwargs = mock_state.update_data.call_args
        assert "assets" in kwargs

@pytest.mark.asyncio
async def test_cq_trade_choose_token_sell(mock_session, mock_callback, mock_state):
    asset_data = [
        MagicMock(asset_code="XLM", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA", balance="100.0"),
        MagicMock(asset_code="USD", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA", balance="10.0")
    ]
    mock_state.get_data.return_value = {"assets": "encoded_assets"}
    callback_data = SaleAssetCallbackData(answer="USD")
    
    with patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.trade.jsonpickle.decode", return_value=asset_data):
        
        await cq_trade_choose_token_sell(mock_callback, callback_data, mock_state, mock_session)
        
        mock_state.update_data.assert_called()
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cq_trade_choose_token_buy(mock_session, mock_callback, mock_state):
    asset_data = [MagicMock(asset_code="EUR", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA", balance="50.0")]
    mock_state.get_data.return_value = {
        "assets": "encoded_assets",
        "send_asset_code": "USD",
        "send_asset_issuer": "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA",
        "send_asset_max_sum": 10.0
    }
    callback_data = BuyAssetCallbackData(answer="EUR")
    
    with patch("routers.trade.stellar_get_market_link", return_value="link"), \
         patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.trade.jsonpickle.decode", return_value=asset_data):
        
        await cq_trade_choose_token_buy(mock_callback, callback_data, mock_state, mock_session)
        
        mock_state.set_state.assert_called_with(StateSaleToken.selling_sum)
        mock_send.assert_called_once()

# --- tests for routers/swap.py ---

@pytest.mark.asyncio
async def test_cmd_swap_01(mock_session, mock_callback, mock_state):
    balance = MagicMock()
    balance.asset_code = "XLM"
    balance.balance = "100.0"
    
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"
    
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository") as MockRepo, \
         patch("infrastructure.services.stellar_service.StellarService"), \
         patch("core.use_cases.wallet.get_balance.GetWalletBalance") as MockUseCase, \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:
        
        # Setup mock repository
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_default_wallet = AsyncMock(return_value=mock_wallet)
        
        # Setup mock use case
        mock_use_case_instance = MockUseCase.return_value
        mock_use_case_instance.execute = AsyncMock(return_value=[balance])
        
        await cmd_swap_01(mock_callback, mock_state, mock_session)
        
        mock_send.assert_called_once()
        args, kwargs = mock_state.update_data.call_args
        assert "assets" in kwargs

@pytest.mark.asyncio
async def test_cq_swap_choose_token_from(mock_session, mock_callback, mock_state):
    asset_data = [MagicMock(asset_code="USD", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA", balance="10.0")]
    mock_state.get_data.return_value = {"assets": "encoded_assets"}
    callback_data = SwapAssetFromCallbackData(answer="USD")
    
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"
    
    with patch("routers.swap.stellar_get_selling_offers_sum", return_value=0, new_callable=AsyncMock), \
         patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository") as MockRepo, \
         patch("infrastructure.services.stellar_service.StellarService"), \
         patch("core.use_cases.wallet.get_balance.GetWalletBalance") as MockUseCase, \
         patch("routers.swap.stellar_check_receive_asset", return_value=["EUR"], new_callable=AsyncMock), \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.swap.jsonpickle.decode", return_value=asset_data):
         
        # Setup mock repository
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_default_wallet = AsyncMock(return_value=mock_wallet)
        
        # Setup mock use case
        mock_use_case_instance = MockUseCase.return_value
        mock_use_case_instance.execute = AsyncMock(return_value=asset_data)
         
        await cq_swap_choose_token_from(mock_callback, callback_data, mock_state, mock_session)
        
        mock_state.update_data.assert_called()
        mock_send.assert_called_once()

# --- NEW TESTS FOR TRADE ROUTER ---

@pytest.mark.asyncio
async def test_cmd_send_sale_sum(mock_session, mock_message, mock_state):
    mock_message.text = "10.0"
    mock_state.get_data.return_value = {
        "receive_asset_code": "USD",
        "send_asset_code": "XLM",
        "market_link": "link",
        "msg": "msg"
    }
    
    with patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send:
         await cmd_send_sale_sum(mock_message, mock_state, mock_session)
         mock_state.update_data.assert_called()
         mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_sale_cost(mock_session, mock_message, mock_state):
    mock_message.text = "10.0" # receive total sum
    
    with patch("routers.trade.cmd_xdr_order", new_callable=AsyncMock) as mock_xdr:
        await cmd_send_sale_cost(mock_message, mock_state, mock_session)
        
        mock_state.update_data.assert_called_with(receive_sum=10.0, msg=None)
        mock_xdr.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_show_orders(mock_session, mock_callback, mock_state):
    mock_offers = [MagicMock(id=1, amount="10", price="0.5", selling=MagicMock(asset_code="XLM"), buying=MagicMock(asset_code="USD"))]
    
    with patch("routers.trade.stellar_get_offers", return_value=mock_offers, new_callable=AsyncMock), \
         patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send:
         
         await cmd_show_orders(mock_callback, mock_state, mock_session)
         
         mock_send.assert_called_once()
         args, kwargs = mock_state.update_data.call_args
         assert "offers" in kwargs


@pytest.mark.asyncio
async def test_cb_edit_order(mock_session, mock_callback, mock_state):
    callback_data = EditOrderCallbackData(answer=1)
    offer = MagicMock(id=1, amount="10", price="0.5", selling=MagicMock(asset_code="XLM"), buying=MagicMock(asset_code="USD"))
    
    mock_state.get_data.return_value = {"offers": jsonpickle.encode([offer])}
    
    # Ensure jsonpickle.decode returns a list
    with patch("routers.trade.jsonpickle.decode", return_value=[offer]), \
         patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send:

        await cb_edit_order(mock_callback, callback_data, mock_state, mock_session)
        mock_state.update_data.assert_called()
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_delete_order(mock_session, mock_callback, mock_state):
    offer = MagicMock(id=1, amount="10", price="0.5", selling=MagicMock(asset_code="XLM", asset_issuer=None), buying=MagicMock(asset_code="USD", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"))
    mock_state.get_data.return_value = {"edit_offer_id": 1, "offers": jsonpickle.encode([offer])}

    with patch("routers.trade.jsonpickle.decode", return_value=[offer]), \
         patch("routers.trade.cmd_xdr_order", new_callable=AsyncMock) as mock_xdr:
        await cmd_delete_order(mock_callback, mock_state, mock_session)
        
        args, kwargs = mock_state.update_data.call_args
        assert kwargs.get('delete_order') is True
        mock_xdr.assert_called_once()

# --- NEW TESTS FOR SWAP ROUTER ---

@pytest.mark.asyncio
async def test_cq_swap_choose_token_for(mock_session, mock_callback, mock_state):
    callback_data = SwapAssetForCallbackData(answer="USD")
    valid_issuer = "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"
    mock_asset = MagicMock(asset_code="USD", asset_issuer=valid_issuer, balance="100.0")
    
    mock_state.get_data.return_value = {
        "assets": "encoded", 
        "send_asset_blocked_sum": 0, 
        "send_asset_code": "XLM", 
        "send_asset_issuer": None,
        "receive_asset_code": "USD",
        "receive_asset_issuer": valid_issuer
    }
    
    with patch("routers.swap.jsonpickle.decode", return_value=[mock_asset]), \
         patch("routers.swap.stellar_get_market_link", return_value="link"), \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:

         await cq_swap_choose_token_for(mock_callback, callback_data, mock_state, mock_session)
         
         mock_state.set_state.assert_called_with(StateSwapToken.swap_sum)
         mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_swap_sum(mock_session, mock_message, mock_state):
    mock_message.text = "10.0"
    mock_state.get_data.return_value = {
        "send_asset_code": "XLM", "send_asset_issuer": None, # Native
        "receive_asset_code": "USD", "receive_asset_issuer": "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA",
        "cancel_offers": False, "xdr": None,
        "msg": "msg"
    }
    
    mock_user = MagicMock(can_5000=1)
    
    with patch("infrastructure.persistence.sqlalchemy_user_repository.SqlAlchemyUserRepository") as MockUserRepo, \
         patch("routers.swap.stellar_get_user_account", new_callable=AsyncMock), \
         patch("routers.swap.stellar_check_receive_sum", return_value=("9.5", False), new_callable=AsyncMock), \
         patch("core.use_cases.trade.swap_assets.SwapAssets") as MockSwapAssets, \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:
         
         mock_user_repo = MockUserRepo.return_value
         mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
         mock_use_case = MockSwapAssets.return_value
         mock_use_case.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR_SWAP"))
         
         await cmd_swap_sum(mock_message, mock_state, mock_session)
         
         mock_state.update_data.assert_called()
         mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cq_swap_strict_receive(mock_session, mock_callback, mock_state):
    mock_state.get_data.return_value = {"receive_asset_code": "USD"}
    
    with patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:

         await cq_swap_strict_receive(mock_callback, mock_state, mock_session)
         
         mock_state.set_state.assert_called_with(StateSwapToken.swap_receive_sum)
         mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_swap_receive_sum(mock_session, mock_message, mock_state):
    mock_message.text = "10.0"
    mock_state.get_data.return_value = {
        "send_asset_code": "XLM", "send_asset_issuer": None,
        "receive_asset_code": "USD", "receive_asset_issuer": "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA",
        "cancel_offers": False,
        "msg": "msg"
    }
    
    mock_user = MagicMock(can_5000=1)
    
    with patch("infrastructure.persistence.sqlalchemy_user_repository.SqlAlchemyUserRepository") as MockUserRepo, \
         patch("routers.swap.stellar_get_user_account", new_callable=AsyncMock), \
         patch("routers.swap.stellar_check_send_sum", return_value=("11.0", False), new_callable=AsyncMock), \
         patch("core.use_cases.trade.swap_assets.SwapAssets") as MockSwapAssets, \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:
         
         mock_user_repo = MockUserRepo.return_value
         mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
         mock_use_case = MockSwapAssets.return_value
         mock_use_case.execute = AsyncMock(return_value=MagicMock(success=True, xdr="XDR_SWAP_STRICT"))
         
         await cmd_swap_receive_sum(mock_message, mock_state, mock_session)
         
         _, kwargs = mock_use_case.execute.call_args
         assert kwargs.get('strict_receive') is True
         
         mock_state.update_data.assert_called()
         mock_send.assert_called_once()


import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.trade import cmd_market, cmd_sale_new_order, cq_trade_choose_token_sell, cq_trade_choose_token_buy, StateSaleToken, SaleAssetCallbackData, BuyAssetCallbackData, cmd_send_sale_sum, cmd_send_sale_cost, cmd_show_orders, cb_edit_order, EditOrderCallbackData, cmd_delete_order, cmd_edit_sale_sum, cmd_edit_sale_cost, cmd_edit_order_amount, cmd_edit_order_price
from routers.swap import cmd_swap_01, cq_swap_choose_token_from, SwapAssetFromCallbackData, cq_swap_choose_token_for, SwapAssetForCallbackData, cmd_swap_sum, StateSwapToken, cq_swap_strict_receive, cmd_swap_receive_sum
from stellar_sdk import Asset
import jsonpickle

# --- tests for routers/trade.py ---

@pytest.mark.asyncio
async def test_cmd_market(mock_session, mock_callback):
    with patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send:
        mock_app_context = MagicMock()
        mock_app_context.localization_service.get_text.return_value = "text"
        await cmd_market(mock_callback, mock_session, app_context=mock_app_context)
        mock_send.assert_called_once()
        mock_callback.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_sale_new_order(mock_session, mock_callback, mock_state):
    balance = MagicMock()
    balance.asset_code = "XLM"
    balance.balance = "100.0"
    
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"
    
    # Setup mock app_context factories
    mock_app_context = MagicMock()
    mock_app_context.repository_factory.get_wallet_repository.return_value.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value.execute = AsyncMock(return_value=[balance])
    mock_app_context.localization_service.get_text.return_value = "text"
    
    with patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_sale_new_order(mock_callback, mock_state, mock_session, app_context=mock_app_context)
        
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
        
        mock_app_context = MagicMock()
        mock_app_context.localization_service.get_text.return_value = "text"
        await cq_trade_choose_token_sell(mock_callback, callback_data, mock_state, mock_session, app_context=mock_app_context)
        
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
        
        mock_app_context = MagicMock()
        mock_app_context.localization_service.get_text.return_value = "text"
        await cq_trade_choose_token_buy(mock_callback, callback_data, mock_state, mock_session, app_context=mock_app_context)
        
        mock_state.set_state.assert_called_with(StateSaleToken.selling_sum)
        mock_send.assert_called_once()

# --- tests for routers/swap.py ---

@pytest.mark.asyncio
async def test_cmd_swap_01(mock_session, mock_callback, mock_state):
    """Test cmd_swap_01 using DI-based mocking (no patches for repositories/services)."""
    balance = MagicMock()
    balance.asset_code = "XLM"
    balance.balance = "100.0"
    
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"
    
    # Setup mock_app_context with DI
    mock_app_context = MagicMock()
    mock_app_context.localization_service.get_text.return_value = "text"
    
    # Mock repository_factory
    mock_wallet_repo = AsyncMock()
    mock_wallet_repo.get_default_wallet.return_value = mock_wallet
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    # Mock use_case_factory
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = [balance]
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_use_case
    
    # Only patch send_message (Telegram API - external)
    with patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_swap_01(mock_callback, mock_state, mock_session, app_context=mock_app_context)
        
        mock_send.assert_called_once()
        args, kwargs = mock_state.update_data.call_args
        assert "assets" in kwargs

@pytest.mark.asyncio
async def test_cq_swap_choose_token_from(mock_session, mock_callback, mock_state):
    """Test cq_swap_choose_token_from using DI-based mocking."""
    asset_data = [MagicMock(asset_code="USD", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA", balance="10.0")]
    mock_state.get_data.return_value = {"assets": "encoded_assets"}
    callback_data = SwapAssetFromCallbackData(answer="USD")
    
    mock_wallet = MagicMock()
    mock_wallet.assets_visibility = "{}"
    mock_wallet.public_key = "GCPUBLIC"
    
    # Setup mock_app_context with DI
    mock_app_context = MagicMock()
    mock_app_context.localization_service.get_text.return_value = "text"
    
    # Mock repository_factory
    mock_wallet_repo = AsyncMock()
    mock_wallet_repo.get_default_wallet.return_value = mock_wallet
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    # Mock stellar_service (external network call)
    mock_app_context.stellar_service = AsyncMock()
    mock_app_context.stellar_service.get_selling_offers.return_value = []
    
    # Mock use_case_factory
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = asset_data
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_use_case
    
    # Only patch external functions and Telegram send_message
    with patch("routers.swap.stellar_check_receive_asset", return_value=["EUR"], new_callable=AsyncMock), \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.swap.jsonpickle.decode", return_value=asset_data):
        
        await cq_swap_choose_token_from(mock_callback, callback_data, mock_state, mock_session, app_context=mock_app_context)
        
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
         mock_app_context = MagicMock()
         mock_app_context.localization_service.get_text.return_value = "text"
         await cmd_send_sale_sum(mock_message, mock_state, mock_session, app_context=mock_app_context)
         mock_state.update_data.assert_called()
         mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_send_sale_cost(mock_session, mock_message, mock_state):
    mock_message.text = "10.0" # receive total sum
    
    with patch("routers.trade.cmd_xdr_order", new_callable=AsyncMock) as mock_xdr:
        mock_app_context = MagicMock()
        mock_app_context.localization_service.get_text.return_value = "text"
        await cmd_send_sale_cost(mock_message, mock_state, mock_session, app_context=mock_app_context)
        
        mock_state.update_data.assert_called_with(receive_sum=10.0, msg=None)
        mock_xdr.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_show_orders(mock_session, mock_callback, mock_state):
    mock_offers = [MagicMock(id=1, amount="10", price="0.5", selling=MagicMock(asset_code="XLM"), buying=MagicMock(asset_code="USD"))]
    
    mock_app_context = MagicMock()
    mock_app_context.repository_factory.get_wallet_repository.return_value.get_default_wallet = AsyncMock(return_value=MagicMock(public_key="PK"))
    
    # Mock stellar service
    mock_app_context.stellar_service.get_selling_offers = AsyncMock(return_value=[{
        'id': '1', 'amount': '10', 'price': '0.5', 
        'selling': {'asset_code': 'XLM', 'asset_issuer': None, 'asset_type': 'native'}, 
        'buying': {'asset_code': 'USD', 'asset_issuer': 'ISSUER', 'asset_type': 'credit_alphanum4'}
    }])
    mock_app_context.localization_service.get_text.return_value = "text"
    
    with patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send:
         await cmd_show_orders(mock_callback, mock_state, mock_session, app_context=mock_app_context)
         
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

        mock_app_context = MagicMock()
        mock_app_context.localization_service.get_text.return_value = "text"
        await cb_edit_order(mock_callback, callback_data, mock_state, mock_session, app_context=mock_app_context)
        mock_state.update_data.assert_called()
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_delete_order(mock_session, mock_callback, mock_state):
    offer = MagicMock(id=1, amount="10", price="0.5", selling=MagicMock(asset_code="XLM", asset_issuer=None), buying=MagicMock(asset_code="USD", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"))
    mock_state.get_data.return_value = {"edit_offer_id": 1, "offers": jsonpickle.encode([offer])}

    with patch("routers.trade.jsonpickle.decode", return_value=[offer]), \
         patch("routers.trade.cmd_xdr_order", new_callable=AsyncMock) as mock_xdr:
        mock_app_context = MagicMock()
        mock_app_context.localization_service.get_text.return_value = "text"
        await cmd_delete_order(mock_callback, mock_state, mock_session, app_context=mock_app_context)
        
        args, kwargs = mock_state.update_data.call_args
        assert kwargs.get('delete_order') is True
        mock_xdr.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_edit_order_amount(mock_session, mock_callback, mock_state):
    valid_issuer = "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"
    data = {
        "offers": jsonpickle.encode([MagicMock(id=1, amount="10.0", price="0.5", selling=MagicMock(asset_code="XLM", asset_issuer=None), buying=MagicMock(asset_code="USD", asset_issuer=valid_issuer))]), 
        "edit_offer_id": 1, 
        "send_asset_code": "XLM", "send_asset_issuer": None,
        "receive_asset_code": "USD", "receive_asset_issuer": valid_issuer
    }
    mock_state.get_data.return_value = data
    
    mock_app_context = MagicMock()
    mock_balance = MagicMock(asset_code="XLM", balance="100.0")
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value.execute = AsyncMock(return_value=[mock_balance])
    mock_app_context.localization_service.get_text.return_value = "text"
    
    with patch("routers.trade.jsonpickle.decode", return_value=[MagicMock(id=1, amount="10.0", price="0.5", selling=MagicMock(asset_code="XLM"), buying=MagicMock(asset_code="USD", asset_issuer=valid_issuer))]), \
         patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.trade.stellar_get_market_link", return_value="link"):
         
        await cmd_edit_order_amount(mock_callback, mock_state, mock_session, app_context=mock_app_context)
        
        mock_state.set_state.assert_called_with(StateSaleToken.editing_amount)
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_edit_sale_sum(mock_session, mock_message, mock_state):
    mock_message.text = "20.0"
    mock_state.get_data.return_value = {"receive_sum": "5.0", "send_sum": "10.0"}
    
    mock_app_context = MagicMock()
    mock_app_context.localization_service.get_text.return_value = "text"
    
    with patch("routers.trade.cmd_xdr_order", new_callable=AsyncMock) as mock_xdr:
        await cmd_edit_sale_sum(mock_message, mock_state, mock_session, app_context=mock_app_context)
        
        mock_state.update_data.assert_called()
        mock_xdr.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_edit_order_price(mock_session, mock_callback, mock_state):
    valid_issuer = "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"
    offer = MagicMock(id=1, amount="10.0", price="0.5", selling=MagicMock(asset_code="XLM", asset_issuer=None), buying=MagicMock(asset_code="USD", asset_issuer=valid_issuer))
    data = {
        "offers": jsonpickle.encode([offer]), 
        "edit_offer_id": 1, 
        "send_asset_code": "XLM", "send_asset_issuer": None,
        "receive_asset_code": "USD", "receive_asset_issuer": valid_issuer
    }
    mock_state.get_data.return_value = data
    
    mock_app_context = MagicMock()
    mock_app_context.localization_service.get_text.return_value = "text"
    
    with patch("routers.trade.jsonpickle.decode", return_value=[offer]), \
         patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.trade.stellar_get_market_link", return_value="link"):
         
        await cmd_edit_order_price(mock_callback, mock_state, mock_session, app_context=mock_app_context)
        
        mock_state.set_state.assert_called_with(StateSaleToken.editing_price)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_edit_sale_cost(mock_session, mock_message, mock_state):
    mock_message.text = "10.0"
    
    mock_app_context = MagicMock()
    mock_app_context.localization_service.get_text.return_value = "text"
    
    with patch("routers.trade.cmd_xdr_order", new_callable=AsyncMock) as mock_xdr:
        await cmd_edit_sale_cost(mock_message, mock_state, mock_session, app_context=mock_app_context)
        
        mock_state.update_data.assert_called_with(receive_sum=10.0, msg=None)
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

        mock_app_context = MagicMock()
        mock_app_context.localization_service.get_text.return_value = "text"

        await cq_swap_choose_token_for(mock_callback, callback_data, mock_state, mock_session, app_context=mock_app_context)
          
        mock_state.set_state.assert_called_with(StateSwapToken.swap_sum)
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_swap_sum(mock_session, mock_message, mock_state):
    """Test cmd_swap_sum using DI-based mocking."""
    mock_message.text = "10.0"
    mock_state.get_data.return_value = {
        "send_asset_code": "XLM", "send_asset_issuer": None,
        "receive_asset_code": "USD", "receive_asset_issuer": "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA",
        "cancel_offers": False, "xdr": None,
        "msg": "msg"
    }
    
    mock_user = MagicMock(can_5000=1)
    
    # Setup mock_app_context with DI
    mock_app_context = MagicMock()
    mock_app_context.localization_service.get_text.return_value = "text"
    
    # Mock repository_factory (for user repo)
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = mock_user
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    # Mock use_case_factory (for swap use case)
    mock_swap_use_case = AsyncMock()
    mock_swap_use_case.execute.return_value = MagicMock(success=True, xdr="XDR_SWAP")
    mock_app_context.use_case_factory.create_swap_assets.return_value = mock_swap_use_case
    
    # Only patch external stellar functions and Telegram send_message
    with patch("routers.swap.stellar_check_receive_sum", return_value=("9.5", False), new_callable=AsyncMock), \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:
        
        await cmd_swap_sum(mock_message, mock_state, mock_session, app_context=mock_app_context)
        
        mock_state.update_data.assert_called()
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cq_swap_strict_receive(mock_session, mock_callback, mock_state):
    mock_state.get_data.return_value = {"receive_asset_code": "USD"}
    
    with patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:

        mock_app_context = MagicMock()
        mock_app_context.localization_service.get_text.return_value = "text"

        await cq_swap_strict_receive(mock_callback, mock_state, mock_session, app_context=mock_app_context)
         
        mock_state.set_state.assert_called_with(StateSwapToken.swap_receive_sum)
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_swap_receive_sum(mock_session, mock_message, mock_state):
    """Test cmd_swap_receive_sum using DI-based mocking."""
    mock_message.text = "10.0"
    mock_state.get_data.return_value = {
        "send_asset_code": "XLM", "send_asset_issuer": None,
        "receive_asset_code": "USD", "receive_asset_issuer": "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA",
        "cancel_offers": False,
        "msg": "msg"
    }
    
    mock_user = MagicMock(can_5000=1)
    
    # Setup mock_app_context with DI
    mock_app_context = MagicMock()
    mock_app_context.localization_service.get_text.return_value = "text"
    
    # Mock repository_factory (for user repo)
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = mock_user
    mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
    
    # Mock use_case_factory (for swap use case)
    mock_swap_use_case = AsyncMock()
    mock_swap_use_case.execute.return_value = MagicMock(success=True, xdr="XDR_SWAP_STRICT")
    mock_app_context.use_case_factory.create_swap_assets.return_value = mock_swap_use_case
    
    # Only patch external stellar functions and Telegram send_message
    with patch("routers.swap.stellar_check_send_sum", return_value=("11.0", False), new_callable=AsyncMock), \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send:
        
        await cmd_swap_receive_sum(mock_message, mock_state, mock_session, app_context=mock_app_context)
        
        # Verify use case was called with strict_receive=True
        _, kwargs = mock_swap_use_case.execute.call_args
        assert kwargs.get('strict_receive') is True
        
        mock_state.update_data.assert_called()


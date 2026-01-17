
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types
from aiogram.fsm.context import FSMContext
from routers.trade import cmd_market, cmd_sale_new_order, cq_trade_choose_token_sell, cq_trade_choose_token_buy, StateSaleToken, SaleAssetCallbackData, BuyAssetCallbackData
from routers.swap import cmd_swap_01, cq_swap_choose_token_from, SwapAssetFromCallbackData
from stellar_sdk import Asset
import jsonpickle

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}
    return state

@pytest.fixture
def mock_callback():
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.from_user.username = "user"
    callback.message = AsyncMock()
    callback.message.chat.id = 123
    return callback

@pytest.fixture
def mock_message():
    message = AsyncMock()
    message.from_user.id = 123
    message.chat.id = 123
    message.text = "test_text"
    return message

# --- tests for routers/trade.py ---

@pytest.mark.asyncio
async def test_cmd_market(mock_session, mock_callback):
    with patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_market(mock_callback, mock_session)
        mock_send.assert_called_once()
        mock_callback.answer.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_sale_new_order(mock_session, mock_callback, mock_state):
    balance = MagicMock()
    balance.asset_code = "XLM"
    balance.balance = "100.0"
    
    with patch("routers.trade.have_free_xlm", return_value=True), \
         patch("routers.trade.stellar_get_balances", return_value=[balance], new_callable=AsyncMock), \
         patch("routers.trade.db_get_default_wallet"), \
         patch("routers.trade.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}

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
         patch("routers.trade.jsonpickle.decode", return_value=asset_data), \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
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
         patch("routers.trade.jsonpickle.decode", return_value=asset_data), \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cq_trade_choose_token_buy(mock_callback, callback_data, mock_state, mock_session)
        
        mock_state.set_state.assert_called_with(StateSaleToken.selling_sum)
        mock_send.assert_called_once()

# --- tests for routers/swap.py ---

@pytest.mark.asyncio
async def test_cmd_swap_01(mock_session, mock_callback, mock_state):
    balance = MagicMock()
    balance.asset_code = "XLM"
    balance.balance = "100.0"
    
    with patch("routers.swap.stellar_get_balances", return_value=[balance], new_callable=AsyncMock), \
         patch("routers.swap.db_get_default_wallet"), \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send, \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
        
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cmd_swap_01(mock_callback, mock_state, mock_session)
        
        mock_send.assert_called_once()
        args, kwargs = mock_state.update_data.call_args
        assert "assets" in kwargs

@pytest.mark.asyncio
async def test_cq_swap_choose_token_from(mock_session, mock_callback, mock_state):
    asset_data = [MagicMock(asset_code="USD", asset_issuer="GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA", balance="10.0")]
    mock_state.get_data.return_value = {"assets": "encoded_assets"}
    callback_data = SwapAssetFromCallbackData(answer="USD")
    
    with patch("routers.swap.stellar_get_selling_offers_sum", return_value=0, new_callable=AsyncMock), \
         patch("routers.swap.stellar_get_balances", return_value=asset_data, new_callable=AsyncMock), \
         patch("routers.swap.db_get_default_wallet"), \
         patch("routers.swap.stellar_check_receive_asset", return_value=["EUR"], new_callable=AsyncMock), \
         patch("routers.swap.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.swap.jsonpickle.decode", return_value=asset_data), \
         patch("other.lang_tools.global_data") as mock_gd, \
         patch("other.lang_tools.get_user_id", return_value=123):
         
        mock_gd.user_lang_dic = {123: 'en'}
        mock_gd.lang_dict = {'en': {}}
        
        await cq_swap_choose_token_from(mock_callback, callback_data, mock_state, mock_session)
        
        mock_state.update_data.assert_called()
        mock_send.assert_called_once()

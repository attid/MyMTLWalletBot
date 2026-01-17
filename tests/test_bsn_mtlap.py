
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from aiogram import types, Bot
from aiogram.fsm.context import FSMContext
from routers.bsn import bsn_mode_command, process_tags, finish_send_bsn, BSNStates, finish_back_bsn
from routers.mtlap import cmd_mtlap_tools, cmd_mtlap_tools_delegate_a, cmd_mtlap_tools_delegate_c, cmd_mtlap_tools_add_delegate_a, cmd_mtlap_send_add_delegate_for_a, cmd_mtlap_tools_recommend, cmd_mtlap_send_recommend
import jsonpickle

# --- tests for routers/bsn.py ---

@pytest.mark.asyncio
async def test_bsn_mode_command(mock_session, mock_message, mock_state):
    command = MagicMock()
    command.args = "tag value"
    
    mock_bsn_data = MagicMock()
    mock_bsn_data.is_empty.return_value = False
    
    with patch("routers.bsn.clear_state", new_callable=AsyncMock) as mock_clear, \
         patch("routers.bsn.bsn_stellar_get_data", return_value=mock_bsn_data, new_callable=AsyncMock), \
         patch("routers.bsn.parse_tag", new_callable=AsyncMock) as mock_parse, \
         patch("routers.bsn.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.bsn.make_tag_message", return_value="msg"), \
         patch("routers.bsn.get_bsn_kb"), \
         patch("routers.bsn.clear_last_message_id", new_callable=AsyncMock):
         
        await bsn_mode_command(mock_message, mock_state, command, mock_session)
        
        mock_clear.assert_called_once()
        mock_parse.assert_called_once()
        mock_state.set_state.assert_called_with(BSNStates.waiting_for_tags)

@pytest.mark.asyncio
async def test_finish_send_bsn(mock_session, mock_callback, mock_state):
    mock_bsn_data = MagicMock()
    # jsonpickle.loads needs to return the mock_bsn_data
    
    with patch("routers.bsn.jsonpickle.loads", return_value=mock_bsn_data), \
         patch("routers.bsn.cmd_gen_data_xdr", return_value="XDR", new_callable=AsyncMock), \
         patch("routers.bsn.cmd_ask_pin", new_callable=AsyncMock) as mock_ask_pin:

        await finish_send_bsn(mock_callback, mock_state, mock_session)
        
        mock_state.update_data.assert_called()
        mock_ask_pin.assert_called_once()

# --- tests for routers/mtlap.py ---

@pytest.mark.asyncio
async def test_cmd_mtlap_tools(mock_session, mock_callback, mock_state):
    with patch("routers.mtlap.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_mtlap_tools(mock_callback, mock_state, mock_session)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_mtlap_tools_delegate_a(mock_session, mock_callback, mock_state):
    with patch("routers.mtlap.stellar_get_data", return_value={"mtla_a_delegate": "DelegateA"}, new_callable=AsyncMock), \
         patch("routers.mtlap.send_message", new_callable=AsyncMock) as mock_send:
         
        from routers.mtlap import cmd_mtlap_tools_delegate_a
        await cmd_mtlap_tools_delegate_a(mock_callback, mock_state, mock_session)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_mtlap_tools_delegate_c(mock_session, mock_callback, mock_state):
    with patch("routers.mtlap.stellar_get_data", return_value={"mtla_c_delegate": "DelegateC"}, new_callable=AsyncMock), \
         patch("routers.mtlap.send_message", new_callable=AsyncMock) as mock_send:
         
        await cmd_mtlap_tools_delegate_c(mock_callback, mock_state, mock_session)
        mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_process_tags(mock_session, mock_message, mock_state):
    mock_bsn_data = MagicMock()
    mock_bsn_data.is_empty.return_value = False
    mock_state.get_data.return_value = {'tags': 'pickled_data'}
    
    # Mock return of jsonpickle.loads
    with patch("routers.bsn.jsonpickle.loads", return_value=mock_bsn_data), \
         patch("routers.bsn.jsonpickle.dumps", return_value="dumps"), \
         patch("routers.bsn.parse_tag", new_callable=AsyncMock) as mock_parse, \
         patch("routers.bsn.clear_last_message_id", new_callable=AsyncMock), \
         patch("routers.bsn.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.bsn.make_tag_message", return_value="msg"), \
         patch("routers.bsn.get_bsn_kb"):
         
        await process_tags(mock_message, mock_state, mock_session)
        
        mock_parse.assert_called()
        mock_state.update_data.assert_called_with(tags="dumps")
        mock_send.assert_called_once()

# --- NEW TESTS FOR MTLAP ROUTER ---

@pytest.mark.asyncio
async def test_cmd_mtlap_tools_add_delegate_a(mock_session, mock_callback, mock_state):
    # Test low xlm
    with patch("routers.mtlap.have_free_xlm", return_value=False), \
         patch("routers.mtlap.send_message", new_callable=AsyncMock) as mock_send:
        await cmd_mtlap_tools_add_delegate_a(mock_callback, mock_state, mock_session)
        mock_callback.answer.assert_called()

    # Test success
    # Define a custom mock for global_data to allow setting db_pool attr
    custom_gd = MagicMock()
    custom_gd.db_pool = MagicMock()
    custom_gd.user_lang_dic = {123: 'en'}
    custom_gd.lang_dict = {'en': {}}

    with patch("routers.mtlap.have_free_xlm", return_value=True), \
         patch("routers.mtlap.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.mtlap.get_kb_return"):

        await cmd_mtlap_tools_add_delegate_a(mock_callback, mock_state, mock_session)
        mock_state.set_state.assert_called() # MTLAPStateTools.delegate_for_a
        mock_send.assert_called()

@pytest.mark.asyncio
async def test_cmd_mtlap_send_add_delegate_for_a(mock_session, mock_message, mock_state):
    mock_message.text = "GDELEGATE"
    mock_account = MagicMock()
    mock_account.account.account.account_id = "GDELEGATE"
    
    with patch("routers.mtlap.stellar_check_account", return_value=mock_account, new_callable=AsyncMock), \
         patch("routers.mtlap.stellar_get_user_account", new_callable=AsyncMock), \
         patch("routers.mtlap.cmd_gen_data_xdr", return_value="XDR", new_callable=AsyncMock), \
         patch("routers.mtlap.send_message", new_callable=AsyncMock) as mock_send:
         
         await cmd_mtlap_send_add_delegate_for_a(mock_message, mock_state, mock_session)
         
         mock_state.update_data.assert_called_with(xdr="XDR")
         mock_send.assert_called_once()

@pytest.mark.asyncio
async def test_cmd_mtlap_tools_recommend(mock_session, mock_callback, mock_state):
    with patch("routers.mtlap.stellar_get_data", return_value={}, new_callable=AsyncMock), \
         patch("routers.mtlap.send_message", new_callable=AsyncMock) as mock_send, \
         patch("routers.mtlap._collect_recommendations", return_value=([], None)):

        await cmd_mtlap_tools_recommend(mock_callback, mock_state, mock_session)

        mock_state.set_state.assert_called() # recommend_for
        mock_send.assert_called()

@pytest.mark.asyncio
async def test_cmd_mtlap_send_recommend(mock_session, mock_message, mock_state):
    mock_message.text = "GRECOMMEND"
    mock_account = MagicMock()
    mock_account.account.account.account_id = "GRECOMMEND"
    
    with patch("routers.mtlap.stellar_get_data", return_value={}, new_callable=AsyncMock), \
         patch("routers.mtlap._collect_recommendations", return_value=([], None)), \
         patch("routers.mtlap.stellar_check_account", return_value=mock_account, new_callable=AsyncMock), \
         patch("routers.mtlap.stellar_get_user_account", new_callable=AsyncMock), \
         patch("routers.mtlap.cmd_gen_data_xdr", return_value="XDR", new_callable=AsyncMock), \
         patch("routers.mtlap.send_message", new_callable=AsyncMock) as mock_send:

        await cmd_mtlap_send_recommend(mock_message, mock_state, mock_session)
        
        mock_state.update_data.assert_called_with(xdr="XDR")
        mock_send.assert_called_once()

# --- NEW TESTS FOR BSN ROUTER ---

@pytest.mark.asyncio
async def test_finish_back_bsn(mock_session, mock_callback, mock_state):
    with patch("routers.bsn.cmd_show_balance", new_callable=AsyncMock) as mock_show:
        await finish_back_bsn(mock_callback, mock_state, mock_session)
        
        mock_state.set_state.assert_called_with(None)
        mock_state.update_data.assert_called_with(tags=None)
        mock_show.assert_called_once()

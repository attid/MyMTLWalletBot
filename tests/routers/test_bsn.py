
import pytest
import jsonpickle  # type: ignore
from unittest.mock import AsyncMock, MagicMock, patch

from routers.bsn import bsn_router, BSNStates, SEND_CALLBACK_DATA, BACK_CALLBACK_DATA, BSNData, BSNRow, Tag, Value, Key, Address, ActionType
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)

@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if bsn_router.parent_router:
        bsn_router._parent_router = None

@pytest.fixture
def setup_bsn_mocks(router_app_context, mock_horizon):
    """
    Common mock setup for BSN router tests.
    """
    class BSNMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            
            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

            # Configure mock_horizon with initial data
            mock_horizon.set_account(self.wallet.public_key, data={
                'Name': 'VGVzdFVzZXI=',  # base64 encoded "TestUser"
                'About': 'VGVzdCBkZXNjcmlwdGlvbg==',
            })

        def set_account_data(self, data: dict):
            """Configure Stellar account data."""
            mock_horizon.set_account(self.wallet.public_key, data=data)

    return BSNMockHelper(router_app_context)


@pytest.mark.asyncio
async def test_bsn_mode_command(mock_telegram, router_app_context, setup_bsn_mocks):
    """Test /bsn command: should fetch data and show menu."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(bsn_router)

    update = create_message_update(user_id=123, text="/bsn")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify response. Initially no changes, so it shows bsn_empty_message.
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "bsn_empty_message" in req['data']['text']
    assert "kb_back" in req['data']['reply_markup']


@pytest.mark.asyncio
async def test_bsn_mode_command_with_args(mock_telegram, router_app_context, setup_bsn_mocks):
    """Test /bsn Name Alice command: should parse tag immediately."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(bsn_router)

    setup_bsn_mocks.set_account_data({}) # Empty data

    update = create_message_update(user_id=123, text="/bsn Name Alice")
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    # Should show [+], Name and Alice because it's a new tag (modified)
    assert "[+]" in req['data']['text']
    assert "Name" in req['data']['text']
    assert "Alice" in req['data']['text']


@pytest.mark.asyncio
async def test_process_tags_interaction(mock_telegram, router_app_context, setup_bsn_mocks):
    """Test entering tags in BSN mode."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(bsn_router)

    # 1. Enter BSN mode
    update1 = create_message_update(user_id=123, text="/bsn")
    await dp.feed_update(bot=router_app_context.bot, update=update1, app_context=router_app_context)
    mock_telegram.clear()

    # 2. Send a new tag
    update2 = create_message_update(user_id=123, text="Website https://mtl.me")
    await dp.feed_update(bot=router_app_context.bot, update=update2, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "Website" in req['data']['text']
    assert "https://mtl.me" in req['data']['text']
    assert "[+]" in req['data']['text']


@pytest.mark.asyncio
async def test_finish_send_bsn(mock_telegram, mock_horizon, router_app_context, setup_bsn_mocks):
    """Test SEND button: should generate XDR and ask for PIN."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(bsn_router)

    # Setup state with some changed tags
    user_id = 123
    test_bsn_data = BSNData(
        address=Address(setup_bsn_mocks.wallet.public_key),
        data=[BSNRow.from_str("Name", "Alice")]
    )
    test_bsn_data.add_new_data_row(Key("About"), Value("Designer"))
    
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    await state.set_state(BSNStates.waiting_for_tags)
    await state.update_data(tags=jsonpickle.dumps(test_bsn_data))

    # We need to mock cmd_ask_pin because it's imported in bsn.py
    with patch("routers.bsn.cmd_ask_pin", AsyncMock()) as mock_ask_pin:
        update = create_callback_update(user_id=user_id, callback_data=SEND_CALLBACK_DATA)
        await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)
        
        # Verify XDR was stored in state
        state_data = await state.get_data()
        assert "xdr" in state_data
        assert "AAAA" in state_data['xdr']
        # Verify PIN requested
        mock_ask_pin.assert_called_once()


@pytest.mark.asyncio
async def test_finish_back_bsn(mock_telegram, router_app_context, setup_bsn_mocks):
    """Test BACK button: should return to balance."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(bsn_router)

    user_id = 123
    state = dp.fsm.get_context(bot=router_app_context.bot, chat_id=user_id, user_id=user_id)
    await state.set_state(BSNStates.waiting_for_tags)

    # Mock cmd_show_balance
    with patch("routers.bsn.cmd_show_balance", AsyncMock()) as mock_show_balance:
        update = create_callback_update(user_id=user_id, callback_data=BACK_CALLBACK_DATA)
        await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)
        
        mock_show_balance.assert_called_once()
        assert await state.get_state() is None


# --- Unit tests for BSN logic ---

def test_bsn_tag_parsing():
    """Unit test for Tag.parse()."""
    t1 = Tag.parse("Name")
    assert t1.key == "Name" and t1.num is None
    
    t2 = Tag.parse("About2")
    assert t2.key == "About" and t2.num == 2
    
    t3 = Tag.parse("CustomTag")
    assert t3.key == "CustomTag"

def test_bsn_data_operations():
    """Unit test for BSNData logic."""
    data = BSNData(Address("G..."), [])
    data.add_new_data_row(Key("Name"), Value("Alice"))
    assert len(data.changed_items()) == 1
    assert data.changed_items()[0].tag.key == "Name"
    assert data.changed_items()[0].action_type == ActionType.ADD

    # Change existing tag by using its specific name with number
    data.add_new_data_row(Key("Name1"), Value("Bob"))
    assert len(data.changed_items()) == 1
    assert data.changed_items()[0].value == "Bob"
    assert data.changed_items()[0].action_type == ActionType.CHANGE

    # Delete
    data.del_data_row(Key("Name1"))
    assert data.changed_items()[0].is_remove()

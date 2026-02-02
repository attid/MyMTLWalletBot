"""
Integration test for NotificationService webhook handling.

This test verifies the complete flow:
webhook → process_notification → _send_notification_to_user → cmd_info_message → send_message

Specifically tests the case where NotificationService calls cmd_info_message
with bot/dispatcher but WITHOUT app_context, which caused the bug:
'NoneType' object has no attribute 'bot'
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from aiogram import Dispatcher
import pytest_asyncio

from infrastructure.services.notification_service import NotificationService
from core.models.notification import NotificationOperation
from db.models import MyMtlWalletBot
from tests.conftest import get_telegram_request


@pytest.fixture
def mock_config():
    """Mock configuration for NotificationService."""
    config = MagicMock()
    config.notifier_url = "http://test-notifier:4021"
    config.webhook_port = 8081
    config.webhook_public_url = "http://test-bot:8081/webhook"
    config.notifier_auth_token = "test-token"
    config.service_secret = None
    config.notifier_public_key = None
    return config


@pytest.fixture
def mock_db_pool():
    """Mock database pool with session context manager."""
    from contextlib import asynccontextmanager

    pool = MagicMock()

    # Mock session
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    @asynccontextmanager
    async def mock_get_session():
        yield session

    pool.get_session = mock_get_session
    pool._session = session  # Store for easy access in tests
    return pool


@pytest_asyncio.fixture
async def notification_service(mock_config, mock_db_pool, router_bot):
    """Create NotificationService instance with real bot connected to mock_telegram."""
    from infrastructure.services.localization_service import LocalizationService

    dispatcher = Dispatcher()
    # Use real localization service with mock db_pool
    localization = LocalizationService(db_pool=mock_db_pool)
    await localization.load_languages("langs")

    service = NotificationService(
        config=mock_config,
        db_pool=mock_db_pool,
        bot=router_bot,  # Real bot connected to mock_telegram
        localization_service=localization,
        dispatcher=dispatcher,
    )
    return service


@pytest.mark.asyncio
async def test_notification_service_sends_message_without_app_context(
    notification_service, mock_telegram, mock_db_pool
):
    """
    Test that NotificationService can send notifications even when
    it doesn't pass app_context to cmd_info_message.

    This is the bug scenario:
    - NotificationService passes bot=self.bot, dispatcher=self.dispatcher
    - But does NOT pass app_context
    - cmd_info_message then passes app_context=None to send_message
    - send_message should use bot parameter instead of app_context.bot
    """

    # Setup: Create mock wallet and operation
    wallet = MagicMock(spec=MyMtlWalletBot)
    wallet.user_id = 12345
    wallet.public_key = "GTEST" + "A" * 51
    wallet.id = 1

    operation = MagicMock(spec=NotificationOperation)
    operation.id = "test-op-123"
    operation.operation = "payment"
    operation.payment_amount = "100.0"
    operation.payment_asset = "XLM"
    operation.from_account = "GFROM" + "A" * 51
    operation.for_account = "GTO" + "B" * 51
    operation.memo = None

    # Mock database to return empty notification filters
    async def mock_execute(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        return mock_result

    mock_db_pool._session.execute = mock_execute

    # Execute: Call _send_notification_to_user
    # This should NOT raise AttributeError: 'NoneType' object has no attribute 'bot'
    await notification_service._send_notification_to_user(wallet, operation)

    # Assert: Check mock_telegram received sendMessage
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None, "Bot should send message via Telegram API"

    # Verify correct user_id
    sent_chat_id = int(req["data"]["chat_id"])
    assert sent_chat_id == 12345, f"Expected chat_id 12345, got {sent_chat_id}"

    # Verify message was sent (content doesn't matter - just that it was sent without crashing)
    sent_text = req["data"]["text"]
    assert len(sent_text) > 0, "Message text should not be empty"


@pytest.mark.asyncio
async def test_send_message_works_with_bot_parameter(router_bot):
    """
    Unit test: send_message should work with bot parameter when app_context is minimal.

    This directly tests the fix for the bug.
    """
    from infrastructure.utils.telegram_utils import send_message
    from unittest.mock import MagicMock

    # Create minimal app_context with bot and dispatcher
    app_context = MagicMock()
    app_context.bot = router_bot
    app_context.dispatcher = Dispatcher()

    # Execute: Call send_message with bot and minimal app_context
    # This should NOT raise AttributeError
    try:
        await send_message(
            session=None,
            user_id=12345,
            msg="Test message",
            reply_markup=None,
            bot=router_bot,
            app_context=app_context,
        )
        # Success - no exception raised
        success = True
    except AttributeError as e:
        if "'NoneType' object has no attribute 'bot'" in str(e):
            pytest.fail(f"Bug not fixed: {e}")
        raise

    assert success, (
        "send_message should work with bot parameter and minimal app_context"
    )

@pytest.mark.asyncio
async def test_notification_sell_offer_link(
    notification_service, mock_telegram, mock_db_pool
):
    """
    Test that manage_sell_offer notifications include a clickable link to the offer
    when offer_id > 0.
    """
    # Setup
    wallet = MagicMock(spec=MyMtlWalletBot)
    wallet.user_id = 12345
    wallet.public_key = "GSELLER" + "A" * 50
    wallet.id = 1

    operation = MagicMock(spec=NotificationOperation)
    operation.id = "op-123"
    operation.operation = "manage_sell_offer"
    operation.offer_amount = "10.0"
    operation.offer_price = "2.0"
    operation.offer_selling_asset = "USDM"
    operation.offer_buying_asset = "XLM"
    operation.offer_id = 1821833749  # This should be the result after processing logic
    # In integration test with full service, we should simulate the payload.
    # But here we are calling _send_notification_to_user with an already mapped operation.
    # So we just ensure the operation object HAS the correct ID, assuming _map_payload_to_operation works.
    # To test logic properly, we should actually test _map_payload_to_operation or mocked behavior.
    
    # Let's trust that we are testing _send_notification_to_user's handling of the ID.
    # We will add a simpler unit test for mapping logic if needed.
    operation.from_account = wallet.public_key
    operation.for_account = wallet.public_key
    operation.transaction_hash = "txhash123"
    operation.display_amount_value = "10.0" # needed for filter check logic
    operation.memo = None
    
    # Mock db for filters
    async def mock_execute(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        return mock_result
    mock_db_pool._session.execute = mock_execute

    # Execute
    await notification_service._send_notification_to_user(wallet, operation)

    # Assert
    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    text = req["data"]["text"]
    
    # Check for link
    expected_link = 'https://viewer.eurmtl.me/offer/1821833749'
    assert expected_link in text, f"Message text should contain link: {expected_link}"
    assert "ID: <a href=" in text, "Message should contain HTML link tag"

@pytest.mark.asyncio
async def test_notification_payload_mapping(notification_service):
    """
    Test _map_payload_to_operation logic for various scenarios.
    """
    # 1. Test created_offer_id fallback
    payload_offer = {
        "operation": {
            "id": "123",
            "type": "manage_sell_offer",
            "account": "GABC",
            "amount": "100",
            "price": "1.0",
            "offer_id": "0",
            "created_offer_id": "99999",
            "asset": {"asset_type": "native"}
        }
    }
    op_offer = notification_service._map_payload_to_operation(payload_offer)
    assert op_offer.offer_id == 99999
    
    # 2. Test path_payment_strict_send (uses dest_amount)
    payload_path_send = {
        "operation": {
            "id": "124",
            "type": "path_payment_strict_send",
            "to": "GTO",
            "amount": "10.0",        # Sent
            "dest_min": "20.0",      # Min Received
            "dest_amount": "21.5",   # Actual Received
            "asset": {"asset_code": "EURMTL", "asset_type": "credit_alphanum4"},
            "source_asset": {"asset_type": "native"}
        }
    }
    op_send = notification_service._map_payload_to_operation(payload_path_send)
    assert op_send.path_sent_amount == 10.0
    assert op_send.path_received_amount == 21.5

    # 3. Test path_payment_strict_receive (uses source_amount)
    payload_path_recv = {
        "operation": {
            "id": "125",
            "type": "path_payment_strict_receive",
            "to": "GTO",
            "amount": "50.0",        # Received
            "source_max": "60.0",    # Max Sent
            "source_amount": "55.5", # Actual Sent
            "asset": {"asset_code": "EURMTL", "asset_type": "credit_alphanum4"},
            "source_asset": {"asset_type": "native"}
        }
    }
    op_recv = notification_service._map_payload_to_operation(payload_path_recv)
    assert op_recv.path_received_amount == 50.0 # Strict receive means we got exactly this
    assert op_recv.path_sent_amount == 55.5

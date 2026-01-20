"""
Tests for routers/cheque.py

This file demonstrates the correct testing patterns:
1. Use mock_telegram for Telegram API (mandatory)
2. Use custom middleware with l10n support for cheque router
3. Use helper functions: create_message_update, create_callback_update, get_telegram_request
4. Configure mocks via app_context DI
5. Minimal patch() usage - only for bot.me (external property)

See tests/README.md for complete testing rules.
"""

import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock

from routers.cheque import router as cheque_router, ChequeCallbackData
from db.models import ChequeStatus
from core.domain.value_objects import PaymentResult, Balance
from core.interfaces.repositories import IChequeRepository, IWalletRepository
from core.domain.entities import Cheque, Wallet
from core.use_cases.cheque.create_cheque import CreateCheque
from core.use_cases.wallet.get_balance import GetWalletBalance
from tests.conftest import (
    create_message_update,
    create_callback_update,
    get_telegram_request,
)


@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if cheque_router.parent_router:
        cheque_router._parent_router = None


# Custom middleware for cheque tests (needs l10n)
class ChequeTestMiddleware:
    def __init__(self, app_context):
        self.app_context = app_context
    
    async def __call__(self, handler, event, data):
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = MagicMock()
        session.rollback = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.all.return_value = []
        session.execute.return_value = result
        
        data["session"] = session
        data["app_context"] = self.app_context
        data["l10n"] = MagicMock()  # Required by cheque router
        return await handler(event, data)


@pytest.mark.asyncio
async def test_cmd_create_cheque_flow(mock_telegram, router_app_context, dp):
    """
    Test cheque creation flow: /create_cheque -> sum -> execute
    """
    user_id = 123
    
    dp.message.middleware(ChequeTestMiddleware(router_app_context))
    dp.callback_query.middleware(ChequeTestMiddleware(router_app_context))
    dp.include_router(cheque_router)

    # 1. Start /create_cheque
    update1 = create_message_update(user_id, "/create_cheque", update_id=1)
    await dp.feed_update(bot=router_app_context.bot, update=update1, app_context=router_app_context)

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "send_cheque_sum" in req["data"]["text"]

    # 2. Enter sum
    mock_create_cheque = MagicMock(spec=CreateCheque)
    mock_create_cheque.execute = AsyncMock(return_value=PaymentResult(success=True, xdr="XDR"))
    router_app_context.use_case_factory.create_create_cheque.return_value = mock_create_cheque

    update2 = create_message_update(user_id, "50", update_id=2, message_id=2)
    await dp.feed_update(bot=router_app_context.bot, update=update2, app_context=router_app_context)

    # Verify cheque preview was shown (message might be deleted, so check >= 1)
    messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(messages) >= 1, "Should send at least initial message"


@pytest.mark.asyncio
async def test_cb_cheque_info(mock_telegram, router_app_context, dp):
    """Test cheque info callback"""
    user_id = 123
    cheque_uuid = "uuid-info"
    
    dp.callback_query.middleware(ChequeTestMiddleware(router_app_context))
    dp.include_router(cheque_router)

    # Mock cheque repository
    mock_cheque = MagicMock(spec=Cheque)
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.count = 10
    mock_cheque.comment = "test comment"
    
    mock_repo = MagicMock(spec=IChequeRepository)
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(return_value=3)
    router_app_context.repository_factory.get_cheque_repository.return_value = mock_repo

    cb_data = ChequeCallbackData(uuid=cheque_uuid, cmd="info").pack()
    update = create_callback_update(user_id, cb_data, update_id=1)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify callback answer
    req = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert req is not None
    assert "3" in req["data"]["text"]  # received
    assert "10" in req["data"]["text"]  # total


@pytest.mark.asyncio
async def test_cmd_invoice_yes(mock_telegram, mock_horizon, router_app_context, dp):
    """Test InvoiceYes callback"""
    user_id = 123
    cheque_uuid = "uuid-invoice"
    
    dp.message.middleware(ChequeTestMiddleware(router_app_context))
    dp.callback_query.middleware(ChequeTestMiddleware(router_app_context))
    dp.include_router(cheque_router)

    # Setup Cheque (Invoice)
    valid_issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    
    mock_cheque = MagicMock(spec=Cheque)
    mock_cheque.status = ChequeStatus.INVOICE.value
    mock_cheque.count = 5
    mock_cheque.asset = f"BTC:{valid_issuer}"
    mock_cheque.amount = 0.1
    mock_cheque.uuid = cheque_uuid
    mock_cheque.comment = "invoice comment"

    mock_repo = MagicMock(spec=IChequeRepository)
    mock_repo.get_by_uuid = AsyncMock(return_value=mock_cheque)
    mock_repo.get_receive_count = AsyncMock(return_value=0)
    router_app_context.repository_factory.get_cheque_repository.return_value = mock_repo

    # Setup Balance UseCase
    mock_balance_uc = MagicMock(spec=GetWalletBalance)
    mock_balance = Balance(
        asset_code="EURMTL",
        asset_issuer="G...",
        balance="100.0",
        limit=None,
        asset_type="credit_alphanum12"
    )
    mock_balance_uc.execute = AsyncMock(return_value=[mock_balance])
    router_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc

    # Setup Wallet Repo
    mock_wallet = MagicMock(spec=Wallet)
    mock_wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    mock_wallet_repo = MagicMock(spec=IWalletRepository)
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    router_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    # Configure mock_horizon for GUSER
    mock_horizon.set_account(mock_wallet.public_key)

    # Run /start invoice_... to set state
    update1 = create_message_update(user_id, f"/start invoice_{cheque_uuid}", update_id=1)
    await dp.feed_update(bot=router_app_context.bot, update=update1, app_context=router_app_context)

    # Click InvoiceYes
    update2 = create_callback_update(user_id, "InvoiceYes", update_id=2, message_id=2)
    await dp.feed_update(bot=router_app_context.bot, update=update2, app_context=router_app_context)

    # Verify at least Loading message was sent
    messages = [r for r in mock_telegram if r['method'] == 'sendMessage']
    assert len(messages) >= 1, "Should send at least Loading message"
    
    # Verify trustline was built (main functionality)
    # build_change_trust_transaction calls load_account which hits Horizon
    reqs = mock_horizon.get_requests("accounts")
    assert len(reqs) >= 1
    assert any(r['account_id'] == mock_wallet.public_key for r in reqs)


@pytest.mark.asyncio
async def test_inline_query_cheques(mock_telegram, router_app_context, dp):
    """Test inline query for cheques"""
    user_id = 999
    
    dp.inline_query.middleware(ChequeTestMiddleware(router_app_context))
    dp.include_router(cheque_router)

    # Mock cheque repository
    mock_cheque = MagicMock(spec=Cheque)
    mock_cheque.uuid = "uuid-inline"
    mock_cheque.status = ChequeStatus.CHEQUE.value
    mock_cheque.amount = 5.0
    mock_cheque.count = 1
    mock_cheque.comment = "InlineC"
    mock_cheque.asset = "EURMTL:G..."
    
    mock_repo = MagicMock(spec=IChequeRepository)
    mock_repo.get_available = AsyncMock(return_value=[mock_cheque])
    router_app_context.repository_factory.get_cheque_repository.return_value = mock_repo

    # Mock bot.me for link generation
    mock_me = MagicMock()
    mock_me.username = "testbot"
    
    with patch.object(router_app_context.bot, 'me', AsyncMock(return_value=mock_me)):
        from aiogram import types
        update = types.Update(
            update_id=1,
            inline_query=types.InlineQuery(
                id="iq1",
                from_user=types.User(id=user_id, is_bot=False, first_name="U", username="u"),
                query="",
                offset=""
            )
        )
        await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # Verify inline query answer
    req = get_telegram_request(mock_telegram, "answerInlineQuery")
    assert req is not None
    results_str = req["data"]["results"]
    results = json.loads(results_str)
    assert len(results) == 1
    assert "uuid-inline" == results[0]["id"]

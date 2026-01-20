
import pytest
from unittest.mock import MagicMock, AsyncMock
from core.use_cases.wallet.get_balance import GetWalletBalance
from core.domain.entities import Wallet
from core.domain.value_objects import Balance
from other.asset_visibility_tools import get_asset_visibility, ASSET_VISIBLE

@pytest.mark.asyncio
async def test_get_balance_filters_lp_shares():
    # Setup
    mock_repo = MagicMock()
    mock_stellar = MagicMock()
    
    # Mock Wallet
    wallet = Wallet(
        id=1, user_id=123, public_key="GUSER", is_default=True, is_free=False,
        balances_event_id="0", last_event_id="0"
    )
    mock_repo.get_default_wallet = AsyncMock(return_value=wallet)
    mock_repo.update = AsyncMock()

    # Mock Stellar Account Details with LP shares and normal assets
    mock_stellar.get_account_details = AsyncMock(return_value={
        'balances': [
            {'asset_type': 'native', 'balance': '100', 'buying_liabilities': '0', 'selling_liabilities': '0'},
            {'asset_type': 'liquidity_pool_shares', 'liquidity_pool_id': 'deadbeef', 'balance': '50'},
            {'asset_type': 'credit_alphanum4', 'asset_code': 'CUSTOM', 'asset_issuer': 'GISSUER', 'balance': '500'}
        ],
        'num_sponsoring': 0,
        'signers': [],
        'data': {}
    })
    mock_stellar.get_selling_offers = AsyncMock(return_value=[])
    mock_stellar.get_assets_by_issuer = AsyncMock(return_value=[])  # Default empty

    use_case = GetWalletBalance(mock_repo, mock_stellar)

    # Execute
    balances = await use_case.execute(user_id=123)

    # Verify
    # Should contain XLM and CUSTOM, but NOT liquidity_pool_shares
    assert len(balances) == 2
    asset_codes = [b.asset_code for b in balances]
    assert 'XLM' in asset_codes
    assert 'CUSTOM' in asset_codes
    assert None not in asset_codes
    assert 'liquidity_pool_shares' not in [b.asset_type for b in balances]


@pytest.mark.asyncio
async def test_get_balance_includes_issued_assets():
    # Setup
    mock_repo = MagicMock()
    mock_stellar = MagicMock()
    
    # Mock Wallet (User is ISSUER)
    wallet = Wallet(
        id=1, user_id=123, public_key="GISSUER", is_default=True, is_free=False,
        balances_event_id="0", last_event_id="0"
    )
    mock_repo.get_default_wallet = AsyncMock(return_value=wallet)
    mock_repo.update = AsyncMock()

    # Mock Stellar Account Details (normal assets)
    mock_stellar.get_account_details = AsyncMock(return_value={
        'balances': [
             {'asset_type': 'native', 'balance': '100', 'buying_liabilities': '0', 'selling_liabilities': '0'}
        ],
        'num_sponsoring': 0, 'signers': [], 'data': {}
    })
    mock_stellar.get_selling_offers = AsyncMock(return_value=[])

    # Mock Issued Assets
    mock_stellar.get_assets_by_issuer = AsyncMock(return_value=[
        {'asset_code': 'MYTOKEN', 'asset_type': 'credit_alphanum12'}
    ])

    use_case = GetWalletBalance(mock_repo, mock_stellar)

    # Execute
    balances = await use_case.execute(user_id=123)

    # Verify
    assert len(balances) == 2
    asset_codes = {b.asset_code: b for b in balances}
    
    assert 'XLM' in asset_codes
    assert 'MYTOKEN' in asset_codes
    
    my_token = asset_codes['MYTOKEN']
    assert my_token.balance == 'unlimited'
    assert my_token.asset_issuer == 'GISSUER'


@pytest.mark.asyncio
async def test_custom_token_visibility_logic():
    # Simulate the logic in start_msg.py
    
    # default visibility string (empty/None)
    vis_str = "{}"
    
    # Custom token "CUSTOM" should be visible by default
    assert get_asset_visibility(vis_str, 'CUSTOM') == ASSET_VISIBLE
    
    # Custom token "UNLIMITED" should be visible by default
    assert get_asset_visibility(vis_str, 'UNLIMITED') == ASSET_VISIBLE
    
    # Simulate hidden
    vis_str_hidden = '{"CUSTOM": "hidden"}'
    assert get_asset_visibility(vis_str_hidden, 'CUSTOM') != ASSET_VISIBLE
    

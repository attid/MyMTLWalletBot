
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from stellar_sdk import Keypair
from other.stellar_tools import stellar_delete_account, stellar_delete_all_deleted

# Mock Keypairs
G_SIGNER = "G_SIGNER_KEY"
S_SIGNER = "S_SIGNER_KEY"
G_MASTER = "G_MASTER_ADDRESS"
G_DELETE = "G_DELETE_ADDRESS"
S_DELETE = "S_DELETE_KEY"

@pytest.fixture
def mock_keypairs():
    master_kp = MagicMock(spec=Keypair)
    master_kp.public_key = G_SIGNER
    master_kp.secret = S_SIGNER
    
    delete_kp = MagicMock(spec=Keypair)
    delete_kp.public_key = G_DELETE
    delete_kp.secret = S_DELETE
    delete_kp.signing_key = True # Simulate having secret
    
    return master_kp, delete_kp

@pytest.mark.asyncio
async def test_stellar_delete_account_uses_master_source_address(mock_keypairs):
    master_kp, delete_kp = mock_keypairs
    master_source_address = G_MASTER
    
    with patch("other.stellar_tools.ServerAsync") as MockServerAsync, \
         patch("other.stellar_tools.TransactionBuilder") as MockTransactionBuilder, \
         patch("other.stellar_tools.stellar_sign"), \
         patch("other.stellar_tools.async_stellar_send", new_callable=AsyncMock), \
         patch("other.stellar_tools.base_fee", 100):
        
        # Setup Server Mock
        server_instance = MagicMock() # Use MagicMock for synchronous methods like accounts()
        # But load_account must be async
        server_instance.load_account = AsyncMock()
        
        MockServerAsync.return_value.__aenter__.return_value = server_instance
        
        # Setup Account Loading
        mock_source_account = MagicMock()
        server_instance.load_account.return_value = mock_source_account
        
        # Setup Account Details Call
        # Mock delete account details
        delete_acc_details = {
            'balances': [{'asset_type': 'native', 'balance': '10.0', 'asset_code': 'XLM'}], 
            'data': {} # No data entries
        }
        # Mock master account details (for trustlines check)
        master_acc_details = {
            'balances': []
        }

        mock_accounts_builder = MagicMock()
        server_instance.accounts.return_value = mock_accounts_builder
        
        # account_id(id) returns a builder with .call() method
        # We need .call() to be async (awaitable)
        
        def account_id_side_effect(account_id):
            mock_req = MagicMock()
            mock_call = AsyncMock() 
            if account_id == G_DELETE:
                mock_call.return_value = delete_acc_details
            elif account_id == G_MASTER: 
                mock_call.return_value = master_acc_details
            else:
                mock_call.return_value = {}
            mock_req.call = mock_call
            return mock_req
            
        mock_accounts_builder.account_id.side_effect = account_id_side_effect

        # Setup TransactionBuilder
        tx_builder_instance = MagicMock()
        MockTransactionBuilder.return_value = tx_builder_instance
        tx_builder_instance.build.return_value.to_xdr.return_value = "fake_xdr"

        # Execute
        await stellar_delete_account(master_kp, delete_kp, master_source_address=str(master_source_address))

        # Verification
        
        # 1. Verify load_account was called with master_source_address
        server_instance.load_account.assert_awaited_with(master_source_address)
        
        # 2. Verify TransactionBuilder init with correct source_account
        MockTransactionBuilder.assert_called_with(
            source_account=mock_source_account,
            network_passphrase='Public Global Stellar Network ; September 2015',
            base_fee=100
        )
        
        # 3. Verify account detail fetching used master_source_address
        mock_accounts_builder.account_id.assert_any_call(master_source_address)
        
        # 4. Verify Account Merge Operation destination
        tx_builder_instance.append_account_merge_op.assert_called_with(
            master_source_address, delete_kp.public_key
        )


@pytest.mark.asyncio
async def test_stellar_delete_all_deleted_passes_correct_address():
    # Mock dependencies
    with patch("other.stellar_tools.stellar_get_master", new_callable=AsyncMock) as mock_get_master, \
         patch("other.stellar_tools.SqlAlchemyWalletRepository") as MockRepo, \
         patch("other.stellar_tools.decrypt", return_value="secret"), \
         patch("other.stellar_tools.stellar_delete_account", new_callable=AsyncMock) as mock_delete_account, \
         patch("other.stellar_tools.Keypair") as MockKeypair:
        
        # Setup Master Keypair (Signer)
        master_kp = MagicMock()
        master_kp.public_key = G_SIGNER
        mock_get_master.return_value = master_kp
        
        # Setup Repo and Wallets
        repo_instance = AsyncMock()
        MockRepo.return_value = repo_instance
        
        # Mock getting default wallet for user 0 (The Real Address)
        master_wallet = MagicMock()
        master_wallet.public_key = G_MASTER
        repo_instance.get_default_wallet.return_value = master_wallet
        
        # Mock deleted wallets
        deleted_wallet = MagicMock()
        deleted_wallet.secret_key = "enc_secret"
        deleted_wallet.user_id = 123
        deleted_wallet.is_free = True
        deleted_wallet.public_key = G_DELETE
        
        repo_instance.get_all_deleted.return_value = [deleted_wallet]
        
        # Mock Keypair.from_secret to accept "secret"
        mock_kp_instance = MagicMock()
        MockKeypair.from_secret.return_value = mock_kp_instance
        
        # Execute
        await stellar_delete_all_deleted(AsyncMock())
        
        # Verify
        # Check that get_default_wallet(0) was called
        repo_instance.get_default_wallet.assert_awaited_with(0)
        
        # Check that stellar_delete_account was called with master_source_address=G_MASTER
        assert mock_delete_account.call_count == 1
        call_args = mock_delete_account.call_args
        
        # Args: (master_account, delete_account)
        # Kwargs: master_source_address=...
        assert call_args[0][0] == master_kp
        assert call_args[1]['master_source_address'] == G_MASTER

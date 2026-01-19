import pytest
from unittest.mock import AsyncMock, MagicMock
from core.domain.entities import Wallet
from core.use_cases.wallet.get_secrets import GetWalletSecrets

@pytest.mark.asyncio
async def test_get_wallet_secrets_with_seed():
    # Setup Mocks
    mock_wallet_repo = AsyncMock()
    mock_encryption_service = MagicMock()
    
    user_id = 123
    pin = "1234"
    encrypted_secret = "ENC_SECRET"
    raw_secret = "RAW_SECRET"
    encrypted_seed = "ENC_SEED"
    raw_seed = "word1 word2 word3"
    
    wallet = Wallet(
        id=1, 
        user_id=user_id, 
        public_key="PUB", 
        is_default=True, 
        is_free=False,
        secret_key=encrypted_secret,
        seed_key=encrypted_seed
    )
    
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    # Mock Decryption
    # First call: decrypt secret_key with pin
    # Second call: decrypt seed_key with raw_secret
    def decrypt_side_effect(data, key):
        if data == encrypted_secret and key == pin:
            return raw_secret
        if data == encrypted_seed and key == raw_secret:
            return raw_seed
        return None
        
    mock_encryption_service.decrypt.side_effect = decrypt_side_effect
    
    # Execute
    use_case = GetWalletSecrets(mock_wallet_repo, mock_encryption_service)
    secrets = await use_case.execute(user_id, pin)
    
    # Verify
    assert secrets is not None
    assert secrets.secret_key == raw_secret
    assert secrets.seed_phrase == raw_seed
    
    # Verify calls
    assert mock_encryption_service.decrypt.call_count == 2

@pytest.mark.asyncio
async def test_get_wallet_secrets_no_seed():
    # Setup Mocks
    mock_wallet_repo = AsyncMock()
    mock_encryption_service = MagicMock()
    
    user_id = 123
    pin = "1234"
    
    wallet = Wallet(
        id=1, 
        user_id=user_id, 
        public_key="PUB", 
        is_default=True, 
        is_free=False,
        secret_key="ENC_SECRET",
        seed_key=None # No seed
    )
    
    mock_wallet_repo.get_default_wallet.return_value = wallet
    mock_encryption_service.decrypt.return_value = "RAW_SECRET"
    
    # Execute
    use_case = GetWalletSecrets(mock_wallet_repo, mock_encryption_service)
    secrets = await use_case.execute(user_id, pin)
    
    # Verify
    assert secrets is not None
    assert secrets.secret_key == "RAW_SECRET"
    assert secrets.seed_phrase is None

import pytest
from unittest.mock import AsyncMock, MagicMock
from stellar_sdk import Network, TransactionEnvelope

from core.use_cases.stellar.process_uri import ProcessStellarUri


@pytest.mark.asyncio
async def test_sep7_rebuild_preserves_bsn_challenge_preconditions():
    # Setup Mocks
    mock_wallet_repo = AsyncMock()
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    mock_wallet_repo.get_default_wallet.return_value = mock_wallet

    mock_stellar_service = AsyncMock()
    # Return valid account details for sequence number
    mock_stellar_service.get_account_details.return_value = {"sequence": "12345"}

    use_case = ProcessStellarUri(mock_wallet_repo, mock_stellar_service)

    user_id = 123
    uri_data = "web+stellar:tx?xdr=AAAAAgAAAAA%2FHWyX8fwoUZSqStT7Am3ezdktyPTkutQ%2F%2B5GWy%2BTJAAAAAMgAAAAAAAAAAQAAAAEAAAAAaXzu6wAAAABpfPAXAAAAAAAAAAIAAAAAAAAACgAAAApic24uZXhwZXJ0AAAAAAABAAAAEDQ5N2ZjN2QyYjEzNzExNzYAAAAAAAAACgAAAA93ZWJfYXV0aF9kb21haW4AAAAAAQAAAApic24uZXhwZXJ0AAAAAAAAAAAAAcvkyQAAAABALx6Jiwp4JFrut7cIL8LoxBpj1Ct9o7PWTSUjqQ6ko8ZzHpQzT1kqtGzjuSQmaQerRcFtePFnbHlKDhkYlb85Ag%3D%3D&replace=sourceAccount%3AX%3BX%3Aaccount+to+authenticate&callback=url%3Ahttps%3A%2F%2Fbsn.expert%2Flogin%2Fcallback&msg=bsn.expert+auth&origin_domain=bsn.expert&signature=tuMphNLs46wzd0Qom%2FxBGX7%2FLB8760%2BwOqYRj%2Fc5xX%2BTHZkd8rN%2FUca2t%2F1ZgAgptfJPE6X%2FlmT9HFIOyNOvBA%3D%3D"

    # Execute
    result = await use_case.execute(uri_data, user_id)

    # Check result
    if not result.success:
        pytest.fail(f"Execution failed with error: {result.error_message}")

    # If success, verify XDR is present
    assert result.xdr is not None

    challenge = use_case._parse_transaction_stellar_uri(uri_data)[
        "uri_object"
    ].transaction_envelope.transaction
    rebuilt = TransactionEnvelope.from_xdr(
        result.xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    ).transaction

    assert challenge.preconditions.time_bounds.min_time == 1769795307
    assert challenge.preconditions.time_bounds.max_time == 1769795607
    assert rebuilt.preconditions == challenge.preconditions
    assert rebuilt.memo == challenge.memo
    assert rebuilt.operations == challenge.operations
    assert rebuilt.soroban_data == challenge.soroban_data
    assert rebuilt.source.account_id == mock_wallet.public_key
    assert rebuilt.sequence == 12346
    assert rebuilt.fee == 10000 * len(rebuilt.operations)

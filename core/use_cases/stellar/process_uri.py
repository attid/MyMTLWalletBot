import urllib.parse
from typing import Dict, Any, Optional
from stellar_sdk import Network, TransactionBuilder
from stellar_sdk.sep import stellar_uri

from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService


class ProcessStellarUriResult:
    def __init__(self, success: bool, xdr: Optional[str] = None, callback_url: Optional[str] = None, 
                 return_url: Optional[str] = None, error_message: Optional[str] = None):
        self.success = success
        self.xdr = xdr
        self.callback_url = callback_url
        self.return_url = return_url
        self.error_message = error_message


class ProcessStellarUri:
    def __init__(self, wallet_repo: IWalletRepository, stellar_service: IStellarService):
        self.wallet_repo = wallet_repo
        self.stellar_service = stellar_service

    async def execute(self, uri_data: str, user_id: int) -> ProcessStellarUriResult:
        try:
            # Parse URI
            parsed_data = self._parse_transaction_stellar_uri(uri_data)
            uri_object = parsed_data['uri_object']
            callback_url = parsed_data['callback_url']
            return_url = parsed_data['return_url']

            xdr_to_check = None
            
            if uri_object.replace:
                # Need to replace source account (tx sequence) with user's account
                wallet = await self.wallet_repo.get_default_wallet(user_id)
                if not wallet:
                     return ProcessStellarUriResult(success=False, error_message="User wallet not found")

                # Fetch generic account details (to get sequence number)
                # IStellarService.get_account_details returns dict, but we need object for SDK builder?
                # Actually, SDK TransactionBuilder needs a 'source_account' object which has 'sequence'.
                # IStellarService doesn't expose 'load_account' returning SDK object directly to avoid leaking SDK types to Core?
                # But here we are dealing with SDK internals (TransactionBuilder) anyway.
                # However, this use case is in Core.
                # Ideally Core should not import stellar_sdk if possible, or only value objects.
                # But we are already importing stellar_sdk ... 
                # Let's use IStellarService to load account. 
                # Wait, IStellarService.get_account_details returns Dict.
                pass
                # The issue is TransactionBuilder source_account requirement. 
                # It needs an object with `account.account_id` and `account.sequence`.
                # We can create a dummy object or extend IStellarService to return something usable.
                # Or, we can move this logic to IStellarService completely? e.g. service.process_uri(...)
                # The plan said "Move process_transaction_stellar_uri to ProcessStellarUri.py".
                
                # Let's fetch account details via service and wrap manually?
                # Or better: `service.load_account_for_builder(public_key)`?
                # But `stellar_tools.py` uses `server.load_account`.
                
                # I'll implement a helper in this file to mimic Account object if needed, 
                # using data from service.get_account_details.
                
                account_details = await self.stellar_service.get_account_details(wallet.public_key)
                if not account_details:
                     return ProcessStellarUriResult(success=False, error_message="Account details not found")
                
                # Mock object for SDK
                class SimpleAccount:
                    def __init__(self, account_id, sequence):
                        self.account_id = account_id
                        self.sequence = int(sequence)
                        
                    async def get_sequence(self):
                         # SDK might not await this, it just accesses .sequence 
                         # But wait, SDK TransactionBuilder calls `source_account.increment_sequence_number()` 
                         # and accesses .sequence.
                         pass
                    
                    @property
                    def increment_sequence_number(self):
                         def func():
                             self.sequence += 1
                         return func

                source_account = SimpleAccount(wallet.public_key, account_details['sequence'])
                
                # Rebuild transaction
                # We need base_fee. Config? Constants?
                base_fee = 10000 
                
                transaction = TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                    base_fee=base_fee,
                )
                transaction.set_timeout(180) # 3 mins

                for operation in uri_object.transaction_envelope.transaction.operations:
                    transaction.append_operation(operation)
                
                envelope = transaction.build()
                xdr_to_check = envelope.to_xdr()

            else:
                xdr_to_check = uri_object.transaction_envelope.to_xdr()

            return ProcessStellarUriResult(
                success=True,
                xdr=xdr_to_check,
                callback_url=callback_url,
                return_url=return_url
            )

        except Exception as e:
            return ProcessStellarUriResult(success=False, error_message=str(e))

    def _parse_transaction_stellar_uri(self, uri_data, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE):
        uri_object = stellar_uri.TransactionStellarUri.from_uri(uri_data, network_passphrase=network_passphrase)

        callback_url = uri_object.callback
        return_url = None

        if hasattr(uri_object, 'return_url'):
            return_url = uri_object.return_url
        elif hasattr(uri_object, 'operation_attrs') and 'return_url' in uri_object.operation_attrs:
            return_url = uri_object.operation_attrs['return_url']
        else:
            try:
                parsed = urllib.parse.urlparse(uri_data)
                query_parameters = urllib.parse.parse_qs(parsed.query)
                if 'return_url' in query_parameters:
                    return_url = query_parameters['return_url'][0]
            except Exception:
                pass

        return {
            'uri_object': uri_object,
            'callback_url': callback_url,
            'return_url': return_url
        }

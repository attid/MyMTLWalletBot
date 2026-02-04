import urllib.parse
from typing import Optional
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
                account_details = await self.stellar_service.get_account_details(wallet.public_key)
                if not account_details:
                     return ProcessStellarUriResult(success=False, error_message="Account details not found")
                
                from stellar_sdk import Account
                source_account = Account(wallet.public_key, int(account_details['sequence']))
                
                # Rebuild transaction
                # We need base_fee. Config? Constants?
                base_fee = 10000 
                
                transaction = TransactionBuilder(
                    source_account=source_account,  # type: ignore[arg-type]
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

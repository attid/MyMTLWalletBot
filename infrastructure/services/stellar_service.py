from typing import Dict, Any, Optional, List
from stellar_sdk import AiohttpClient, ServerAsync
from stellar_sdk.exceptions import NotFoundError
from core.interfaces.services import IStellarService

class StellarService(IStellarService):
    def __init__(self, horizon_url: str = "https://horizon-testnet.stellar.org"):
        self.horizon_url = horizon_url
        # In a real implementation, we would instantiate the Stellar SDK Server here
        # e.g. self.server = Server(horizon_url)

    async def get_account_details(self, public_key: str) -> Optional[Dict[str, Any]]:
        try:
             async with ServerAsync(horizon_url=self.horizon_url, client=AiohttpClient()) as server:
                account_resp = await server.accounts().account_id(public_key).call()
                return account_resp
        except NotFoundError:
            return None
        except Exception as e:
            print(f"Error fetching account {public_key}: {e}")
            return None

    async def get_selling_offers(self, public_key: str) -> List[Dict[str, Any]]:
        try:
            async with ServerAsync(horizon_url=self.horizon_url, client=AiohttpClient()) as server:
                # Limit 200 matches existing logic
                offers_resp = await server.offers().for_seller(public_key).limit(200).call()
                return offers_resp['_embedded']['records']
        except Exception as e:
            print(f"Error fetching offers {public_key}: {e}")
            return []

    async def check_account_exists(self, account_id: str) -> bool:
        try:
            async with ServerAsync(horizon_url=self.horizon_url, client=AiohttpClient()) as server:
                await server.accounts().account_id(account_id).call()
                return True
        except NotFoundError:
            return False
        except Exception as e:
            print(f"Error checking account {account_id}: {e}")
            return False

    async def build_payment_transaction(
        self, 
        source_account_id: str, 
        destination_account_id: str, 
        asset_code: str, 
        asset_issuer: Optional[str], 
        amount: str, 
        memo: Optional[str] = None,
        sequence: Optional[int] = None,
        cancel_offers: bool = False
    ) -> str:
        async with ServerAsync(horizon_url=self.horizon_url, client=AiohttpClient()) as server:
             # Load source account for sequence number
             source_account = await server.load_account(source_account_id)
        
        from stellar_sdk import TransactionBuilder, Asset, Network, Price
        
        base_fee = 10000 # Configurable?
        transaction = TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=base_fee
        )
        transaction.set_timeout(180)
        
        if asset_code == "XLM" and not asset_issuer:
            asset = Asset.native()
        else:
            asset = Asset(asset_code, asset_issuer)
            
        if cancel_offers:
             # Fetch offers for this asset and cancel them
             offers = await self.get_selling_offers(source_account_id)
             # Filter offers that sell this asset
             for offer in offers:
                 selling = offer.get('selling', {})
                 s_code = selling.get('asset_code')
                 s_issuer = selling.get('asset_issuer')
                 # Check if match
                 is_match = False
                 if asset_code == "XLM":
                      if selling.get('asset_type') == 'native': is_match = True
                 else:
                      if s_code == asset_code and s_issuer == asset_issuer: is_match = True
                      
                 if is_match:
                      # Cancel offer
                      # ManageSellOffer with amount=0
                      buying = offer.get('buying', {})
                      b_code = buying.get('asset_code')
                      b_issuer = buying.get('asset_issuer')
                      
                      buying_asset = Asset.native() if buying.get('asset_type') == 'native' else Asset(b_code, b_issuer)
                      
                      transaction.append_manage_sell_offer_op(
                          selling=asset,
                          buying=buying_asset,
                          amount='0',
                          price=Price.from_raw_price('1'), 
                          offer_id=int(offer.get('id', 0))
                      )
            
        transaction.append_payment_op(
            destination=destination_account_id,
            amount=amount,
            asset=asset
        )
        
        if memo:
            transaction.add_text_memo(memo)
            
        return transaction.build().to_xdr()

    async def submit_transaction(self, xdr: str) -> Dict[str, Any]:
        async with ServerAsync(horizon_url=self.horizon_url, client=AiohttpClient()) as server:
            from stellar_sdk import TransactionEnvelope, Network
            transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
            response = await server.submit_transaction(transaction)
            return response

from typing import Dict, Any, Optional, List
from stellar_sdk import AiohttpClient, ServerAsync
from stellar_sdk.exceptions import NotFoundError
from core.interfaces.services import IStellarService
from core.domain.value_objects import Asset

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
        cancel_offers: bool = False,
        create_account: bool = False
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
        
        if create_account:
            transaction.append_create_account_op(
                destination=destination_account_id,
                starting_balance=amount
            )
        else:
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

    async def swap_assets(
        self,
        source_account_id: str,
        send_asset: Asset,
        send_amount: str,
        receive_asset: Asset,
        receive_amount: str,
        path: List[Asset] = [],
        strict_receive: bool = False, # if True, use destination amount, else source amount
        cancel_offers: bool = False
    ) -> str:
        async with ServerAsync(horizon_url=self.horizon_url, client=AiohttpClient()) as server:
             source_account = await server.load_account(source_account_id)
        
        from stellar_sdk import TransactionBuilder, Asset as SdkAsset, Network, Price
        
        base_fee = 10000 
        transaction = TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=base_fee
        )
        transaction.set_timeout(180)

        # Helper to convert domain Asset to SDK Asset
        def to_sdk_asset(a: Asset) -> SdkAsset:
            if a.code == "XLM": return SdkAsset.native()
            return SdkAsset(a.code, a.issuer)

        if cancel_offers:
             # Reuse logic from build_payment
             offers = await self.get_selling_offers(source_account_id)
             for offer in offers:
                 selling = offer.get('selling', {})
                 s_code = selling.get('asset_code')
                 s_issuer = selling.get('asset_issuer')
                 is_match = False
                 if send_asset.code == "XLM":
                      if selling.get('asset_type') == 'native': is_match = True
                 else:
                      if s_code == send_asset.code and s_issuer == send_asset.issuer: is_match = True
                      
                 if is_match:
                      buying = offer.get('buying', {})
                      b_code = buying.get('asset_code')
                      b_issuer = buying.get('asset_issuer')
                      buying_asset = SdkAsset.native() if buying.get('asset_type') == 'native' else SdkAsset(b_code, b_issuer)
                      
                      transaction.append_manage_sell_offer_op(
                          selling=to_sdk_asset(send_asset),
                          buying=buying_asset,
                          amount='0',
                          price=Price.from_raw_price('1'), 
                          offer_id=int(offer.get('id', 0))
                      )

        path_assets = [to_sdk_asset(a) for a in path]
        
        if strict_receive:
            transaction.append_path_payment_strict_receive_op(
                destination=source_account_id, # sending to self
                send_asset=to_sdk_asset(send_asset),
                send_max=send_amount,
                dest_asset=to_sdk_asset(receive_asset),
                dest_amount=receive_amount,
                path=path_assets
            )
        else:
             transaction.append_path_payment_strict_send_op(
                destination=source_account_id,
                send_asset=to_sdk_asset(send_asset),
                send_amount=send_amount,
                dest_asset=to_sdk_asset(receive_asset),
                dest_min=receive_amount,
                path=path_assets
            )
            
        return transaction.build().to_xdr()

    async def manage_offer(
        self,
        source_account_id: str,
        selling: Asset,
        buying: Asset,
        amount: str,
        price: str,
        offer_id: int = 0
    ) -> str:
        async with ServerAsync(horizon_url=self.horizon_url, client=AiohttpClient()) as server:
             source_account = await server.load_account(source_account_id)
        
        from stellar_sdk import TransactionBuilder, Asset as SdkAsset, Network, Price
        
        transaction = TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=10000
        )
        transaction.set_timeout(180)

        def to_sdk_asset(a: Asset) -> SdkAsset:
            if a.code == "XLM": return SdkAsset.native()
            return SdkAsset(a.code, a.issuer)
            
        transaction.append_manage_sell_offer_op(
            selling=to_sdk_asset(selling),
            buying=to_sdk_asset(buying),
            amount=amount,
            price=Price.from_raw_price(price),
            offer_id=offer_id
        )
        
        return transaction.build().to_xdr()

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

    async def submit_transaction(self, xdr: str) -> Dict[str, Any]:
        # TODO: Implement submit
        return {"hash": "mock_hash", "successful": True}

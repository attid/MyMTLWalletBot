from typing import List, Any
from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService
from core.domain.value_objects import Balance

class GetWalletBalance:
    def __init__(self, wallet_repository: IWalletRepository, stellar_service: IStellarService):
        self.wallet_repository = wallet_repository
        self.stellar_service = stellar_service

    async def execute(self, user_id: int, public_key: str = None) -> List[Balance]:
        """
        Retrieves the balance for the user's default wallet or specified public key, 
        including calculation of locked reserves.
        """
        # 1. Determine target public key
        target_key = public_key
        if not target_key:
            # Get default wallet
            wallet = await self.wallet_repository.get_default_wallet(user_id)
            if not wallet:
                raise ValueError("No default wallet found for user")
            target_key = wallet.public_key

        # 2. Get account details from Stellar
        account_details = await self.stellar_service.get_account_details(target_key)
        
        if not account_details:
             return []
             
        offers = await self.stellar_service.get_selling_offers(target_key)

        # 3. Calculate Reserves (Business Logic)
        # lock_sum = 1 (base reserve for account entry)
        lock_sum = 1.0
        lock_sum += float(account_details.get('num_sponsoring', 0)) * 0.5
        lock_sum += (len(account_details.get('signers', [])) - 1) * 0.5
        lock_sum += (len(account_details.get('balances', [])) - 1) * 0.5
        lock_sum += (len(account_details.get('data', {}))) * 0.5
        lock_sum += len(offers) * 0.5
        
        domain_balances = []
        raw_balances = account_details.get('balances', [])
        
        for b in raw_balances:
            asset_type = b.get('asset_type')
            balance = b.get('balance')
            buying_liabilities = b.get('buying_liabilities', '0')
            selling_liabilities = b.get('selling_liabilities', '0')
            asset_code = b.get('asset_code')
            asset_issuer = b.get('asset_issuer')
            
            if asset_type == 'native':
                asset_code = 'XLM'
                # Add reserve to selling_liabilities for Native asset (XLM)
                total_locked = float(selling_liabilities) + lock_sum
                selling_liabilities = str(total_locked)
                
            domain_balances.append(Balance(
                asset_code=asset_code,
                asset_issuer=asset_issuer,
                asset_type=asset_type,
                balance=balance,
                buying_liabilities=buying_liabilities,
                selling_liabilities=selling_liabilities
            ))
            
        return domain_balances

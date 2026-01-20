from typing import List, Optional
from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService
from core.domain.value_objects import Balance

class GetWalletBalance:
    def __init__(self, wallet_repository: IWalletRepository, stellar_service: IStellarService):
        self.wallet_repository = wallet_repository
        self.stellar_service = stellar_service

    async def execute(self, user_id: int, public_key: Optional[str] = None) -> List[Balance]:
        """
        Retrieves the balance for the user's default wallet or specified public key, 
        including calculation of locked reserves.
        """
        wallet = None
        target_key = public_key
        
        # 1. Determine target public key and wallet for caching
        if not target_key:
            # Get default wallet
            wallet = await self.wallet_repository.get_default_wallet(user_id)
            if not wallet:
                raise ValueError("No default wallet found for user")
            target_key = wallet.public_key
            
            # Check Cache (only for default wallet)
            if wallet.balances and wallet.balances_event_id == wallet.last_event_id:
                # Assuming balances are list of Balance objects (handled by Repo/jsonpickle)
                # Need to filter output based on is_free??
                # Legacy: if free_wallet, filter XLM? NO, separate logic in stellar_get_balance_str handles display.
                # stellar_get_balances logic actually filtered Native if free_wallet==0?
                # "if free_wallet == 0: result.append(balance)" -> This limits native asset to non-free wallets?
                # So free wallets DO NOT get XLM in the result list?
                # Line 720 adds XLM manually as a link for free wallets.
                # So logically, GetWalletBalance should return ALL balances, and Presenter/Router handles display?
                # BUT if GetWalletBalance REPLACES stellar_get_balances, the callers expect filtered list?
                # Or add filter param?
                # Legacy logic is messy. Let's return ALL and update callers to filter?
                # Or filter here to be safe drop-in replacement.
                # If I filter here, I change the contract ("Get Balance" should get all balances).
                # But "Free Wallet" concept implies user doesn't own XLM.
                # Let's implement filters like legacy if we want to avoid regression.
                # Legacy: if free_wallet==1 (True), XLM is skipped in the loop (lines 786).
                
                # However, for CACHING to be correct, the cache likely stores ALL balances?
                # Legacy saved `result` to cache. `result` EXCLUDED XLM for free wallets.
                # So cache contains filtered list.
                
                # If I change logic to store full list, legacy code (if any left) reading cache might be confused?
                # But I am removing DB access so nobody else reads cache directly except through Repo.
                
                # I will trust the cache for now.
                return wallet.balances

        # 2. Get account details from Stellar
        account_details = await self.stellar_service.get_account_details(target_key)
        
        if not account_details:
             return []
             
        offers = await self.stellar_service.get_selling_offers(target_key)

        # 3. Calculate Reserves (Business Logic)
        lock_sum = 1.0
        lock_sum += float(account_details.get('num_sponsoring', 0)) * 0.5
        lock_sum += (len(account_details.get('signers', [])) - 1) * 0.5
        lock_sum += (len(account_details.get('balances', [])) - 1) * 0.5
        lock_sum += (len(account_details.get('data', {}))) * 0.5
        lock_sum += len(offers) * 0.5
        
        domain_balances = []
        raw_balances = account_details.get('balances', [])
        
        # Check is_free for filtering
        is_free_wallet = wallet.is_free if wallet else False
        # If public_key was provided, we didn't fetch wallet, so we don't know is_free.
        # But legacy only caches/filters for default wallet (where wallet is known).
        # Should we fetch wallet for public_key if provided? 
        # Legacy stellar_get_balances:
        # user_account = await stellar_get_user_account... (fetches key from DB if None)
        # free_wallet = await stellar_is_free_wallet(session, user_id) (fetches default wallet)
        # So legacy ALWAYS checked default wallet's free status!
        # Even if public_key was passed?
        # Line 741: `free_wallet = await stellar_is_free_wallet(session, user_id)` checks DEFAULT wallet.
        # So even if I ask for random public key, it filters based on MY default wallet? That sounds like a bug or specific feature.
        # But wait, public_key argument usually is None.
        # If public_key IS passed, it's usually for checking someone else?
        # If I check someone else, why filter based on MY wallet type?
        # Assuming public_key is usually None.
        
        if not wallet and public_key:
             # We might not know if it is free. Assume NOT free?
             is_free_wallet = False

        for b in raw_balances:
            asset_type = b.get('asset_type')
            balance = b.get('balance')
            buying_liabilities = b.get('buying_liabilities', '0')
            selling_liabilities = b.get('selling_liabilities', '0')
            asset_code = b.get('asset_code')
            asset_issuer = b.get('asset_issuer')
            
            if asset_type == 'liquidity_pool_shares':
                continue

            if asset_type == 'native':
                asset_code = 'XLM'
                # Add reserve to selling_liabilities for Native asset (XLM)
                total_locked = float(selling_liabilities) + lock_sum
                selling_liabilities = str(total_locked)
                
                # Legacy Filter: Skip Native if Free Wallet
                if is_free_wallet:
                     continue
                
            domain_balances.append(Balance(
                asset_code=asset_code,
                asset_issuer=asset_issuer,
                asset_type=asset_type,
                balance=balance,
                buying_liabilities=buying_liabilities,
                selling_liabilities=selling_liabilities
            ))
            
        # 4. Update Cache
        if wallet and not public_key:
            wallet.balances = domain_balances
            # Legacy: checks last_event_id.
            # We assume last_event_id is up to date on wallet entity from fetching.
            wallet.balances_event_id = wallet.last_event_id
            await self.wallet_repository.update(wallet)
            
        return domain_balances

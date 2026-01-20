"""Use Case Factory Interface and Implementations.

Provides dependency injection for use cases in routers.
"""
from abc import ABC, abstractmethod
from typing import Any

from core.interfaces.repositories import IRepositoryFactory
from core.interfaces.services import IStellarService, IEncryptionService


class IUseCaseFactory(ABC):
    """Abstract Factory for creating Use Cases with dependencies injected."""

    @abstractmethod
    def create_get_wallet_balance(self, session: Any):
        """Create GetWalletBalance use case."""
        pass

    @abstractmethod
    def create_swap_assets(self, session: Any):
        """Create SwapAssets use case."""
        pass

    @abstractmethod
    def create_manage_offer(self, session: Any):
        """Create ManageOffer use case."""
        pass
        
    @abstractmethod
    def create_change_wallet_password(self, session: Any):
        """Create ChangeWalletPassword use case."""
        pass

    @abstractmethod
    def create_get_wallet_secrets(self, session: Any):
        """Create GetWalletSecrets use case."""
        pass

    @abstractmethod
    def create_send_payment(self, session: Any):
        """Create SendPayment use case."""
        pass

    @abstractmethod
    def create_register_user(self, session: Any):
        """Create RegisterUser use case."""
        pass

    @abstractmethod
    def create_update_user_profile(self, session: Any):
        """Create UpdateUserProfile use case."""
        pass

    @abstractmethod
    def create_add_donation(self, session: Any):
        """Create AddDonation use case."""
        pass
    
    @abstractmethod
    def create_wallet_secret_service(self, session: Any):
        """Create WalletSecretService."""
        pass

    @abstractmethod
    def create_process_stellar_uri(self, session: Any):
        """Create ProcessStellarUri use case."""
        pass

    @abstractmethod
    def create_add_wallet(self, session: Any):
        """Create AddWallet use case."""
        pass

    @abstractmethod
    def create_create_cheque(self, session: Any):
        """Create CreateCheque use case."""
        pass

    @abstractmethod
    def create_claim_cheque(self, session: Any):
        """Create ClaimCheque use case."""
        pass

    @abstractmethod
    def create_cancel_cheque(self, session: Any):
        """Create CancelCheque use case."""
        pass


class UseCaseFactory(IUseCaseFactory):
    """
    Factory for creating Use Cases with pre-configured dependencies.
    
    Usage in routers:
        use_case = app_context.use_case_factory.create_swap_assets(session)
        result = await use_case.execute(...)
    """

    def __init__(self, repository_factory: IRepositoryFactory, stellar_service: IStellarService, encryption_service: IEncryptionService, cheque_public_key: str):
        self.repository_factory = repository_factory
        self.stellar_service = stellar_service
        self.encryption_service = encryption_service
        self.cheque_public_key = cheque_public_key

    def create_get_wallet_balance(self, session: Any):
        from core.use_cases.wallet.get_balance import GetWalletBalance
        repo = self.repository_factory.get_wallet_repository(session)
        return GetWalletBalance(repo, self.stellar_service)

    def create_swap_assets(self, session: Any):
        from core.use_cases.trade.swap_assets import SwapAssets
        repo = self.repository_factory.get_wallet_repository(session)
        return SwapAssets(repo, self.stellar_service)

    def create_manage_offer(self, session: Any):
        from core.use_cases.trade.manage_offer import ManageOffer
        repo = self.repository_factory.get_wallet_repository(session)
        return ManageOffer(repo, self.stellar_service)

    def create_change_wallet_password(self, session: Any):
        from core.use_cases.wallet.change_password import ChangeWalletPassword
        repo = self.repository_factory.get_wallet_repository(session)
        return ChangeWalletPassword(repo, self.encryption_service)

    def create_get_wallet_secrets(self, session: Any):
        from core.use_cases.wallet.get_secrets import GetWalletSecrets
        repo = self.repository_factory.get_wallet_repository(session)
        return GetWalletSecrets(repo, self.encryption_service)

    def create_send_payment(self, session: Any):
        from core.use_cases.payment.send_payment import SendPayment
        repo = self.repository_factory.get_wallet_repository(session)
        return SendPayment(repo, self.stellar_service)

    def create_register_user(self, session: Any):
        from core.use_cases.user.register import RegisterUser
        user_repo = self.repository_factory.get_user_repository(session)
        wallet_repo = self.repository_factory.get_wallet_repository(session)
        return RegisterUser(user_repo, wallet_repo)

    def create_update_user_profile(self, session: Any):
        from core.use_cases.user.update_profile import UpdateUserProfile
        repo = self.repository_factory.get_user_repository(session)
        return UpdateUserProfile(repo)

    def create_add_donation(self, session: Any):
        from core.use_cases.user.manage_user import AddDonation
        repo = self.repository_factory.get_user_repository(session)
        return AddDonation(repo)

    def create_wallet_secret_service(self, session: Any):
        from infrastructure.services.wallet_secret_service import SqlAlchemyWalletSecretService
        return SqlAlchemyWalletSecretService(session)

    def create_process_stellar_uri(self, session: Any):
        from core.use_cases.stellar.process_uri import ProcessStellarUri
        repo = self.repository_factory.get_wallet_repository(session)
        return ProcessStellarUri(repo, self.stellar_service)

    def create_add_wallet(self, session: Any):
        from core.use_cases.wallet.add_wallet import AddWallet
        repo = self.repository_factory.get_wallet_repository(session)
        return AddWallet(repo)

    def create_create_cheque(self, session: Any):
        from core.use_cases.cheque.create_cheque import CreateCheque
        repo = self.repository_factory.get_wallet_repository(session)
        return CreateCheque(repo, self.stellar_service)

    def create_claim_cheque(self, session: Any):
        from core.use_cases.cheque.claim_cheque import ClaimCheque
        repo = self.repository_factory.get_wallet_repository(session)
        cheque_repo = self.repository_factory.get_cheque_repository(session)
        add_wallet = self.create_add_wallet(session)
        return ClaimCheque(repo, cheque_repo, self.stellar_service, self.encryption_service, add_wallet, self.cheque_public_key)

    def create_cancel_cheque(self, session: Any):
        from core.use_cases.cheque.cancel_cheque import CancelCheque
        repo = self.repository_factory.get_wallet_repository(session)
        cheque_repo = self.repository_factory.get_cheque_repository(session)
        return CancelCheque(repo, cheque_repo, self.stellar_service, self.encryption_service, self.cheque_public_key)

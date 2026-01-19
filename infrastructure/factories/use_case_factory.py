"""Use Case Factory Interface and Implementations.

Provides dependency injection for use cases in routers.
"""
from abc import ABC, abstractmethod
from typing import Any

from core.interfaces.repositories import IRepositoryFactory
from core.interfaces.services import IStellarService


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


class UseCaseFactory(IUseCaseFactory):
    """
    Factory for creating Use Cases with pre-configured dependencies.
    
    Usage in routers:
        use_case = app_context.use_case_factory.create_swap_assets(session)
        result = await use_case.execute(...)
    """

    def __init__(self, repository_factory: IRepositoryFactory, stellar_service: IStellarService):
        self.repository_factory = repository_factory
        self.stellar_service = stellar_service

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

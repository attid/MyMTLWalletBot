from core.interfaces.repositories import IUserRepository, IWalletRepository


class DeleteUser:
    def __init__(self, user_repo: IUserRepository, wallet_repo: IWalletRepository):
        self.user_repo = user_repo
        self.wallet_repo = wallet_repo

    async def execute(self, user_id: int) -> None:
        """
        Delete a user and all their wallets (Soft Delete).
        """
        # Delete wallets (Soft Delete as per repository impl)
        await self.wallet_repo.delete_all_by_user(user_id)

        # Delete user
        await self.user_repo.delete(user_id)

        # Both repository methods now commit internally, so no additional commit needed here


class AddDonation:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def execute(self, user_id: int, amount: float) -> None:
        """
        Add donation amount to user.
        """
        await self.user_repo.update_donate_sum(user_id, amount)

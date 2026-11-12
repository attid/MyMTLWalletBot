from core.interfaces.repositories import (
    IUserRepository,
    IWalletRepository,
    INotificationRepository,
    IMessageRepository,
)


class DeleteUser:
    def __init__(
        self,
        user_repo: IUserRepository,
        wallet_repo: IWalletRepository,
        notification_repo: INotificationRepository,
        message_repo: IMessageRepository,
    ):
        self.user_repo = user_repo
        self.wallet_repo = wallet_repo
        self.notification_repo = notification_repo
        self.message_repo = message_repo

    async def execute(self, user_id: int) -> None:
        """Reset a user: soft delete wallets and remove the user row.

        Dependents are removed first, in FK-safe order, because
        NOTIFICATION_FILTERS and MYMTLWALLETBOT_MESSAGES reference
        MYMTLWALLETBOT_USERS. Wallet rows are only marked NEED_DELETE=1:
        keys and on-chain funds stay intact.
        """
        await self.notification_repo.delete_all_by_user(user_id)
        await self.message_repo.delete_all_by_user(user_id)
        await self.wallet_repo.delete_all_by_user(user_id)
        await self.user_repo.delete(user_id)


class AddDonation:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def execute(self, user_id: int, amount: float) -> None:
        """
        Add donation amount to user.
        """
        await self.user_repo.update_donate_sum(user_id, amount)

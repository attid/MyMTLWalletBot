"""Independent Telegram delivery for blockchain notifications."""

from typing import Protocol

from aiogram import Bot

from core.models.blockchain_notification import BlockchainNotification


class NotificationSender(Protocol):
    """Sends a notification without participating in UI state management."""

    async def send_notification(self, notification: BlockchainNotification) -> None: ...


class TelegramNotificationDeliveryService:
    """Send notification messages without touching the FSM or UI keyboard."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_notification(self, notification: BlockchainNotification) -> None:
        await self._bot.send_message(
            chat_id=notification.user_id,
            text=notification.text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

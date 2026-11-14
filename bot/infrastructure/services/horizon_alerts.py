"""Admin notifications about Horizon failover events.

Delivery is best-effort on purpose: the admin message is a convenience on top of
the structured ``event=horizon_failover`` logs, never a durable queue. The
failover contract forbids delaying a request to deliver a notification.
"""

from __future__ import annotations

from loguru import logger
from aiogram import Bot

from infrastructure.services.horizon_pool import (
    FailoverReason,
    HorizonEvent,
    HorizonEventKind,
)

_REASON_TEXT = {
    FailoverReason.RATE_LIMITED: "rate limit",
    FailoverReason.SERVER_ERROR: "server error",
    FailoverReason.UNREACHABLE: "unreachable/timeout",
}


class HorizonAdminAlerter:
    """Formats pool events and sends them to the admin chat."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def notify(self, event: HorizonEvent) -> None:
        text = format_horizon_event(event)
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
        except Exception as exc:  # best-effort: never break a request
            logger.bind(
                event="horizon_failover",
                stage="alert_failed",
                pool=event.role,
                error=str(exc),
            ).warning("Horizon failover alert was not delivered")


def format_horizon_event(event: HorizonEvent) -> str:
    pool = f"{event.role}-horizon"
    if event.kind is HorizonEventKind.SWITCH:
        reason = (
            _REASON_TEXT[event.reason]
            if event.reason in _REASON_TEXT
            else "unknown reason"
        )
        if event.http_status:
            reason = f"{reason}, HTTP {event.http_status}"
        attempt = f", попытка {event.attempt}" if event.attempt else ""
        return (
            f"⚠️ Horizon failover ({pool})\n"
            f"{event.from_url} → {event.to_url}\n"
            f"Причина: {reason}{attempt}"
        )
    if event.kind is HorizonEventKind.ALL_DOWN:
        backoff = (
            f", повтор через ~{event.backoff_seconds:g}s"
            if event.backoff_seconds
            else ""
        )
        return (
            f"🚨 Horizon: все ноды недоступны ({pool})\n"
            f"Последняя: {event.from_url}{backoff}\n"
            "Запросы к Stellar временно не выполняются."
        )
    if event.kind is HorizonEventKind.FREEZE:
        return (
            f"🚨 Horizon freeze ({pool})\n"
            f"Переключений за окно: {event.switches}\n"
            f"Остаёмся на {event.to_url} до конца окна."
        )
    return (
        f"✅ Horizon восстановлен ({pool}): {event.to_url}\n"
        f"Переключений за инцидент: {event.switches}"
    )

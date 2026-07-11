"""Non-navigating controls for delayed blockchain notifications."""

from aiogram import F, Router, types
from loguru import logger

from infrastructure.services.app_context import AppContext
from infrastructure.services.notification_badge_service import BADGE_CALLBACK_DATA


router = Router()


@router.callback_query(F.data == BADGE_CALLBACK_DATA)
async def flush_pending_notifications(
    callback: types.CallbackQuery, app_context: AppContext
) -> None:
    """Flush queued notifications without changing the active UI flow."""
    await callback.answer()
    coordinator = app_context.notification_coordinator
    if coordinator is not None:
        try:
            await coordinator.flush(
                callback.from_user.id, ignore_hold=True, reason="manual_badge_click"
            )
        except Exception:
            logger.bind(
                event="notification_manual_flush_failed", user_id=callback.from_user.id
            ).exception("manual pending-notification flush failed")

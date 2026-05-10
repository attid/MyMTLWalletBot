from aiogram.fsm.context import FSMContext
from aiogram.types import ErrorEvent, Update
from sentry_sdk import capture_exception, push_scope

from other.config_reader import config


def _format_exception_summary(exception: Exception) -> str:
    message = str(exception)
    if len(message) > 500:
        message = message[:497] + "..."
    return f"{type(exception).__name__}: {message}"


def _format_update_summary(update: Update) -> dict[str, object]:
    summary: dict[str, object] = {"update_id": update.update_id}

    if update.message:
        summary["event"] = "message"
        summary["user_id"] = (
            update.message.from_user.id if update.message.from_user else None
        )
        summary["chat_id"] = update.message.chat.id
        return summary

    if update.callback_query:
        summary["event"] = "callback_query"
        summary["user_id"] = update.callback_query.from_user.id
        summary["callback_data"] = update.callback_query.data
        if update.callback_query.message:
            summary["message_id"] = update.callback_query.message.message_id
        return summary

    summary["event"] = update.event_type
    return summary


async def sentry_error_handler(
    event: ErrorEvent, state: FSMContext | None = None
) -> None:
    from loguru import logger

    update_summary = _format_update_summary(event.update)
    logger.opt(exception=event.exception).error(
        "Error caught: {} on update: {}",
        _format_exception_summary(event.exception),
        update_summary,
    )

    user_id = None
    if event.update.message and event.update.message.from_user:
        user_id = event.update.message.from_user.id
    elif event.update.callback_query and event.update.callback_query.from_user:
        user_id = event.update.callback_query.from_user.id

    if len(config.sentry_dsn) > 20:
        with push_scope() as scope:
            if state:
                data = await state.get_data()
                scope.set_context("aiogram", {"state": data})
            scope.set_user({"id": user_id})
            capture_exception(event.exception)

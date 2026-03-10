from aiogram.fsm.context import FSMContext
from aiogram.types import ErrorEvent
from sentry_sdk import capture_exception, push_scope

from other.config_reader import config


async def sentry_error_handler(event: ErrorEvent, state: FSMContext | None = None) -> None:
    from loguru import logger

    logger.exception(f"Error caught: {event.exception} on update: {event.update}")

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

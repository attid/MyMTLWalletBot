import asyncio
from contextlib import suppress
from functools import wraps
from typing import Callable, Optional

from loguru import logger
from aiogram import Bot
from other.loguru_tools import safe_catch_async


class TaskKilled(Exception):
    pass


def kill_task(task):
    task.cancel()


_bot: Optional[Bot] = None
_admin_id: Optional[int] = None


def setup_async_utils(bot: Bot, admin_id: int):
    global _bot, _admin_id
    _bot = bot
    _admin_id = admin_id


@safe_catch_async
async def task_with_timeout(
    func: Callable, timeout: int, kill_on_timeout: bool, *args, **kwargs
):
    task = asyncio.create_task(func(*args, **kwargs))

    # start_time = datetime.now()

    async def send_update():
        minutes_passed = 0
        while not task.done():
            await asyncio.sleep(60)  # Wait for 1 minute
            minutes_passed += 1
            if _bot and _admin_id:
                try:
                    await _bot.send_message(
                        chat_id=_admin_id,
                        text=f"Task {func.__name__} has been running for {minutes_passed} minute(s).",
                    )
                except Exception:
                    pass

    update_task = asyncio.create_task(send_update())

    try:
        result = await asyncio.wait_for(task, timeout=timeout)
        if not update_task.done():
            update_task.cancel()
        return result
    except asyncio.TimeoutError:
        if not update_task.done():
            update_task.cancel()
        raise TaskKilled(f"Task {func.__name__} was timeout")
    finally:
        if kill_on_timeout and not task.done():
            kill_task(task)


def with_timeout(timeout: float):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async def log_long_runtime() -> None:
                warnings = 0
                while True:
                    await asyncio.sleep(timeout)
                    warnings += 1
                    logger.bind(
                        event="async_task_running_long",
                        function=func.__name__,
                        elapsed_seconds=timeout * warnings,
                    ).warning(
                        f"Function {func.__name__} is still running: "
                        f"elapsed_seconds={timeout * warnings:g}"
                    )

            warning_task = asyncio.create_task(log_long_runtime())
            try:
                return await func(*args, **kwargs)
            finally:
                warning_task.cancel()
                with suppress(asyncio.CancelledError):
                    await warning_task

        return wrapper

    return decorator

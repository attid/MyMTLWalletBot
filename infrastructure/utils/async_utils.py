import asyncio
from datetime import datetime
from functools import wraps
from time import time
from typing import Callable, Any

from loguru import logger
from other.global_data import global_data # Used for sending admin notifications in task_with_timeout
from other.loguru_tools import safe_catch_async

class TaskKilled(Exception):
    pass


def kill_task(task):
    task.cancel()


@safe_catch_async
async def task_with_timeout(func: Callable, timeout: int, kill_on_timeout: bool, *args, **kwargs):
    task = asyncio.create_task(func(*args, **kwargs))

    # start_time = datetime.now()

    async def send_update():
        minutes_passed = 0
        while not task.done():
            await asyncio.sleep(60)  # Wait for 1 minute
            minutes_passed += 1
            try:
                await global_data.bot.send_message(
                    chat_id=global_data.admin_id,
                    text=f"Task {func.__name__} has been running for {minutes_passed} minute(s)."
                )
            except:
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


def with_timeout(timeout: int, kill_on_timeout: bool = False):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time()
            task = asyncio.create_task(func(*args, **kwargs))
            minutes_logged = 0

            while not task.done():
                await asyncio.sleep(1)  # Check every second
                elapsed_time = time() - start_time
                minutes = int(elapsed_time / 60)
                if elapsed_time > timeout and minutes > minutes_logged:
                    logger.warning(f"Function {func.__name__} running for {minutes} minutes")

                    if kill_on_timeout:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            logger.error(f"Task {func.__name__} forced stopped")
                        return None
                    else:
                        logger.info(f"Waiting for {func.__name__} finish after timeout")

                    minutes_logged = minutes

            try:
                result = await task
                return result
            finally:
                if not task.done():
                    logger.warning(f"Task {func.__name__} still running after processing")
                else:
                    total_minutes = int((time() - start_time) / 60)
                    if total_minutes > 0:
                        logger.info(
                            f"Function {func.__name__} finished, total runtime: {total_minutes} minutes")

        return wrapper

    return decorator

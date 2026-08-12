import asyncio

import pytest

from infrastructure.utils.async_utils import with_timeout


@pytest.mark.asyncio
async def test_with_timeout_warns_without_cancelling_long_coroutine() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    cancelled = asyncio.Event()

    @with_timeout(0.01)
    async def stuck_work() -> None:
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(stuck_work())
    try:
        await asyncio.wait_for(started.wait(), timeout=0.1)
        await asyncio.sleep(0.03)

        assert not task.done()
        assert not cancelled.is_set()

        release.set()
        await asyncio.wait_for(task, timeout=0.2)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_with_timeout_preserves_timeout_raised_by_wrapped_function() -> None:
    @with_timeout(1)
    async def upstream_timeout() -> None:
        raise TimeoutError("upstream request timed out")

    with pytest.raises(TimeoutError, match="upstream request timed out"):
        await upstream_timeout()

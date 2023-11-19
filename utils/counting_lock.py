import asyncio

class CountingLock:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._waiting_count = 0

    async def acquire(self):
        self._waiting_count += 1
        await self._lock.acquire()
        self._waiting_count -= 1

    def release(self):
        self._lock.release()

    def waiting_count(self):
        return self._waiting_count

    async def __aenter__(self):
        await self.acquire()

    async def __aexit__(self, exc_type, exc, tb):
        self.release()

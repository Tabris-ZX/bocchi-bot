import asyncio
import time
from collections import deque


class DrawerRequestQueue:
    def __init__(self, interval_seconds: int = 60) -> None:
        self.interval_seconds = interval_seconds
        self._lock = asyncio.Lock()
        self._queue: deque[asyncio.Future[None]] = deque()
        self._next_available_at = 0.0
        self._processing = False

    async def enter(self) -> tuple[asyncio.Future[None], int, int]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        async with self._lock:
            now = time.monotonic()
            cooldown_seconds = max(0, int(self._next_available_at - now))
            position = len(self._queue) + (1 if self._processing else 0)
            eta_seconds = cooldown_seconds + position * self.interval_seconds
            self._queue.append(future)
            self._try_wake_next_locked()
            return future, position, eta_seconds

    async def wait_turn(self, future: asyncio.Future[None]) -> None:
        await future

    async def leave(self) -> None:
        async with self._lock:
            self._processing = False
            self._next_available_at = time.monotonic() + self.interval_seconds
        await asyncio.sleep(self.interval_seconds)
        async with self._lock:
            self._try_wake_next_locked()

    async def cancel(self, future: asyncio.Future[None]) -> None:
        async with self._lock:
            if future in self._queue:
                self._queue.remove(future)
            if not future.done():
                future.cancel()
            self._try_wake_next_locked()

    def _try_wake_next_locked(self) -> None:
        while self._queue and self._queue[0].done():
            self._queue.popleft()

        if self._processing or not self._queue:
            return

        now = time.monotonic()
        if now < self._next_available_at:
            return

        future = self._queue.popleft()
        self._processing = True
        if not future.done():
            future.set_result(None)

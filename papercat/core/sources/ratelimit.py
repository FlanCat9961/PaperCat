from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class TokenBucket:
    def __init__(
        self,
        min_interval_sec: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.min_interval_sec = min_interval_sec
        self._clock = clock
        self._sleeper = sleeper
        self._lock = asyncio.Lock()
        self._last_acquire_time: float | None = None

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            if self._last_acquire_time is not None:
                elapsed = now - self._last_acquire_time
                remaining = self.min_interval_sec - elapsed
                if remaining > 0:
                    await self._sleeper(remaining)
                    now = self._clock()
            self._last_acquire_time = now

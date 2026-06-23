from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class AsyncRunner:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._tasks: set[asyncio.Task[Any]] = set()

    def submit(
        self,
        coro: Coroutine[Any, Any, T],
        on_progress: Callable[[object], None] | None = None,
        on_done: Callable[[T], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> asyncio.Task[T]:
        del on_progress
        task = self.loop.create_task(coro)
        self._tasks.add(task)

        def handle_done(done: asyncio.Task[T]) -> None:
            self._tasks.discard(done)
            try:
                result = done.result()
            except asyncio.CancelledError:
                return
            except BaseException as exc:
                if on_error is not None:
                    self.loop.call_soon(on_error, exc)
            else:
                if on_done is not None:
                    self.loop.call_soon(on_done, result)

        task.add_done_callback(handle_done)
        return task

    def submit_sync(
        self,
        func: Callable[..., T],
        *args: object,
        on_done: Callable[[T], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> asyncio.Task[T]:
        async def run_in_thread() -> T:
            return await asyncio.to_thread(func, *args)

        return self.submit(run_in_thread(), on_done=on_done, on_error=on_error)

    def cancel_all(self) -> None:
        for task in list(self._tasks):
            task.cancel()

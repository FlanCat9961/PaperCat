from __future__ import annotations

from collections.abc import Callable

from papercat.core.cleaner import Cleaner, CleanupReport
from papercat.gui.workers.async_runner import AsyncRunner


class CleanupController:
    def __init__(self, cleaner: Cleaner, async_runner: AsyncRunner) -> None:
        self.cleaner = cleaner
        self.async_runner = async_runner

    def start_auto(self, on_done: Callable[[CleanupReport], None] | None = None) -> None:
        self.async_runner.submit_sync(self.cleaner.cleanup_auto, on_done=on_done)

    def start_manual(
        self, ids: list[int], on_done: Callable[[CleanupReport], None] | None = None
    ) -> None:
        self.async_runner.submit_sync(self.cleaner.cleanup_manual, ids, on_done=on_done)

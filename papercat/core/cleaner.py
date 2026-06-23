from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from papercat.core.config import Config
from papercat.core.library import Library
from papercat.core.lock import ProcessLock
from papercat.core.notifier import Notifier


@dataclass
class CleanupResult:
    deleted_count: int
    skipped_kept: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass
class CleanupReport:
    mode: Literal["auto", "manual"]
    started_at: int
    finished_at: int
    result: CleanupResult


class Cleaner:
    def __init__(
        self,
        *,
        config: Config,
        library: Library,
        notifier: Notifier,
        lock: ProcessLock,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.library = library
        self.notifier = notifier
        self.lock = lock
        self.logger = logger

    def cleanup_auto(self) -> CleanupReport:
        started_at = int(time.time())
        with self.lock:
            total = self.library.count_non_kept()
            excess = max(0, total - self.config.non_kept_limit)
            victims = self.library.oldest_non_kept(excess) if excess else []
            deleted = self.library.delete_many([victim.id for victim in victims])
        report = CleanupReport("auto", started_at, int(time.time()), CleanupResult(deleted))
        self.notifier.notify(self.notifier.from_cleanup_report(report))
        return report

    def cleanup_manual(self, ids: list[int]) -> CleanupReport:
        started_at = int(time.time())
        with self.lock:
            safe_ids: list[int] = []
            skipped_kept = 0
            for wallpaper_id in ids:
                record = self.library.get(wallpaper_id)
                if record is None:
                    continue
                if record.is_kept:
                    skipped_kept += 1
                    continue
                safe_ids.append(wallpaper_id)
            deleted = self.library.delete_many(safe_ids)
        report = CleanupReport(
            "manual", started_at, int(time.time()), CleanupResult(deleted, skipped_kept)
        )
        self.notifier.notify(self.notifier.from_cleanup_report(report))
        return report

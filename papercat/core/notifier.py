import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol


class NotificationConfigLike(Protocol):
    enabled: bool
    on_crawl_done: bool
    on_cleanup_done: bool
    on_error: bool


class NotifyEventType(StrEnum):
    CRAWL_DONE = "crawl_done"
    CLEANUP_DONE = "cleanup_done"
    ERROR = "error"


@dataclass(frozen=True)
class NotifyEvent:
    type: NotifyEventType
    title: str
    body: str
    urgency: Literal["low", "normal", "critical"] = "normal"


Runner = Callable[..., subprocess.CompletedProcess[str]]


class Notifier:
    def __init__(
        self,
        cfg: NotificationConfigLike,
        runner: Runner = subprocess.run,
        logger: logging.Logger | None = None,
    ) -> None:
        self.cfg = cfg
        self.runner = runner
        self.logger = logger or logging.getLogger(__name__)

    def notify(self, event: NotifyEvent) -> None:
        if not self.cfg.enabled or not self._event_enabled(event.type):
            return
        try:
            self.runner(
                [
                    "notify-send",
                    "--app-name=PaperCat",
                    f"--urgency={event.urgency}",
                    event.title,
                    event.body,
                ],
                capture_output=True,
            )
        except Exception as exc:
            self.logger.warning("desktop notification failed: %s", exc)

    @staticmethod
    def from_crawl_report(report: object) -> NotifyEvent:
        downloaded = getattr(report, "total_downloaded", 0)
        failures = getattr(report, "total_failures", 0)
        return NotifyEvent(
            NotifyEventType.CRAWL_DONE,
            "PaperCat crawl completed",
            f"Downloaded {downloaded} wallpaper(s), {failures} failure(s).",
            "normal" if failures == 0 else "critical",
        )

    @staticmethod
    def from_cleanup_report(report: object) -> NotifyEvent:
        deleted = getattr(report, "deleted", getattr(report, "deleted_count", 0))
        return NotifyEvent(
            NotifyEventType.CLEANUP_DONE,
            "PaperCat cleanup completed",
            f"Deleted {deleted} wallpaper(s).",
        )

    def _event_enabled(self, event_type: NotifyEventType) -> bool:
        return {
            NotifyEventType.CRAWL_DONE: self.cfg.on_crawl_done,
            NotifyEventType.CLEANUP_DONE: self.cfg.on_cleanup_done,
            NotifyEventType.ERROR: self.cfg.on_error,
        }[event_type]

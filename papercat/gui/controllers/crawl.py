from __future__ import annotations

from collections.abc import Callable

from papercat.core.crawler import Crawler, CrawlReport, ProgressCallback
from papercat.core.subscription import SubscriptionStore
from papercat.gui.workers.async_runner import AsyncRunner


class CrawlController:
    def __init__(
        self, crawler: Crawler, store: SubscriptionStore, async_runner: AsyncRunner
    ) -> None:
        self.crawler = crawler
        self.store = store
        self.async_runner = async_runner
        self._busy = False

    def is_busy(self) -> bool:
        return self._busy

    def start(
        self,
        sub_ids: list[int],
        on_progress: ProgressCallback = None,
        on_done: Callable[[CrawlReport], None] | None = None,
    ) -> None:
        if self._busy:
            return
        selected_ids = set(sub_ids)
        subscriptions = [
            sub for sub in self.store.list(enabled_only=True) if sub.id in selected_ids
        ]
        self._busy = True

        def done(report: CrawlReport) -> None:
            self._busy = False
            if on_done is not None:
                on_done(report)

        def error(exc: BaseException) -> None:
            self._busy = False
            raise exc

        self.async_runner.submit(
            self.crawler.crawl(subscriptions, progress=on_progress), on_done=done, on_error=error
        )

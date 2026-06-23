from __future__ import annotations

import asyncio
import inspect
import logging
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from papercat.core.config import Config
from papercat.core.exceptions import SourceAuthError, SourceError
from papercat.core.hook import HookRunner
from papercat.core.library import Library
from papercat.core.lock import ProcessLock
from papercat.core.matcher import matches_aspect_ratio, matches_format
from papercat.core.notifier import Notifier
from papercat.core.sources.base import CandidateItem, HttpClientLike, SearchQuery, Source
from papercat.core.sources.http import HttpClient
from papercat.core.sources.registry import SourceRegistry
from papercat.core.subscription import Subscription


@dataclass
class SubscriptionResult:
    subscription_id: int
    subscription_name: str
    downloaded: int = 0
    skipped_duplicate: int = 0
    skipped_filter: int = 0
    failures: list[str] = field(default_factory=list)
    aborted_reason: str | None = None


@dataclass
class CrawlReport:
    started_at: int
    finished_at: int
    results: list[SubscriptionResult]

    @property
    def total_downloaded(self) -> int:
        return sum(result.downloaded for result in self.results)

    @property
    def total_failures(self) -> int:
        return sum(len(result.failures) for result in self.results)


class ProgressEvent(BaseModel):
    type: Literal["sub_started", "sub_progress", "sub_finished", "crawl_started", "crawl_finished"]
    subscription_id: int | None = None
    subscription_name: str | None = None
    downloaded: int = 0
    target: int = 0
    message: str | None = None


ProgressCallback = Callable[[ProgressEvent], Awaitable[None] | None] | None


class Crawler:
    def __init__(
        self,
        *,
        config: Config,
        library: Library,
        source_registry: SourceRegistry,
        hook_runner: HookRunner,
        notifier: Notifier,
        lock: ProcessLock,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.library = library
        self.source_registry = source_registry
        self.hook_runner = hook_runner
        self.notifier = notifier
        self.lock = lock
        self.logger = logger

    async def crawl(
        self, subs: Sequence[Subscription], progress: ProgressCallback = None
    ) -> CrawlReport:
        started_at = int(time.time())
        await self._emit(progress, ProgressEvent(type="crawl_started"))
        with self.lock:
            async with HttpClient(
                proxy=self.config.proxy,
                timeout=self.config.crawl.request_timeout_seconds,
                user_agent="PaperCat/0.1",
                retry_attempts=self.config.crawl.retry_attempts,
            ) as http:
                sem = asyncio.Semaphore(self.config.crawl.max_concurrent_subscriptions)
                results = await asyncio.gather(
                    *(self._run_with_sem(sub, http, sem, progress) for sub in subs),
                    return_exceptions=False,
                )

        report = CrawlReport(started_at, int(time.time()), list(results))
        self.notifier.notify(self.notifier.from_crawl_report(report))
        await self._emit(
            progress, ProgressEvent(type="crawl_finished", downloaded=report.total_downloaded)
        )
        return report

    async def _run_with_sem(
        self,
        sub: Subscription,
        http: HttpClientLike,
        sem: asyncio.Semaphore,
        progress: ProgressCallback,
    ) -> SubscriptionResult:
        async with sem:
            return await self._run_one(sub, http, progress)

    async def _run_one(
        self, sub: Subscription, http: HttpClientLike, progress: ProgressCallback
    ) -> SubscriptionResult:
        result = SubscriptionResult(sub.id, sub.name, aborted_reason="exhausted")
        await self._emit(
            progress,
            ProgressEvent(
                type="sub_started",
                subscription_id=sub.id,
                subscription_name=sub.name,
                target=self.config.crawl.per_subscription_max,
            ),
        )
        source = self.source_registry.get(sub.source)
        query = SearchQuery(
            include_tags=sub.include_tags,
            exclude_tags=sub.exclude_tags,
            min_resolution=sub.resolution,
            aspect_ratio=sub.aspect_ratio,
            nsfw_level=sub.nsfw_level,
            formats=list(sub.formats),
            max_pages=sub.max_scan_pages,
        )
        try:
            random_candidates: list[CandidateItem] = []
            scanned_candidates = 0
            async for item in source.search(query, http=http, credentials=self.config.credentials):
                scanned_candidates += 1
                if scanned_candidates > sub.max_scan_candidates:
                    result.aborted_reason = "scan_limit_reached"
                    break
                if self.library.exists(item.source, item.source_id):
                    result.skipped_duplicate += 1
                    if sub.crawl_strategy == "incremental_strict":
                        result.aborted_reason = "duplicate_hit"
                        break
                    continue
                if not matches_format(item.file_ext, sub.formats) or not matches_aspect_ratio(
                    item.width,
                    item.height,
                    sub.aspect_ratio,
                    self.config.crawl.aspect_tolerance,
                ):
                    result.skipped_filter += 1
                    continue
                if sub.crawl_strategy == "random":
                    random_candidates.append(item)
                    continue

                await self._download_item(source, item, sub, http, result, progress)
                if result.downloaded >= self.config.crawl.per_subscription_max:
                    result.aborted_reason = "quota_reached"
                    break

            if (
                sub.crawl_strategy == "random"
                and result.aborted_reason not in {"error", "quota_reached"}
            ):
                random.shuffle(random_candidates)
                for item in random_candidates:
                    await self._download_item(source, item, sub, http, result, progress)
                    if result.downloaded >= self.config.crawl.per_subscription_max:
                        result.aborted_reason = "quota_reached"
                        break
        except SourceAuthError as exc:
            result.aborted_reason = "error"
            result.failures.append(f"auth: {exc}")
        except SourceError as exc:
            result.aborted_reason = "error"
            result.failures.append(str(exc))

        await self._emit(
            progress,
            ProgressEvent(
                type="sub_finished",
                subscription_id=sub.id,
                subscription_name=sub.name,
                downloaded=result.downloaded,
                target=self.config.crawl.per_subscription_max,
                message=result.aborted_reason,
            ),
        )
        return result

    async def _download_item(
        self,
        source: Source,
        item: CandidateItem,
        sub: Subscription,
        http: HttpClientLike,
        result: SubscriptionResult,
        progress: ProgressCallback,
    ) -> None:
        tmp = self._tmp_path(item.source, item.source_id, item.file_ext)
        try:
            await source.download(item, tmp, http=http)
            record = self.library.import_downloaded(item, sub, tmp, int(time.time()))
            self.hook_runner.run_post_download(record.path)
            result.downloaded += 1
            await self._emit(
                progress,
                ProgressEvent(
                    type="sub_progress",
                    subscription_id=sub.id,
                    subscription_name=sub.name,
                    downloaded=result.downloaded,
                    target=self.config.crawl.per_subscription_max,
                ),
            )
        except Exception as exc:
            result.failures.append(str(exc))
            tmp.unlink(missing_ok=True)

    def _tmp_path(self, source: str, source_id: str, file_ext: str) -> Path:
        return self.library.wallpaper_dir / f"{source}_{source_id}.{file_ext}.part"

    @staticmethod
    async def _emit(progress: ProgressCallback, event: ProgressEvent) -> None:
        if progress is not None:
            result = progress(event)
            if inspect.isawaitable(result):
                await result

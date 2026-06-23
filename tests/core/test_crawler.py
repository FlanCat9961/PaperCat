from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from papercat.core.config import Config, CrawlConfig, HookConfig, NotificationConfig
from papercat.core.crawler import Crawler, ProgressEvent
from papercat.core.exceptions import SourceAuthError
from papercat.core.hook import HookRunner
from papercat.core.library import Library
from papercat.core.lock import ProcessLock
from papercat.core.notifier import Notifier
from papercat.core.sources.base import CandidateItem, HttpClientLike, SearchQuery, Source
from papercat.core.sources.registry import SourceRegistry
from papercat.core.subscription import Subscription
from papercat.core.types import AspectRatio, NsfwLevel, Resolution


class FakeSource(Source):
    id = "fake"
    display_name = "Fake"
    requires_api_key_for_nsfw = False
    default_min_interval_sec = 0.0

    def __init__(self) -> None:
        super().__init__()
        self.items: list[CandidateItem] = []
        self.auth_error = False
        self.queries: list[SearchQuery] = []

    async def search(
        self,
        q: SearchQuery,
        *,
        http: HttpClientLike,
        credentials,
    ) -> AsyncIterator[CandidateItem]:
        del http, credentials
        self.queries.append(q)
        if self.auth_error:
            raise SourceAuthError("missing key")
        for item in self.items:
            yield item

    async def download(self, item: CandidateItem, dst_part: Path, *, http: HttpClientLike) -> None:
        dst_part.parent.mkdir(parents=True, exist_ok=True)
        dst_part.write_bytes(item.source_id.encode("utf-8"))


def candidate(source_id: str, file_ext: str = "jpg", width: int = 1920) -> CandidateItem:
    return CandidateItem(
        source="fake",
        source_id=source_id,
        url=f"https://example.invalid/{source_id}",
        width=width,
        height=1080,
        file_ext=file_ext,
        nsfw_level=NsfwLevel.SFW,
        tags=["cat"],
        original_url=f"https://example.invalid/post/{source_id}",
    )


def subscription() -> Subscription:
    return Subscription(
        id=1,
        name="Sub",
        source="fake",
        include_tags=["cat"],
        resolution=Resolution(1920, 1080),
        aspect_ratio=AspectRatio(16, 9),
        formats=["jpg"],
    )


def make_crawler(tmp_path, fake_source: FakeSource, per_subscription_max: int = 2) -> Crawler:
    registry = SourceRegistry()
    registry._sources[fake_source.id] = fake_source
    config = Config(
        crawl=CrawlConfig(
            per_subscription_max=per_subscription_max,
            max_concurrent_subscriptions=1,
            request_timeout_seconds=1,
            retry_attempts=0,
        ),
        notifications=NotificationConfig(enabled=False),
        hook=HookConfig(),
    )
    library = Library(tmp_path / "db.sqlite3", tmp_path / "wallpapers", tmp_path / "thumbs")
    library.init_schema()
    return Crawler(
        config=config,
        library=library,
        source_registry=registry,
        hook_runner=HookRunner(config.hook, tmp_path / "wallpapers"),
        notifier=Notifier(config.notifications),
        lock=ProcessLock(tmp_path / "crawl.lock"),
        logger=logging.getLogger("test"),
    )


@pytest.mark.asyncio
async def test_crawl_downloads_until_quota_and_emits_progress(tmp_path) -> None:
    fake = FakeSource()
    fake.items = [candidate("1"), candidate("2"), candidate("3")]
    crawler = make_crawler(tmp_path, fake, per_subscription_max=2)
    events: list[ProgressEvent] = []

    report = await crawler.crawl([subscription()], progress=events.append)

    assert report.total_downloaded == 2
    assert report.results[0].aborted_reason == "quota_reached"
    assert [event.type for event in events] == [
        "crawl_started",
        "sub_started",
        "sub_progress",
        "sub_progress",
        "sub_finished",
        "crawl_finished",
    ]


@pytest.mark.asyncio
async def test_incremental_strict_duplicate_hit_aborts_subscription(tmp_path) -> None:
    fake = FakeSource()
    fake.items = [candidate("1"), candidate("2")]
    crawler = make_crawler(tmp_path, fake, per_subscription_max=5)
    part = tmp_path / "existing.part"
    part.write_bytes(b"existing")
    crawler.library.import_downloaded(candidate("1"), subscription(), part, 1)

    strict = subscription().model_copy(update={"crawl_strategy": "incremental_strict"})

    report = await crawler.crawl([strict])

    assert report.results[0].downloaded == 0
    assert report.results[0].skipped_duplicate == 1
    assert report.results[0].aborted_reason == "duplicate_hit"


@pytest.mark.asyncio
async def test_latest_fill_skips_duplicates_and_fills_quota(tmp_path) -> None:
    fake = FakeSource()
    fake.items = [candidate("1"), candidate("2"), candidate("3")]
    crawler = make_crawler(tmp_path, fake, per_subscription_max=2)
    part = tmp_path / "existing.part"
    part.write_bytes(b"existing")
    crawler.library.import_downloaded(candidate("1"), subscription(), part, 1)

    report = await crawler.crawl([subscription()])

    result = report.results[0]
    assert result.downloaded == 2
    assert result.skipped_duplicate == 1
    assert result.aborted_reason == "quota_reached"


@pytest.mark.asyncio
async def test_random_strategy_downloads_from_candidate_pool(
    tmp_path, monkeypatch
) -> None:
    fake = FakeSource()
    fake.items = [candidate("1"), candidate("2"), candidate("3")]
    crawler = make_crawler(tmp_path, fake, per_subscription_max=2)
    part = tmp_path / "existing.part"
    part.write_bytes(b"existing")
    crawler.library.import_downloaded(candidate("1"), subscription(), part, 1)
    monkeypatch.setattr("papercat.core.crawler.random.shuffle", lambda items: items.reverse())

    report = await crawler.crawl([subscription().model_copy(update={"crawl_strategy": "random"})])

    result = report.results[0]
    assert result.downloaded == 2
    assert result.skipped_duplicate == 1
    assert result.aborted_reason == "quota_reached"
    assert crawler.library.exists("fake", "2")
    assert crawler.library.exists("fake", "3")


@pytest.mark.asyncio
async def test_scan_limits_stop_latest_fill(tmp_path) -> None:
    fake = FakeSource()
    fake.items = [candidate("1"), candidate("2"), candidate("3")]
    crawler = make_crawler(tmp_path, fake, per_subscription_max=3)
    limited = subscription().model_copy(update={"max_scan_candidates": 1, "max_scan_pages": 2})

    report = await crawler.crawl([limited])

    assert report.results[0].downloaded == 1
    assert report.results[0].aborted_reason == "scan_limit_reached"
    assert fake.queries[0].max_pages == 2


@pytest.mark.asyncio
async def test_filter_counts_format_and_aspect_misses(tmp_path) -> None:
    fake = FakeSource()
    fake.items = [candidate("png", "png"), candidate("wide", "jpg", width=3000)]
    crawler = make_crawler(tmp_path, fake, per_subscription_max=5)

    report = await crawler.crawl([subscription()])

    assert report.results[0].skipped_filter == 2
    assert report.results[0].downloaded == 0
    assert report.results[0].aborted_reason == "exhausted"


@pytest.mark.asyncio
async def test_source_auth_error_is_recorded(tmp_path) -> None:
    fake = FakeSource()
    fake.auth_error = True
    crawler = make_crawler(tmp_path, fake)

    report = await crawler.crawl([subscription()])

    assert report.results[0].aborted_reason == "error"
    assert report.results[0].failures == ["auth: missing key"]

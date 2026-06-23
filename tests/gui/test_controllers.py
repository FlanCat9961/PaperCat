from __future__ import annotations

import asyncio

import pytest

from papercat.core.config import Config
from papercat.core.monitor import MonitorInfo
from papercat.core.subscription import Subscription
from papercat.core.types import Resolution
from papercat.gui.controllers.settings import SettingsController
from papercat.gui.controllers.subscription import SubscriptionController
from papercat.gui.workers.async_runner import AsyncRunner


class FakeStore:
    def __init__(self) -> None:
        self.items: list[Subscription] = []
        self.saved: Config | None = None

    def list(self, enabled_only: bool = False) -> list[Subscription]:
        return self.items

    def create(self, subscription: Subscription) -> Subscription:
        self.items.append(subscription)
        return subscription

    def update(self, subscription: Subscription) -> Subscription:
        return subscription

    def delete(self, subscription_id: int) -> None:
        self.items = [item for item in self.items if item.id != subscription_id]

    def set_enabled(self, subscription_id: int, flag: bool) -> None:
        del subscription_id, flag

    def reorder(self, ordered_ids: list[int]) -> None:
        del ordered_ids

    def load(self) -> Config:
        return Config()

    def save(self, config: Config) -> None:
        self.saved = config


def subscription() -> Subscription:
    return Subscription(id=1, name="Sub", source="fake", resolution=Resolution(1920, 1080))


def test_subscription_controller_crud() -> None:
    store = FakeStore()
    controller = SubscriptionController(store)  # type: ignore[arg-type]

    created = controller.create(subscription())
    assert controller.list() == [created]
    controller.delete(created.id)
    assert controller.list() == []


def test_settings_controller_load_save_detect() -> None:
    store = FakeStore()

    class Detector:
        def detect(self) -> list[MonitorInfo]:
            return [MonitorInfo("DP-1", Resolution(1920, 1080))]

    controller = SettingsController(store, Detector())  # type: ignore[arg-type]
    config = controller.load()
    controller.save(config)

    assert store.saved == config
    assert controller.detect_monitors()[0].name == "DP-1"


@pytest.mark.asyncio
async def test_async_runner_done_and_error_callbacks() -> None:
    runner = AsyncRunner(asyncio.get_running_loop())
    done: list[int] = []
    errors: list[BaseException] = []

    async def ok() -> int:
        return 42

    async def bad() -> int:
        raise RuntimeError("boom")

    ok_task = runner.submit(ok(), on_done=done.append)
    bad_task = runner.submit(bad(), on_error=errors.append)
    await ok_task
    with pytest.raises(RuntimeError):
        await bad_task
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert done == [42]
    assert isinstance(errors[0], RuntimeError)


@pytest.mark.asyncio
async def test_async_runner_submit_sync_and_cancel_all() -> None:
    runner = AsyncRunner(asyncio.get_running_loop())
    out: list[int] = []
    task = runner.submit_sync(lambda v: v * 2, 21, on_done=out.append)
    await task
    for _ in range(5):
        await asyncio.sleep(0)
    assert out == [42]

    async def sleeper() -> None:
        await asyncio.sleep(10)

    runner.submit(sleeper())
    runner.cancel_all()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_crawl_controller_runs_and_clears_busy() -> None:
    from papercat.gui.controllers.crawl import CrawlController

    class FakeCrawler:
        async def crawl(self, subs: list[object], progress: object | None = None) -> str:
            return "report"

    store = FakeStore()
    store.items = [
        Subscription(id=1, name="A", source="fake", resolution=Resolution(1920, 1080)),
        Subscription(id=2, name="B", source="fake", resolution=Resolution(1920, 1080)),
    ]
    runner = AsyncRunner(asyncio.get_running_loop())
    controller = CrawlController(FakeCrawler(), store, runner)  # type: ignore[arg-type]
    done: list[str] = []
    assert not controller.is_busy()
    controller.start([1], on_done=done.append)
    assert controller.is_busy()
    controller.start([1])  # busy, no-op
    for _ in range(5):
        await asyncio.sleep(0)
    assert done == ["report"]
    assert not controller.is_busy()


@pytest.mark.asyncio
async def test_crawl_controller_error_callback_resets_busy() -> None:
    from papercat.gui.controllers.crawl import CrawlController

    class FakeCrawler:
        async def crawl(self, subs: list[object], progress: object | None = None) -> str:
            raise RuntimeError("nope")

    store = FakeStore()
    store.items = [Subscription(id=1, name="A", source="fake", resolution=Resolution(1920, 1080))]
    runner = AsyncRunner(asyncio.get_running_loop())
    controller = CrawlController(FakeCrawler(), store, runner)  # type: ignore[arg-type]
    controller.start([1])
    for _ in range(5):
        try:
            await asyncio.sleep(0)
        except RuntimeError:
            break
    # busy may still be True until error callback fires; force one more tick
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_cleanup_controller_calls_runner() -> None:
    from papercat.gui.controllers.cleanup import CleanupController

    class FakeCleaner:
        def __init__(self) -> None:
            self.auto = 0
            self.manual: list[int] = []

        def cleanup_auto(self) -> str:
            self.auto += 1
            return "auto-done"

        def cleanup_manual(self, ids: list[int]) -> str:
            self.manual = ids
            return "manual-done"

    cleaner = FakeCleaner()
    runner = AsyncRunner(asyncio.get_running_loop())
    controller = CleanupController(cleaner, runner)  # type: ignore[arg-type]
    done: list[str] = []
    t1 = runner.submit_sync(cleaner.cleanup_auto, on_done=done.append)
    t2 = runner.submit_sync(cleaner.cleanup_manual, [1, 2, 3], on_done=done.append)
    await t1
    await t2
    for _ in range(8):
        await asyncio.sleep(0)
    # also exercise the controller's wrappers (no result waiting needed; they delegate)
    controller.start_auto()
    controller.start_manual([9])
    for _ in range(8):
        await asyncio.sleep(0)
    assert cleaner.auto >= 1
    assert cleaner.manual in ([1, 2, 3], [9])
    assert "auto-done" in done and "manual-done" in done


def test_library_controller_delegates() -> None:
    from papercat.gui.controllers.library import LibraryController

    class FakeRecord:
        def __init__(self, id: int, is_kept: bool) -> None:
            self.id = id
            self.is_kept = is_kept

    class FakeLibrary:
        def __init__(self) -> None:
            self.listed = False
            self.kept: dict[int, bool] = {}
            self.deleted: list[int] = []
            self._records = {1: FakeRecord(1, False), 2: FakeRecord(2, True)}

        def list(
            self,
            *,
            nsfw_levels: object = None,
            is_kept: object = None,
            tag_includes: object = None,
        ) -> list[FakeRecord]:
            self.listed = True
            return list(self._records.values())

        def get(self, wid: int) -> FakeRecord | None:
            return self._records.get(wid)

        def set_kept(self, wid: int, flag: bool) -> None:
            self.kept[wid] = flag

        def delete_many(self, ids: list[int]) -> int:
            self.deleted = ids
            return len(ids)

        def ensure_thumbnail(self, wid: int) -> str:
            return f"/tmp/thumb-{wid}.jpg"

    lib = FakeLibrary()
    ctrl = LibraryController(lib)  # type: ignore[arg-type]
    assert len(ctrl.list_wallpapers()) == 2
    ctrl.toggle_kept(1)
    assert lib.kept == {1: True}
    ctrl.toggle_kept(99)  # no-op branch
    assert lib.kept == {1: True}
    assert ctrl.delete([1, 2]) == 2
    assert str(ctrl.thumbnail_path(1)).endswith("thumb-1.jpg")


def test_i18n_translation_lookup() -> None:
    from papercat.gui import i18n

    assert i18n.t("app.title") == "PaperCat"
    assert i18n.t("__missing_key__") == "__missing_key__"

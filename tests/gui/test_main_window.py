from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from papercat.core.config import Config, ConfigStore
from papercat.core.subscription import Subscription
from papercat.core.types import AspectRatio, NsfwLevel, Resolution
from papercat.gui.controllers.library import LibraryController
from papercat.gui.controllers.settings import SettingsController
from papercat.gui.controllers.subscription import SubscriptionController


class FakeWallpaperRecord:
    def __init__(self, wid: int) -> None:
        self.id = wid
        self.source = "fake"
        self.source_id = f"s{wid}"
        self.filename = f"wp-{wid}.jpg"
        self.subscription_id = None
        self.subscription_name = "Sub"
        self.width = 1920
        self.height = 1080
        self.file_ext = "jpg"
        self.tags = ["cat"]
        self.nsfw_level = NsfwLevel.SFW
        self.download_time = 0
        self.is_kept = False
        self.original_url = None


class FakeLibrary:
    def __init__(self) -> None:
        self.records = [FakeWallpaperRecord(1), FakeWallpaperRecord(2)]
        self.deleted: list[int] = []
        self.kept: dict[int, bool] = {}

    def list(self, **kwargs: object) -> list[FakeWallpaperRecord]:
        return list(self.records)

    def get(self, wid: int) -> FakeWallpaperRecord | None:
        return next((r for r in self.records if r.id == wid), None)

    def set_kept(self, wid: int, flag: bool) -> None:
        self.kept[wid] = flag

    def delete_many(self, ids: list[int]) -> int:
        self.deleted.extend(ids)
        self.records = [r for r in self.records if r.id not in set(ids)]
        return len(ids)

    def ensure_thumbnail(self, wid: int) -> Path:
        raise RuntimeError("thumbnail unavailable in smoke test")


class FakeSubStore:
    def __init__(self) -> None:
        self.items = [
            Subscription(
                id=1,
                name="anime",
                source="wallhaven",
                include_tags=["cat"],
                resolution=Resolution(1920, 1080),
                aspect_ratio=AspectRatio(16, 9),
            ),
        ]

    def list(self, enabled_only: bool = False) -> list[Subscription]:
        return list(self.items)

    def create(self, sub: Subscription) -> Subscription:
        self.items.append(sub)
        return sub

    def update(self, sub: Subscription) -> Subscription:
        return sub

    def delete(self, sub_id: int) -> None:
        self.items = [s for s in self.items if s.id != sub_id]

    def set_enabled(self, sub_id: int, flag: bool) -> None:
        del sub_id, flag

    def reorder(self, ids: list[int]) -> None:
        del ids


class FakeDetector:
    def all_resolutions(self, user_resolutions: list[Resolution]) -> list[Resolution]:
        return [Resolution(2560, 1440)]

    def detect(self) -> list[object]:
        return []


class FakeCrawlCtrl:
    def __init__(self) -> None:
        self.started_with: list[int] | None = None

    def is_busy(self) -> bool:
        return False

    def start(self, sub_ids: list[int], on_progress=None, on_done=None) -> None:
        self.started_with = sub_ids
        if on_done is not None:

            class Report:
                total_downloaded = 3
                total_failures = 0

            on_done(Report())


class FakeAppControllers:
    def __init__(self, tmp_path: Path) -> None:
        store = FakeSubStore()
        sub_ctrl = SubscriptionController(store)  # type: ignore[arg-type]
        config_store = ConfigStore(tmp_path / "config.toml")
        config = config_store.load()
        self.config = config
        self.config_store = config_store
        self.library = LibraryController(FakeLibrary())  # type: ignore[arg-type]
        self.subscription = sub_ctrl
        self.settings = SettingsController(config_store, FakeDetector())  # type: ignore[arg-type]
        self.crawl = FakeCrawlCtrl()
        self.cleanup = None
        self.async_runner = None
        self.monitor_detector = FakeDetector()


@pytest.fixture
def qt_app(qtbot):  # type: ignore[no-untyped-def]
    return qtbot


def test_main_window_builds_and_refreshes(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from papercat.gui.windows.main import MainWindow

    controllers = FakeAppControllers(tmp_path)
    window = MainWindow(controllers=controllers)  # type: ignore[arg-type]
    qtbot.addWidget(window)
    assert window.model.rowCount() == 2
    assert window.sidebar.subscriptions.count() == 1


def test_settings_dialog_round_trip(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from papercat.gui.windows.settings import SettingsDialog

    config_store = ConfigStore(tmp_path / "config.toml")
    ctrl = SettingsController(config_store, FakeDetector())  # type: ignore[arg-type]

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.bind(ctrl)
    dialog.wallpaper_dir.setText(str(tmp_path / "wp"))
    dialog.non_kept_limit.setValue(99)
    dialog._on_accept()

    saved: Config = config_store.load()
    assert saved.non_kept_limit == 99
    assert saved.wallpaper_dir == tmp_path / "wp"


def test_subscription_editor_builds_subscription(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from papercat.gui.windows.subscription_editor import SubscriptionEditorDialog

    controllers = FakeAppControllers(tmp_path)
    dialog = SubscriptionEditorDialog()
    qtbot.addWidget(dialog)
    dialog.bind(controllers)  # type: ignore[arg-type]
    dialog.name.setText("test-sub")
    dialog.include_tags.setText("cat, anime")
    dialog.exclude_tags.setText("dog")
    dialog.aspect_ratio.setText("16:9")
    idx = dialog.crawl_strategy.findData("random")
    dialog.crawl_strategy.setCurrentIndex(idx)
    dialog.max_scan_pages.setValue(8)
    dialog.max_scan_candidates.setValue(321)

    sub = dialog.build_subscription()
    assert sub is not None
    assert sub.name == "test-sub"
    assert sub.include_tags == ["cat", "anime"]
    assert sub.exclude_tags == ["dog"]
    assert sub.aspect_ratio == AspectRatio(16, 9)
    assert sub.crawl_strategy == "random"
    assert sub.max_scan_pages == 8
    assert sub.max_scan_candidates == 321


def test_main_window_crawl_button_starts_crawl(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from papercat.gui.windows.main import MainWindow

    controllers = FakeAppControllers(tmp_path)
    window = MainWindow(controllers=controllers)  # type: ignore[arg-type]
    qtbot.addWidget(window)
    monkeypatched: list[str] = []

    def fake_info(*args: object, **kwargs: object) -> int:
        monkeypatched.append("info")
        return 0

    from PySide6.QtWidgets import QMessageBox

    QMessageBox.information = fake_info  # type: ignore[assignment]
    window._on_crawl_clicked()
    assert controllers.crawl.started_with == [1]


def test_subscription_editor_invalid_aspect_returns_none(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QMessageBox

    from papercat.gui.windows.subscription_editor import SubscriptionEditorDialog

    controllers = FakeAppControllers(tmp_path)
    dialog = SubscriptionEditorDialog()
    qtbot.addWidget(dialog)
    dialog.bind(controllers)  # type: ignore[arg-type]
    dialog.name.setText("bad")
    dialog.aspect_ratio.setText("not a ratio")

    QMessageBox.warning = lambda *a, **k: 0  # type: ignore[assignment]
    assert dialog.build_subscription() is None

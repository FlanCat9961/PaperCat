from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import qasync
from PySide6.QtWidgets import QApplication

from papercat.core.cleaner import Cleaner
from papercat.core.config import Config, ConfigStore
from papercat.core.crawler import Crawler
from papercat.core.hook import HookRunner
from papercat.core.library import Library
from papercat.core.lock import ProcessLock
from papercat.core.logger import setup_logger
from papercat.core.monitor import MonitorDetector
from papercat.core.notifier import Notifier
from papercat.core.paths import DB_FILE, LOCK_FILE, LOG_DIR, THUMB_DIR
from papercat.core.sources import DEFAULT_REGISTRY
from papercat.core.subscription import SubscriptionStore
from papercat.gui.controllers.cleanup import CleanupController
from papercat.gui.controllers.crawl import CrawlController
from papercat.gui.controllers.library import LibraryController
from papercat.gui.controllers.settings import SettingsController
from papercat.gui.controllers.subscription import SubscriptionController
from papercat.gui.windows.main import MainWindow
from papercat.gui.workers.async_runner import AsyncRunner


@dataclass
class AppControllers:
    config: Config
    config_store: ConfigStore
    library: LibraryController
    crawl: CrawlController
    cleanup: CleanupController
    subscription: SubscriptionController
    settings: SettingsController
    async_runner: AsyncRunner
    monitor_detector: MonitorDetector


def build_controllers(loop: asyncio.AbstractEventLoop) -> AppControllers:
    config_store = ConfigStore()
    config = config_store.load()

    logger = setup_logger("papercat", LOG_DIR, process_tag="gui")
    library = Library(DB_FILE, config.wallpaper_dir, THUMB_DIR)
    library.init_schema()

    notifier = Notifier(config.notifications)
    hook_runner = HookRunner(config.hook, config.wallpaper_dir)
    lock = ProcessLock(LOCK_FILE)
    monitor_detector = MonitorDetector()

    crawler = Crawler(
        config=config,
        library=library,
        source_registry=DEFAULT_REGISTRY,
        hook_runner=hook_runner,
        notifier=notifier,
        lock=lock,
        logger=logger,
    )
    cleaner = Cleaner(
        config=config,
        library=library,
        notifier=notifier,
        lock=lock,
        logger=logger,
    )
    subscription_store = SubscriptionStore(source_registry=DEFAULT_REGISTRY)
    async_runner = AsyncRunner(loop)

    return AppControllers(
        config=config,
        config_store=config_store,
        library=LibraryController(library),
        crawl=CrawlController(crawler, subscription_store, async_runner),
        cleanup=CleanupController(cleaner, async_runner),
        subscription=SubscriptionController(subscription_store),
        settings=SettingsController(config_store, monitor_detector),
        async_runner=async_runner,
        monitor_detector=monitor_detector,
    )


def main() -> int:
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    qss = Path(__file__).parent / "theme" / "mocha.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))

    controllers = build_controllers(loop)
    window = MainWindow(controllers=controllers)
    window.show()

    with loop:
        return loop.run_forever() or 0

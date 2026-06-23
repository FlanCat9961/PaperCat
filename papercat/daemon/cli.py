from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence

from papercat.core.cleaner import Cleaner
from papercat.core.config import Config, ConfigStore
from papercat.core.crawler import Crawler
from papercat.core.exceptions import ConfigError, LockBusyError
from papercat.core.hook import HookRunner
from papercat.core.library import Library
from papercat.core.lock import ProcessLock
from papercat.core.logger import setup_logger
from papercat.core.monitor import MonitorDetector
from papercat.core.notifier import Notifier
from papercat.core.paths import DB_FILE, LOCK_FILE, LOG_DIR, THUMB_DIR
from papercat.core.sources import DEFAULT_REGISTRY
from papercat.core.subscription import Subscription, SubscriptionStore

VERSION = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="papercat-daemon")
    parser.add_argument("--version", action="version", version=f"PaperCat {VERSION}")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    crawl = subparsers.add_parser("crawl")
    group = crawl.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true")
    group.add_argument("--subscription", action="append", default=[])

    subparsers.add_parser("cleanup")
    subparsers.add_parser("scan-monitors")
    return parser


def _build_crawler(cfg: Config, logger: logging.Logger) -> Crawler:
    library = Library(DB_FILE, cfg.wallpaper_dir, THUMB_DIR)
    library.init_schema()
    notifier = Notifier(cfg.notifications)
    return Crawler(
        config=cfg,
        library=library,
        source_registry=DEFAULT_REGISTRY,
        hook_runner=HookRunner(cfg.hook, cfg.wallpaper_dir),
        notifier=notifier,
        lock=ProcessLock(LOCK_FILE),
        logger=logger,
    )


def _build_cleaner(cfg: Config, logger: logging.Logger) -> Cleaner:
    library = Library(DB_FILE, cfg.wallpaper_dir, THUMB_DIR)
    library.init_schema()
    notifier = Notifier(cfg.notifications)
    return Cleaner(
        config=cfg,
        library=library,
        notifier=notifier,
        lock=ProcessLock(LOCK_FILE),
        logger=logger,
    )


def _select_subs(args: argparse.Namespace, store: SubscriptionStore) -> list[Subscription]:
    subscriptions = store.list(enabled_only=True)
    requested = set(args.subscription or [])
    if args.all or not requested:
        return subscriptions
    selected = [subscription for subscription in subscriptions if subscription.name in requested]
    missing = requested - {subscription.name for subscription in selected}
    if missing:
        raise ConfigError(f"unknown subscription(s): {', '.join(sorted(missing))}")
    return selected


def _scan_monitors() -> int:
    monitors = MonitorDetector().detect()
    payload = [
        {
            "name": monitor.name,
            "width": monitor.resolution.width,
            "height": monitor.resolution.height,
        }
        for monitor in monitors
    ]
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        cfg = ConfigStore().load()
        logger = setup_logger("papercat", LOG_DIR, process_tag="daemon")
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 3

    try:
        if args.cmd == "crawl":
            store = SubscriptionStore(source_registry=DEFAULT_REGISTRY)
            subs = _select_subs(args, store)
            report = asyncio.run(_build_crawler(cfg, logger).crawl(subs))
            return 0 if report.total_failures == 0 else 1
        if args.cmd == "cleanup":
            _build_cleaner(cfg, logger).cleanup_auto()
            return 0
        if args.cmd == "scan-monitors":
            return _scan_monitors()
        parser.error("missing command")
    except LockBusyError:
        return 2
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 3
    except Exception:
        logger.exception("unhandled daemon error")
        return 4
    return 4

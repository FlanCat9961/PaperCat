import logging
from dataclasses import dataclass
from pathlib import Path

import pytest

from papercat.core.cleaner import Cleaner
from papercat.core.config import Config, NotificationConfig
from papercat.core.exceptions import LockBusyError
from papercat.core.library import Library
from papercat.core.lock import ProcessLock
from papercat.core.notifier import Notifier
from papercat.core.sources.base import CandidateItem
from papercat.core.types import NsfwLevel


@dataclass
class FakeSubscription:
    id: int = 1
    name: str = "Sub"


def candidate(source_id: str) -> CandidateItem:
    return CandidateItem(
        source="fake",
        source_id=source_id,
        url="https://example.invalid/image.jpg",
        width=1920,
        height=1080,
        file_ext="jpg",
        nsfw_level=NsfwLevel.SFW,
        tags=[],
        original_url="https://example.invalid/post",
    )


def import_one(library: Library, tmp_path: Path, source_id: str, download_time: int) -> int:
    part = tmp_path / f"{source_id}.part"
    part.write_bytes(b"image")
    return library.import_downloaded(
        candidate(source_id), FakeSubscription(), part, download_time
    ).id


def make_cleaner(tmp_path, non_kept_limit: int) -> Cleaner:
    config = Config(non_kept_limit=non_kept_limit, notifications=NotificationConfig(enabled=False))
    library = Library(tmp_path / "db.sqlite3", tmp_path / "wallpapers", tmp_path / "thumbs")
    library.init_schema()
    return Cleaner(
        config=config,
        library=library,
        notifier=Notifier(config.notifications),
        lock=ProcessLock(tmp_path / "clean.lock"),
        logger=logging.getLogger("test"),
    )


def test_auto_noop_when_under_limit(tmp_path) -> None:
    cleaner = make_cleaner(tmp_path, non_kept_limit=2)
    import_one(cleaner.library, tmp_path, "1", 1)

    report = cleaner.cleanup_auto()

    assert report.result.deleted_count == 0
    assert cleaner.library.count_non_kept() == 1


def test_auto_deletes_oldest_excess(tmp_path) -> None:
    cleaner = make_cleaner(tmp_path, non_kept_limit=1)
    old = import_one(cleaner.library, tmp_path, "old", 1)
    new = import_one(cleaner.library, tmp_path, "new", 2)

    report = cleaner.cleanup_auto()

    assert report.result.deleted_count == 1
    assert cleaner.library.get(old) is None
    assert cleaner.library.get(new) is not None


def test_auto_does_not_delete_kept_records(tmp_path) -> None:
    cleaner = make_cleaner(tmp_path, non_kept_limit=1)
    kept = import_one(cleaner.library, tmp_path, "kept", 1)
    cleaner.library.set_kept(kept, True)

    report = cleaner.cleanup_auto()

    assert report.result.deleted_count == 0
    assert cleaner.library.get(kept) is not None


def test_manual_skips_kept_records(tmp_path) -> None:
    cleaner = make_cleaner(tmp_path, non_kept_limit=10)
    kept = import_one(cleaner.library, tmp_path, "kept", 1)
    safe = import_one(cleaner.library, tmp_path, "safe", 2)
    cleaner.library.set_kept(kept, True)

    report = cleaner.cleanup_manual([kept, safe])

    assert report.result.deleted_count == 1
    assert report.result.skipped_kept == 1
    assert cleaner.library.get(kept) is not None
    assert cleaner.library.get(safe) is None


def test_lock_busy_error_is_not_swallowed(tmp_path) -> None:
    cleaner = make_cleaner(tmp_path, non_kept_limit=1)
    busy_lock = ProcessLock(tmp_path / "clean.lock")
    busy_lock.acquire()
    try:
        with pytest.raises(LockBusyError):
            cleaner.cleanup_auto()
    finally:
        busy_lock.release()

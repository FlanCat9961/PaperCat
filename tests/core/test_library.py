from dataclasses import dataclass

import pytest

from papercat.core.exceptions import LibraryError
from papercat.core.library import Library
from papercat.core.types import NsfwLevel


@dataclass
class FakeCandidate:
    source: str = "fake"
    source_id: str = "1"
    width: int = 1920
    height: int = 1080
    file_ext: str = "jpg"
    tags: list[str] | None = None
    nsfw_level: NsfwLevel = NsfwLevel.SFW
    original_url: str = "https://example.invalid/1"

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = ["cat", "sky"]


@dataclass
class FakeSubscription:
    id: int = 7
    name: str = "Sub"


def make_library(tmp_path) -> Library:
    return Library(tmp_path / "library.db", tmp_path / "wallpapers", tmp_path / "thumbs")


def import_one(library: Library, tmp_path, source_id: str = "1", download_time: int = 100):
    part = tmp_path / f"{source_id}.part"
    part.write_bytes(b"image")
    return library.import_downloaded(
        FakeCandidate(source_id=source_id), FakeSubscription(), part, download_time
    )


def test_init_schema_is_idempotent(tmp_path) -> None:
    library = make_library(tmp_path)

    library.init_schema()
    library.init_schema()

    assert library.count_non_kept() == 0


def test_import_downloaded_renames_and_inserts(tmp_path) -> None:
    library = make_library(tmp_path)
    record = import_one(library, tmp_path)

    assert record.id == 1
    assert record.path.exists()
    assert record.filename == "fake_1.jpg"
    assert library.exists("fake", "1") is True


def test_import_duplicate_cleans_target_and_raises(tmp_path) -> None:
    library = make_library(tmp_path)
    import_one(library, tmp_path)
    part = tmp_path / "duplicate.part"
    part.write_bytes(b"duplicate")

    with pytest.raises(LibraryError):
        library.import_downloaded(FakeCandidate(source_id="1"), FakeSubscription(), part, 101)

    assert (tmp_path / "wallpapers" / "fake_1.jpg").read_bytes() == b"image"


def test_list_filters(tmp_path) -> None:
    library = make_library(tmp_path)
    first = import_one(library, tmp_path, "1", 100)
    second = import_one(library, tmp_path, "2", 200)
    library.set_kept(second.id, True)

    records = library.list(subscription_id=7, nsfw_levels={NsfwLevel.SFW}, tag_includes=["cat"])
    assert records[0].id == second.id
    assert library.list(is_kept=False) == [first]


def test_count_oldest_and_set_kept(tmp_path) -> None:
    library = make_library(tmp_path)
    first = import_one(library, tmp_path, "1", 100)
    second = import_one(library, tmp_path, "2", 200)

    assert library.count_non_kept() == 2
    assert [record.id for record in library.oldest_non_kept(2)] == [first.id, second.id]

    library.set_kept(first.id, True)
    assert library.count_non_kept() == 1


def test_delete_removes_file_thumbnail_and_db_row(tmp_path) -> None:
    library = make_library(tmp_path)
    record = import_one(library, tmp_path)
    thumb = tmp_path / "thumbs" / f"{record.id}.webp"
    thumb.parent.mkdir()
    thumb.write_bytes(b"thumb")

    assert library.delete(record.id) is True
    assert library.get(record.id) is None
    assert not record.path.exists()
    assert not thumb.exists()


def test_reap_orphans_cleans_files_and_db_rows(tmp_path) -> None:
    library = make_library(tmp_path)
    record = import_one(library, tmp_path)
    orphan = tmp_path / "wallpapers" / "orphan.jpg"
    orphan.write_bytes(b"orphan")
    part = tmp_path / "wallpapers" / "stale.part"
    part.write_bytes(b"part")
    record.path.unlink()

    assert library.reap_orphans() == (2, 1)
    assert library.get(record.id) is None
    assert not orphan.exists()
    assert not part.exists()


def test_ensure_thumbnail_generates_and_hits_cache(tmp_path) -> None:
    try:
        from PIL import Image
    except ModuleNotFoundError:
        pytest.skip("Pillow unavailable")

    library = make_library(tmp_path)
    part = tmp_path / "image.part"
    Image.new("RGB", (32, 32), color="red").save(part, "JPEG")
    record = library.import_downloaded(
        FakeCandidate(source_id="image"), FakeSubscription(), part, 100
    )

    thumb = library.ensure_thumbnail(record.id)
    modified = thumb.stat().st_mtime_ns

    assert thumb.exists()
    assert library.ensure_thumbnail(record.id).stat().st_mtime_ns == modified

from __future__ import annotations

import builtins
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from papercat.core.exceptions import LibraryError
from papercat.core.paths import THUMB_DIR
from papercat.core.types import NsfwLevel


class CandidateItemLike(Protocol):
    @property
    def source(self) -> str: ...

    @property
    def source_id(self) -> str: ...

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def file_ext(self) -> str: ...

    @property
    def tags(self) -> builtins.list[str]: ...

    @property
    def nsfw_level(self) -> NsfwLevel: ...

    @property
    def original_url(self) -> str: ...


class SubscriptionLike(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def name(self) -> str: ...


SCHEMA_V1_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO schema_version VALUES (1);

CREATE TABLE IF NOT EXISTS wallpapers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source            TEXT    NOT NULL,
    source_id         TEXT    NOT NULL,
    filename          TEXT    NOT NULL UNIQUE,
    subscription_id   INTEGER,
    subscription_name TEXT,
    width             INTEGER NOT NULL,
    height            INTEGER NOT NULL,
    file_ext          TEXT    NOT NULL,
    tags_json         TEXT    NOT NULL DEFAULT '[]',
    nsfw_level        TEXT    NOT NULL,
    download_time     INTEGER NOT NULL,
    is_kept           INTEGER NOT NULL DEFAULT 0,
    original_url      TEXT,
    UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_wallpapers_is_kept_dt ON wallpapers(is_kept, download_time);
CREATE INDEX IF NOT EXISTS idx_wallpapers_subscription ON wallpapers(subscription_id);
"""


@dataclass
class WallpaperRecord:
    id: int
    source: str
    source_id: str
    filename: str
    subscription_id: int | None
    subscription_name: str | None
    width: int
    height: int
    file_ext: str
    tags: builtins.list[str]
    nsfw_level: NsfwLevel
    download_time: int
    is_kept: bool
    original_url: str | None
    _wallpaper_dir: Path = field(repr=False, compare=False)

    @property
    def path(self) -> Path:
        return self._wallpaper_dir / self.filename


class Library:
    def __init__(self, db_path: Path, wallpaper_dir: Path, thumb_dir: Path = THUMB_DIR) -> None:
        self.db_path = db_path
        self.wallpaper_dir = wallpaper_dir
        self.thumb_dir = thumb_dir

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_V1_SQL)

    def migrate_if_needed(self) -> None:
        self.init_schema()
        with self._conn() as conn:
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        if version != 1:
            raise LibraryError(f"unsupported library schema version: {version}")

    def exists(self, source: str, source_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM wallpapers WHERE source = ? AND source_id = ? LIMIT 1",
                (source, source_id),
            ).fetchone()
        return row is not None

    def get(self, wallpaper_id: int) -> WallpaperRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM wallpapers WHERE id = ?", (wallpaper_id,)).fetchone()
        return None if row is None else self._row_to_record(row)

    def get_by_filename(self, filename: str) -> WallpaperRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM wallpapers WHERE filename = ?", (filename,)
            ).fetchone()
        return None if row is None else self._row_to_record(row)

    def list(
        self,
        *,
        subscription_id: int | None = None,
        nsfw_levels: set[NsfwLevel] | None = None,
        is_kept: bool | None = None,
        tag_includes: builtins.list[str] | None = None,
        order_by: Literal["download_time", "id"] = "download_time",
        desc: bool = True,
        limit: int | None = None,
        offset: int = 0,
    ) -> builtins.list[WallpaperRecord]:
        clauses: builtins.list[str] = []
        params: builtins.list[object] = []

        if subscription_id is not None:
            clauses.append("subscription_id = ?")
            params.append(subscription_id)
        if nsfw_levels is not None:
            if not nsfw_levels:
                return []
            placeholders = ", ".join("?" for _ in nsfw_levels)
            clauses.append(f"nsfw_level IN ({placeholders})")
            params.extend(level.value for level in nsfw_levels)
        if is_kept is not None:
            clauses.append("is_kept = ?")
            params.append(int(is_kept))
        if tag_includes:
            for tag in tag_includes:
                clauses.append(
                    "EXISTS (SELECT 1 FROM json_each(wallpapers.tags_json) WHERE value = ?)"
                )
                params.append(tag)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        direction = "DESC" if desc else "ASC"
        sql = f"SELECT * FROM wallpapers{where} ORDER BY {order_by} {direction}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)

        with self._conn() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count_non_kept(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM wallpapers WHERE is_kept = 0").fetchone()
            return int(row[0])

    def oldest_non_kept(self, n: int) -> builtins.list[WallpaperRecord]:
        return self.list(is_kept=False, order_by="download_time", desc=False, limit=n)

    def import_downloaded(
        self,
        meta: CandidateItemLike,
        subscription: SubscriptionLike,
        tmp_part_path: Path,
        download_time: int,
    ) -> WallpaperRecord:
        self.init_schema()
        filename = f"{meta.source}_{meta.source_id}.{meta.file_ext.lower().removeprefix('.')}"
        target = self.wallpaper_dir / filename
        if target.exists():
            raise LibraryError(f"wallpaper already exists on disk: {target}")

        self.wallpaper_dir.mkdir(parents=True, exist_ok=True)
        os.replace(tmp_part_path, target)
        try:
            with self._conn() as conn:
                conn.execute("BEGIN")
                conn.execute(
                    """
                    INSERT INTO wallpapers (
                        source, source_id, filename, subscription_id, subscription_name,
                        width, height, file_ext, tags_json, nsfw_level, download_time,
                        is_kept, original_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        meta.source,
                        meta.source_id,
                        filename,
                        subscription.id,
                        subscription.name,
                        meta.width,
                        meta.height,
                        meta.file_ext.lower().removeprefix("."),
                        json.dumps(meta.tags, ensure_ascii=False),
                        meta.nsfw_level.value,
                        download_time,
                        meta.original_url,
                    ),
                )
                conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            target.unlink(missing_ok=True)
            raise LibraryError(
                f"failed to import duplicate wallpaper: {meta.source}/{meta.source_id}"
            ) from exc
        except Exception:
            target.unlink(missing_ok=True)
            raise

        record = self.get_by_filename(filename)
        if record is None:
            raise LibraryError(f"imported wallpaper missing from database: {filename}")
        return record

    def set_kept(self, wallpaper_id: int, flag: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE wallpapers SET is_kept = ? WHERE id = ?", (int(flag), wallpaper_id)
            )

    def delete(self, wallpaper_id: int) -> bool:
        record = self.get(wallpaper_id)
        if record is None:
            return False

        record.path.unlink(missing_ok=True)
        self._thumb_path(wallpaper_id).unlink(missing_ok=True)
        with self._conn() as conn:
            conn.execute("DELETE FROM wallpapers WHERE id = ?", (wallpaper_id,))
        return True

    def delete_many(self, ids: builtins.list[int]) -> int:
        return sum(1 for wallpaper_id in ids if self.delete(wallpaper_id))

    def reap_orphans(self) -> tuple[int, int]:
        self.wallpaper_dir.mkdir(parents=True, exist_ok=True)
        records: builtins.list[WallpaperRecord] = self.list()
        db_filenames = {record.filename for record in records}

        deleted_files = 0
        for path in self.wallpaper_dir.iterdir():
            if not path.is_file():
                continue
            if path.suffix == ".part" or path.name not in db_filenames:
                path.unlink(missing_ok=True)
                deleted_files += 1

        deleted_db_rows = 0
        for record in records:
            if not record.path.exists():
                self.delete(record.id)
                deleted_db_rows += 1

        return deleted_files, deleted_db_rows

    def ensure_thumbnail(self, wallpaper_id: int, size: tuple[int, int] = (256, 256)) -> Path:
        thumb_path = self._thumb_path(wallpaper_id)
        if thumb_path.exists():
            return thumb_path

        record = self.get(wallpaper_id)
        if record is None:
            raise LibraryError(f"wallpaper does not exist: {wallpaper_id}")
        if not record.path.exists():
            raise LibraryError(f"wallpaper file does not exist: {record.path}")

        try:
            from PIL import Image

            self.thumb_dir.mkdir(parents=True, exist_ok=True)
            with Image.open(record.path) as image:
                image.thumbnail(size)
                image.save(thumb_path, "WEBP")
        except Exception as exc:
            raise LibraryError(f"failed to generate thumbnail for {wallpaper_id}: {exc}") from exc
        return thumb_path

    def _thumb_path(self, wallpaper_id: int) -> Path:
        return self.thumb_dir / f"{wallpaper_id}.webp"

    def _row_to_record(self, row: sqlite3.Row) -> WallpaperRecord:
        return WallpaperRecord(
            id=int(row["id"]),
            source=str(row["source"]),
            source_id=str(row["source_id"]),
            filename=str(row["filename"]),
            subscription_id=row["subscription_id"],
            subscription_name=row["subscription_name"],
            width=int(row["width"]),
            height=int(row["height"]),
            file_ext=str(row["file_ext"]),
            tags=list(json.loads(str(row["tags_json"]))),
            nsfw_level=NsfwLevel(str(row["nsfw_level"])),
            download_time=int(row["download_time"]),
            is_kept=bool(row["is_kept"]),
            original_url=row["original_url"],
            _wallpaper_dir=self.wallpaper_dir,
        )

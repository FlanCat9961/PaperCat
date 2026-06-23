from __future__ import annotations

from pathlib import Path

from papercat.core.library import Library, WallpaperRecord
from papercat.core.types import NsfwLevel


class LibraryController:
    def __init__(self, library: Library) -> None:
        self.library = library

    def list_wallpapers(
        self,
        *,
        nsfw_levels: set[NsfwLevel] | None = None,
        is_kept: bool | None = None,
        tag_includes: list[str] | None = None,
    ) -> list[WallpaperRecord]:
        return self.library.list(
            nsfw_levels=nsfw_levels, is_kept=is_kept, tag_includes=tag_includes
        )

    def toggle_kept(self, wallpaper_id: int) -> None:
        record = self.library.get(wallpaper_id)
        if record is not None:
            self.library.set_kept(wallpaper_id, not record.is_kept)

    def delete(self, ids: list[int]) -> int:
        return self.library.delete_many(ids)

    def thumbnail_path(self, wallpaper_id: int) -> Path:
        return self.library.ensure_thumbnail(wallpaper_id)

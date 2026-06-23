from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol

from papercat.core.config import SourceCredentialConfig
from papercat.core.sources.ratelimit import TokenBucket
from papercat.core.types import AspectRatio, NsfwLevel, Resolution


@dataclass(frozen=True)
class CandidateItem:
    source: str
    source_id: str
    url: str
    width: int
    height: int
    file_ext: str
    nsfw_level: NsfwLevel
    tags: list[str]
    original_url: str


@dataclass(frozen=True)
class SearchQuery:
    include_tags: list[str]
    exclude_tags: list[str]
    min_resolution: Resolution
    aspect_ratio: AspectRatio | None
    nsfw_level: NsfwLevel
    formats: list[str]
    page_hint: int = 1
    max_pages: int | None = None


class HttpClientLike(Protocol):
    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> object: ...

    async def stream_to_file(
        self,
        url: str,
        dst: Path,
        *,
        headers: dict[str, str] | None = None,
    ) -> None: ...


class Source(ABC):
    id: ClassVar[str]
    display_name: ClassVar[str]
    requires_api_key_for_nsfw: ClassVar[bool]
    default_min_interval_sec: ClassVar[float]

    def __init__(self) -> None:
        self.token_bucket = TokenBucket(self.default_min_interval_sec)

    @abstractmethod
    def search(
        self,
        q: SearchQuery,
        *,
        http: HttpClientLike,
        credentials: SourceCredentialConfig,
    ) -> AsyncIterator[CandidateItem]: ...

    @abstractmethod
    async def download(
        self, item: CandidateItem, dst_part: Path, *, http: HttpClientLike
    ) -> None: ...

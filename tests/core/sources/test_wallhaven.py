import pytest

from papercat.core.config import SourceCredentialConfig
from papercat.core.exceptions import SourceAuthError
from papercat.core.sources.base import SearchQuery
from papercat.core.sources.wallhaven import WallhavenSource
from papercat.core.types import AspectRatio, NsfwLevel, Resolution


class FakeHttpClient:
    def __init__(self, pages: list[object]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, object] | None, dict[str, str] | None]] = []
        self.downloads: list[tuple[str, object]] = []

    async def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, params, headers))
        return self.pages.pop(0)

    async def stream_to_file(self, url, dst, *, headers=None) -> None:
        self.downloads.append((url, dst))


def query(level: NsfwLevel = NsfwLevel.SFW, max_pages: int | None = None) -> SearchQuery:
    return SearchQuery(
        include_tags=["cat"],
        exclude_tags=["dog"],
        min_resolution=Resolution(1920, 1080),
        aspect_ratio=AspectRatio(16, 9),
        nsfw_level=level,
        formats=["jpg", "png", "webp", "gif"],
        max_pages=max_pages,
    )


@pytest.mark.asyncio
async def test_builds_params_and_maps_fields() -> None:
    source = WallhavenSource()
    source.token_bucket.min_interval_sec = 0
    http = FakeHttpClient(
        [
            {
                "data": [
                    {
                        "id": "abc",
                        "path": "https://w/img.jpg",
                        "dimension_x": 1920,
                        "dimension_y": 1080,
                        "file_type": "image/jpeg",
                        "purity": "sfw",
                        "url": "https://wallhaven.cc/w/abc",
                    }
                ]
            },
            {"data": []},
        ]
    )

    search = source.search(query(), http=http, credentials=SourceCredentialConfig())
    results = [item async for item in search]

    assert http.calls[0][1] == {
        "q": "cat -dog",
        "atleast": "1920x1080",
        "purity": "100",
        "sorting": "date_added",
        "order": "desc",
        "page": 1,
        "ratios": "16x9",
    }
    assert results[0].source_id == "abc"
    assert results[0].file_ext == "jpg"


@pytest.mark.asyncio
async def test_nsfw_without_api_key_raises() -> None:
    with pytest.raises(SourceAuthError):
        candidates = WallhavenSource().search(
            query(NsfwLevel.NSFW),
            http=FakeHttpClient([]),
            credentials=SourceCredentialConfig(),
        )
        await anext(candidates)


@pytest.mark.asyncio
async def test_respects_max_pages() -> None:
    source = WallhavenSource()
    source.token_bucket.min_interval_sec = 0
    http = FakeHttpClient(
        [
            {
                "data": [
                    {
                        "id": "abc",
                        "path": "https://w/img.jpg",
                        "dimension_x": 1920,
                        "dimension_y": 1080,
                        "file_type": "image/jpeg",
                        "purity": "sfw",
                        "url": "https://wallhaven.cc/w/abc",
                    }
                ]
            },
            {
                "data": [
                    {
                        "id": "def",
                        "path": "https://w/img2.jpg",
                        "dimension_x": 1920,
                        "dimension_y": 1080,
                        "file_type": "image/jpeg",
                        "purity": "sfw",
                        "url": "https://wallhaven.cc/w/def",
                    }
                ]
            },
        ]
    )

    results = [
        item
        async for item in source.search(
            query(max_pages=1),
            http=http,
            credentials=SourceCredentialConfig(),
        )
    ]

    assert [item.source_id for item in results] == ["abc"]
    assert len(http.calls) == 1

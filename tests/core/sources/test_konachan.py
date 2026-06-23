import pytest

from papercat.core.config import SourceCredentialConfig
from papercat.core.sources.base import SearchQuery
from papercat.core.sources.konachan import KonachanSource
from papercat.core.types import AspectRatio, NsfwLevel, Resolution


class FakeHttpClient:
    def __init__(self, pages: list[object]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    async def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, params))
        return self.pages.pop(0)

    async def stream_to_file(self, url, dst, *, headers=None) -> None:
        dst.write_text(url, encoding="utf-8")


def query(max_pages: int | None = None) -> SearchQuery:
    return SearchQuery(
        include_tags=["cat"],
        exclude_tags=["dog"],
        min_resolution=Resolution(1920, 1080),
        aspect_ratio=AspectRatio(16, 9),
        nsfw_level=NsfwLevel.SKETCHY,
        formats=["jpg"],
        max_pages=max_pages,
    )


@pytest.mark.asyncio
async def test_tags_mapping_filtering_and_fields() -> None:
    source = KonachanSource()
    source.token_bucket.min_interval_sec = 0
    http = FakeHttpClient(
        [
            [
                {
                    "id": 123,
                    "file_url": "//img/1.jpg",
                    "width": 1920,
                    "height": 1080,
                    "file_ext": "jpg",
                    "rating": "q",
                    "tags": "cat sky",
                },
                {
                    "id": 124,
                    "file_url": "https://img/2.png",
                    "width": 1920,
                    "height": 1080,
                    "file_ext": "png",
                    "rating": "q",
                    "tags": "cat",
                },
            ]
        ]
    )

    search = source.search(query(), http=http, credentials=SourceCredentialConfig())
    results = [item async for item in search]

    assert http.calls[0][1]["tags"] == (
        "cat -dog width:>=1920 height:>=1080 ratio:16:9 rating:q order:date"
    )
    assert len(results) == 1
    assert results[0].url == "https://img/1.jpg"
    assert results[0].original_url == "https://konachan.com/post/show/123"
    assert results[0].tags == ["cat", "sky"]


@pytest.mark.asyncio
async def test_respects_max_pages() -> None:
    source = KonachanSource()
    source.token_bucket.min_interval_sec = 0
    http = FakeHttpClient(
        [
            [
                {
                    "id": 123,
                    "file_url": "https://img/1.jpg",
                    "width": 1920,
                    "height": 1080,
                    "file_ext": "jpg",
                    "rating": "q",
                    "tags": "cat",
                }
            ],
            [
                {
                    "id": 124,
                    "file_url": "https://img/2.jpg",
                    "width": 1920,
                    "height": 1080,
                    "file_ext": "jpg",
                    "rating": "q",
                    "tags": "cat",
                }
            ],
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

    assert [item.source_id for item in results] == ["123"]
    assert len(http.calls) == 1

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from papercat.core.config import SourceCredentialConfig
from papercat.core.sources.base import CandidateItem, HttpClientLike, SearchQuery, Source
from papercat.core.types import NsfwLevel


class _BooruSource(Source):
    BASE_URL: str
    PAGE_LIMIT = 100
    default_min_interval_sec = 1.2
    requires_api_key_for_nsfw = False

    async def search(
        self,
        q: SearchQuery,
        *,
        http: HttpClientLike,
        credentials: SourceCredentialConfig,
    ) -> AsyncIterator[CandidateItem]:
        del credentials
        page = q.page_hint
        while q.max_pages is None or page < q.page_hint + q.max_pages:
            await self.token_bucket.acquire()
            payload = await http.get_json(
                f"{self.BASE_URL}/post.json",
                params={"limit": self.PAGE_LIMIT, "page": page, "tags": self._build_tags(q)},
            )
            if not isinstance(payload, list) or not payload:
                break
            for item in payload:
                candidate = self._candidate_from_item(item)
                if candidate is not None and candidate.file_ext in self._normalized_formats(q):
                    yield candidate
            if len(payload) < self.PAGE_LIMIT:
                break
            page += 1

    async def download(self, item: CandidateItem, dst_part: Path, *, http: HttpClientLike) -> None:
        await http.stream_to_file(item.url, dst_part)

    def _build_tags(self, q: SearchQuery) -> str:
        tags = [
            *q.include_tags,
            *[f"-{tag}" for tag in q.exclude_tags],
            f"width:>={q.min_resolution.width}",
            f"height:>={q.min_resolution.height}",
        ]
        if q.aspect_ratio is not None:
            tags.append(f"ratio:{q.aspect_ratio.width}:{q.aspect_ratio.height}")
        tags.extend(
            [
                {
                    NsfwLevel.SFW: "rating:s",
                    NsfwLevel.SKETCHY: "rating:q",
                    NsfwLevel.NSFW: "rating:e",
                }[q.nsfw_level],
                "order:date",
            ]
        )
        return " ".join(tags)

    def _candidate_from_item(self, item: object) -> CandidateItem | None:
        if not isinstance(item, dict):
            return None
        try:
            source_id = str(item["id"])
            url = str(item["file_url"])
            if url.startswith("//"):
                url = f"https:{url}"
            return CandidateItem(
                source=self.id,
                source_id=source_id,
                url=url,
                width=int(item["width"]),
                height=int(item["height"]),
                file_ext=str(item["file_ext"]).lower().removeprefix("."),
                nsfw_level={
                    "s": NsfwLevel.SFW,
                    "q": NsfwLevel.SKETCHY,
                    "e": NsfwLevel.NSFW,
                }[str(item["rating"])],
                tags=str(item.get("tags", "")).split(),
                original_url=f"{self.BASE_URL}/post/show/{source_id}",
            )
        except (KeyError, TypeError, ValueError) as exc:
            logging.getLogger(__name__).warning("skipping invalid booru item: %s", exc)
            return None

    @staticmethod
    def _normalized_formats(q: SearchQuery) -> set[str]:
        return {fmt.lower().removeprefix(".") for fmt in q.formats}


class KonachanSource(_BooruSource):
    id = "konachan"
    display_name = "Konachan"
    BASE_URL = "https://konachan.com"

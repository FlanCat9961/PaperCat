from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from papercat.core.config import SourceCredentialConfig
from papercat.core.exceptions import SourceAuthError
from papercat.core.sources.base import CandidateItem, HttpClientLike, SearchQuery, Source
from papercat.core.types import NsfwLevel

BASE_URL = "https://wallhaven.cc/api/v1"


class WallhavenSource(Source):
    id = "wallhaven"
    display_name = "Wallhaven"
    requires_api_key_for_nsfw = True
    default_min_interval_sec = 1.5

    async def search(
        self,
        q: SearchQuery,
        *,
        http: HttpClientLike,
        credentials: SourceCredentialConfig,
    ) -> AsyncIterator[CandidateItem]:
        api_key = credentials.wallhaven_api_key
        if q.nsfw_level != NsfwLevel.SFW and not api_key:
            raise SourceAuthError("Wallhaven requires an API key for sketchy/nsfw searches")

        headers = {"X-API-Key": api_key} if api_key else None
        page = q.page_hint
        while q.max_pages is None or page < q.page_hint + q.max_pages:
            await self.token_bucket.acquire()
            params = self._build_params(q, page)
            payload = await http.get_json(f"{BASE_URL}/search", params=params, headers=headers)
            data = payload.get("data", []) if isinstance(payload, dict) else []
            if not data:
                break
            for item in data:
                candidate = self._candidate_from_item(item)
                if candidate is not None:
                    yield candidate
            page += 1

    async def download(self, item: CandidateItem, dst_part: Path, *, http: HttpClientLike) -> None:
        await http.stream_to_file(item.url, dst_part)

    def _build_params(self, q: SearchQuery, page: int) -> dict[str, object]:
        query_parts = [*q.include_tags, *[f"-{tag}" for tag in q.exclude_tags]]

        params: dict[str, object] = {
            "q": " ".join(query_parts),
            "atleast": f"{q.min_resolution.width}x{q.min_resolution.height}",
            "purity": {
                NsfwLevel.SFW: "100",
                NsfwLevel.SKETCHY: "110",
                NsfwLevel.NSFW: "111",
            }[q.nsfw_level],
            "sorting": "date_added",
            "order": "desc",
            "page": page,
        }
        if q.aspect_ratio is not None:
            params["ratios"] = f"{q.aspect_ratio.width}x{q.aspect_ratio.height}"
        return params

    @staticmethod
    def _candidate_from_item(item: object) -> CandidateItem | None:
        if not isinstance(item, dict):
            return None
        try:
            file_ext = {"image/jpeg": "jpg", "image/png": "png"}[str(item["file_type"])]
            return CandidateItem(
                source=WallhavenSource.id,
                source_id=str(item["id"]),
                url=str(item["path"]),
                width=int(item["dimension_x"]),
                height=int(item["dimension_y"]),
                file_ext=file_ext,
                nsfw_level={
                    "sfw": NsfwLevel.SFW,
                    "sketchy": NsfwLevel.SKETCHY,
                    "nsfw": NsfwLevel.NSFW,
                }[str(item["purity"])],
                tags=[],
                original_url=str(item["url"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logging.getLogger(__name__).warning("skipping invalid Wallhaven item: %s", exc)
            return None

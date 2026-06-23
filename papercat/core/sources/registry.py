from __future__ import annotations

from papercat.core.exceptions import ConfigError
from papercat.core.sources.base import Source


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}

    def register(self, src_cls: type[Source]) -> None:
        source = src_cls()
        self._sources[source.id] = source

    def get(self, source_id: str) -> Source:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise ConfigError(f"unknown source: {source_id}") from exc

    def available_ids(self) -> set[str]:
        return set(self._sources)

    def available(self) -> list[Source]:
        return list(self._sources.values())


DEFAULT_REGISTRY = SourceRegistry()

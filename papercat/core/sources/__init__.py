from papercat.core.sources.base import CandidateItem, SearchQuery, Source
from papercat.core.sources.konachan import KonachanSource
from papercat.core.sources.registry import DEFAULT_REGISTRY, SourceRegistry
from papercat.core.sources.wallhaven import WallhavenSource
from papercat.core.sources.yandere import YandereSource

DEFAULT_REGISTRY.register(WallhavenSource)
DEFAULT_REGISTRY.register(KonachanSource)
DEFAULT_REGISTRY.register(YandereSource)

__all__ = [
    "DEFAULT_REGISTRY",
    "CandidateItem",
    "KonachanSource",
    "SearchQuery",
    "Source",
    "SourceRegistry",
    "WallhavenSource",
    "YandereSource",
]

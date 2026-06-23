from __future__ import annotations

from papercat.core.sources.konachan import _BooruSource


class YandereSource(_BooruSource):
    id = "yandere"
    display_name = "yande.re"
    BASE_URL = "https://yande.re"

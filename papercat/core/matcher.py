from collections.abc import Iterable

from papercat.core.types import AspectRatio


def aspect_ratio_value(ar: AspectRatio) -> float:
    return ar.value


def matches_aspect_ratio(
    width: int,
    height: int,
    target: AspectRatio | None,
    tolerance: float = 0.15,
) -> bool:
    if target is None:
        return True
    if height == 0:
        return False

    actual = width / height
    return abs(actual - target.value) / target.value <= tolerance


def matches_format(file_ext: str, formats: Iterable[str]) -> bool:
    normalized_ext = file_ext.lower().removeprefix(".")
    normalized_formats = {item.lower().removeprefix(".") for item in formats}
    return normalized_ext in normalized_formats

import pytest

from papercat.core.matcher import aspect_ratio_value, matches_aspect_ratio, matches_format
from papercat.core.types import AspectRatio


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (16, 9, True),
        (16, 10, True),
        (16, 8, True),
        (21, 9, False),
        (4, 3, False),
    ],
)
def test_matches_aspect_ratio_16_9_tolerance(width: int, height: int, expected: bool) -> None:
    assert matches_aspect_ratio(width, height, AspectRatio(16, 9), 0.15) is expected


@pytest.mark.parametrize(
    ("target", "width", "height", "expected"),
    [
        (AspectRatio(16, 10), 16, 9, True),
        (AspectRatio(16, 10), 4, 3, False),
        (AspectRatio(4, 3), 16, 10, False),
        (AspectRatio(4, 3), 5, 4, True),
    ],
)
def test_matches_aspect_ratio_other_targets(
    target: AspectRatio,
    width: int,
    height: int,
    expected: bool,
) -> None:
    assert matches_aspect_ratio(width, height, target, 0.15) is expected


def test_matches_aspect_ratio_accepts_none_target() -> None:
    assert matches_aspect_ratio(1, 0, None, 0.15) is True


def test_matches_aspect_ratio_zero_height_returns_false() -> None:
    assert matches_aspect_ratio(16, 0, AspectRatio(16, 9), 0.15) is False


def test_aspect_ratio_value() -> None:
    assert aspect_ratio_value(AspectRatio(4, 3)) == pytest.approx(4 / 3)


@pytest.mark.parametrize(
    ("file_ext", "formats"),
    [
        ("JPG", ["jpg"]),
        (".png", ["png"]),
        ("webp", [".WEBP"]),
    ],
)
def test_matches_format_normalizes_case_and_dot(file_ext: str, formats: list[str]) -> None:
    assert matches_format(file_ext, formats) is True


def test_matches_format_rejects_missing_format() -> None:
    assert matches_format("gif", ["jpg", "png"]) is False

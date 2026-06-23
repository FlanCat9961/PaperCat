import pytest

from papercat.core.types import AspectRatio, Resolution


def test_resolution_as_tuple_and_string() -> None:
    resolution = Resolution(width=1920, height=1080)

    assert resolution.as_tuple() == (1920, 1080)
    assert str(resolution) == "1920x1080"


def test_aspect_ratio_value_and_string() -> None:
    ratio = AspectRatio(width=16, height=9)

    assert ratio.value == pytest.approx(16 / 9)
    assert str(ratio) == "16:9"


def test_aspect_ratio_zero_height_raises() -> None:
    ratio = AspectRatio(width=16, height=0)

    with pytest.raises(ZeroDivisionError):
        _ = ratio.value

from dataclasses import dataclass
from enum import StrEnum


class NsfwLevel(StrEnum):
    SFW = "sfw"
    SKETCHY = "sketchy"
    NSFW = "nsfw"


@dataclass(frozen=True)
class Resolution:
    width: int
    height: int

    def as_tuple(self) -> tuple[int, int]:
        return (self.width, self.height)

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class AspectRatio:
    width: int
    height: int

    @property
    def value(self) -> float:
        return self.width / self.height

    def __str__(self) -> str:
        return f"{self.width}:{self.height}"

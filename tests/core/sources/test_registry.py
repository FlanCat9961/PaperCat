import pytest

from papercat.core.exceptions import ConfigError
from papercat.core.sources.base import Source
from papercat.core.sources.registry import SourceRegistry
from papercat.core.sources.wallhaven import WallhavenSource


def test_register_and_get_source() -> None:
    registry = SourceRegistry()

    registry.register(WallhavenSource)

    assert registry.get("wallhaven").id == "wallhaven"
    assert registry.available_ids() == {"wallhaven"}
    assert [source.id for source in registry.available()] == ["wallhaven"]


def test_get_unknown_source_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        SourceRegistry().get("missing")


def test_source_abstract_base_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Source()

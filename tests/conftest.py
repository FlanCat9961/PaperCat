from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_xdg_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    config_home.mkdir()
    data_home.mkdir()

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))

    yield tmp_path

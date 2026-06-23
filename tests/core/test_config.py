import pytest

from papercat.core.config import Config, ConfigStore, CrawlConfig
from papercat.core.exceptions import ConfigError


def test_load_missing_file_writes_default_config(tmp_path) -> None:
    path = tmp_path / "config.toml"
    store = ConfigStore(path)

    config = store.load()

    assert isinstance(config, Config)
    assert path.exists()


def test_save_then_load_round_trips(tmp_path) -> None:
    path = tmp_path / "config.toml"
    store = ConfigStore(path)
    config = Config(non_kept_limit=12, crawl=CrawlConfig(per_subscription_max=2))

    store.save(config)

    assert store.load() == config


def test_invalid_non_kept_limit_raises_config_error(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("non_kept_limit = 0\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        ConfigStore(path).load()


def test_invalid_aspect_tolerance_raises_config_error(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[crawl]\naspect_tolerance = 2.0\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        ConfigStore(path).load()


def test_custom_interval_requires_seconds(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[crawl]\ninterval_preset = 'custom'\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        ConfigStore(path).load()


def test_invalid_toml_raises_config_error(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("not = [valid\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        ConfigStore(path).load()


def test_save_uses_atomic_temp_file_without_leftover(tmp_path) -> None:
    path = tmp_path / "config.toml"

    ConfigStore(path).save(Config())

    assert path.exists()
    assert not (tmp_path / "config.toml.tmp").exists()

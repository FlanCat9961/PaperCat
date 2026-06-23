from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, model_validator

from papercat.core.exceptions import ConfigError
from papercat.core.paths import CONFIG_FILE
from papercat.core.types import Resolution

CleanupPreset = Literal["off", "daily", "every_3d", "weekly", "monthly", "custom"]
CrawlPreset = Literal["off", "hourly", "every_3h", "every_6h", "daily", "custom"]

INTERVAL_PRESETS_SEC: dict[str, dict[str, int | None]] = {
    "cleanup": {
        "off": None,
        "daily": 24 * 60 * 60,
        "every_3d": 3 * 24 * 60 * 60,
        "weekly": 7 * 24 * 60 * 60,
        "monthly": 30 * 24 * 60 * 60,
        "custom": None,
    },
    "crawl": {
        "off": None,
        "hourly": 60 * 60,
        "every_3h": 3 * 60 * 60,
        "every_6h": 6 * 60 * 60,
        "daily": 24 * 60 * 60,
        "custom": None,
    },
}


class ProxyConfig(BaseModel):
    enabled: bool = False
    url: str | None = None


class SourceCredentialConfig(BaseModel):
    wallhaven_api_key: str | None = None


class NotificationConfig(BaseModel):
    enabled: bool = True
    on_crawl_done: bool = True
    on_cleanup_done: bool = True
    on_error: bool = True


class CleanupConfig(BaseModel):
    interval_preset: CleanupPreset = "weekly"
    custom_interval_seconds: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_custom_interval(self) -> CleanupConfig:
        if self.interval_preset == "custom" and self.custom_interval_seconds is None:
            raise ValueError("custom cleanup interval requires custom_interval_seconds")
        return self


class CrawlConfig(BaseModel):
    interval_preset: CrawlPreset = "every_6h"
    custom_interval_seconds: PositiveInt | None = None
    per_subscription_max: PositiveInt = 5
    max_concurrent_subscriptions: PositiveInt = 4
    aspect_tolerance: float = Field(default=0.15, ge=0.0, le=1.0)
    request_timeout_seconds: PositiveInt = 30
    download_timeout_seconds: PositiveInt = 120
    retry_attempts: NonNegativeInt = 3

    @model_validator(mode="after")
    def validate_custom_interval(self) -> CrawlConfig:
        if self.interval_preset == "custom" and self.custom_interval_seconds is None:
            raise ValueError("custom crawl interval requires custom_interval_seconds")
        return self


class HookConfig(BaseModel):
    post_download_command: str = ""
    timeout_seconds: PositiveInt = 10


class Config(BaseModel):
    schema_version: PositiveInt = 1
    wallpaper_dir: Path = Field(default_factory=lambda: Path.home() / "Pictures" / "Wallpapers")
    non_kept_limit: PositiveInt = 50
    nsfw_master_enabled: bool = False
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    credentials: SourceCredentialConfig = Field(default_factory=SourceCredentialConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    hook: HookConfig = Field(default_factory=HookConfig)
    user_resolutions: list[Resolution] = Field(default_factory=list)


def _drop_none(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_drop_none(item) for item in value]
    return value


class ConfigStore:
    def __init__(self, path: Path = CONFIG_FILE) -> None:
        self.path = path

    def load(self) -> Config:
        if not self.path.exists():
            config = Config()
            self.save(config)
            return config

        try:
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
            return Config.model_validate(data)
        except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
            raise ConfigError(f"failed to load config from {self.path}: {exc}") from exc

    def save(self, cfg: Config) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        data = _drop_none(cfg.model_dump(mode="json"))

        try:
            tmp_path.write_text(tomli_w.dumps(data), encoding="utf-8")
            os.replace(tmp_path, self.path)
        except OSError as exc:
            raise ConfigError(f"failed to save config to {self.path}: {exc}") from exc
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

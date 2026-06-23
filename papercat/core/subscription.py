from __future__ import annotations

import builtins
import os
import tomllib
from pathlib import Path
from typing import Literal, Protocol

import tomli_w
from pydantic import BaseModel, Field, model_validator

from papercat.core.exceptions import ConfigError
from papercat.core.paths import SUBSCRIPTIONS_FILE
from papercat.core.types import AspectRatio, NsfwLevel, Resolution

WallpaperFormat = Literal["jpg", "png", "webp", "gif"]
CrawlStrategy = Literal["latest_fill", "incremental_strict", "random"]


def _default_formats() -> builtins.list[WallpaperFormat]:
    return ["jpg", "png"]


class SourceRegistryLike(Protocol):
    def available_ids(self) -> set[str]: ...


class Subscription(BaseModel):
    id: int
    name: str
    source: str
    enabled: bool = True
    include_tags: builtins.list[str] = Field(default_factory=list)
    exclude_tags: builtins.list[str] = Field(default_factory=list)
    resolution: Resolution
    aspect_ratio: AspectRatio | None = None
    nsfw_level: NsfwLevel = NsfwLevel.SFW
    formats: builtins.list[WallpaperFormat] = Field(default_factory=_default_formats)
    order: int = 0
    crawl_strategy: CrawlStrategy = "latest_fill"
    max_scan_pages: int = 5
    max_scan_candidates: int = 200

    @model_validator(mode="after")
    def validate_tags_and_resolution(self) -> Subscription:
        overlap = set(self.include_tags) & set(self.exclude_tags)
        if overlap:
            raise ValueError(f"include_tags and exclude_tags overlap: {sorted(overlap)}")
        if self.resolution.width <= 0 or self.resolution.height <= 0:
            raise ValueError("resolution width and height must be positive")
        if self.max_scan_pages <= 0:
            raise ValueError("max_scan_pages must be positive")
        if self.max_scan_candidates <= 0:
            raise ValueError("max_scan_candidates must be positive")
        return self


class SubscriptionStore:
    def __init__(
        self,
        path: Path = SUBSCRIPTIONS_FILE,
        source_registry: SourceRegistryLike | None = None,
    ) -> None:
        self.path = path
        self.source_registry = source_registry

    def list(self, enabled_only: bool = False) -> builtins.list[Subscription]:
        subscriptions: builtins.list[Subscription] = self._load_all()
        if enabled_only:
            subscriptions = [subscription for subscription in subscriptions if subscription.enabled]
        return sorted(subscriptions, key=lambda subscription: subscription.order)

    def get(self, sub_id: int) -> Subscription | None:
        return next(
            (subscription for subscription in self._load_all() if subscription.id == sub_id), None
        )

    def create(self, sub: Subscription) -> Subscription:
        subscriptions: builtins.list[Subscription] = self._load_all()
        next_id = max((item.id for item in subscriptions), default=0) + 1
        created = sub.model_copy(update={"id": next_id})
        self._validate_subscription(created)
        subscriptions.append(created)
        self._save_all(subscriptions)
        return created

    def update(self, sub: Subscription) -> Subscription:
        self._validate_subscription(sub)
        subscriptions: builtins.list[Subscription] = self._load_all()
        for index, current in enumerate(subscriptions):
            if current.id == sub.id:
                subscriptions[index] = sub
                self._save_all(subscriptions)
                return sub
        raise ConfigError(f"subscription {sub.id} does not exist")

    def delete(self, sub_id: int) -> None:
        subscriptions: builtins.list[Subscription] = [
            subscription for subscription in self._load_all() if subscription.id != sub_id
        ]
        self._save_all(subscriptions)

    def set_enabled(self, sub_id: int, flag: bool) -> None:
        subscription = self.get(sub_id)
        if subscription is None:
            raise ConfigError(f"subscription {sub_id} does not exist")
        self.update(subscription.model_copy(update={"enabled": flag}))

    def reorder(self, ordered_ids: builtins.list[int]) -> None:
        subscriptions_by_id: dict[int, Subscription] = {
            subscription.id: subscription for subscription in self._load_all()
        }
        missing: set[int] = set(ordered_ids) - set(subscriptions_by_id)
        if missing:
            raise ConfigError(f"unknown subscription IDs in reorder: {sorted(missing)}")

        reordered: builtins.list[Subscription] = []
        seen: set[int] = set()
        for order, sub_id in enumerate(ordered_ids):
            seen.add(sub_id)
            reordered.append(subscriptions_by_id[sub_id].model_copy(update={"order": order}))

        remaining = [
            subscription.model_copy(update={"order": len(reordered) + index})
            for index, subscription in enumerate(self.list())
            if subscription.id not in seen
        ]
        self._save_all([*reordered, *remaining])

    def _load_all(self) -> builtins.list[Subscription]:
        if not self.path.exists():
            return []

        try:
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
            raw_subscriptions = data.get("subscriptions", [])
            if not isinstance(raw_subscriptions, list):
                raise ValueError("subscriptions must be a list")
            subscriptions: builtins.list[Subscription] = [
                Subscription.model_validate(item) for item in raw_subscriptions
            ]
            for subscription in subscriptions:
                self._validate_subscription(subscription)
            return subscriptions
        except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
            raise ConfigError(f"failed to load subscriptions from {self.path}: {exc}") from exc

    def _save_all(self, subscriptions: builtins.list[Subscription]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        data = {
            "subscriptions": [
                subscription.model_dump(mode="json") for subscription in subscriptions
            ]
        }

        try:
            tmp_path.write_text(tomli_w.dumps(data), encoding="utf-8")
            os.replace(tmp_path, self.path)
        except OSError as exc:
            raise ConfigError(f"failed to save subscriptions to {self.path}: {exc}") from exc
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def _validate_subscription(self, subscription: Subscription) -> None:
        if self.source_registry is None:
            return
        available_ids = self.source_registry.available_ids()
        if subscription.source not in available_ids:
            raise ConfigError(f"unknown source: {subscription.source}")

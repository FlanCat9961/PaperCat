import pytest

from papercat.core.exceptions import ConfigError
from papercat.core.subscription import Subscription, SubscriptionStore
from papercat.core.types import AspectRatio, NsfwLevel, Resolution


class FakeSourceRegistry:
    def available_ids(self) -> set[str]:
        return {"fake"}


def make_subscription(name: str = "one", source: str = "fake", order: int = 0) -> Subscription:
    return Subscription(
        id=0,
        name=name,
        source=source,
        include_tags=["cat"],
        exclude_tags=["dog"],
        resolution=Resolution(1920, 1080),
        aspect_ratio=AspectRatio(16, 9),
        nsfw_level=NsfwLevel.SFW,
        formats=["jpg", "png"],
        order=order,
    )


def test_crud_round_trip(tmp_path) -> None:
    store = SubscriptionStore(tmp_path / "subscriptions.toml", FakeSourceRegistry())

    created = store.create(
        make_subscription().model_copy(
            update={
                "crawl_strategy": "random",
                "max_scan_pages": 7,
                "max_scan_candidates": 123,
            }
        )
    )
    assert created.id == 1
    assert store.get(1) == created

    updated = created.model_copy(update={"name": "updated"})
    assert store.update(updated).name == "updated"
    assert store.get(1) == updated

    store.delete(1)
    assert store.get(1) is None


def test_enabled_only_filter(tmp_path) -> None:
    store = SubscriptionStore(tmp_path / "subscriptions.toml", FakeSourceRegistry())
    first = store.create(make_subscription("first"))
    second = store.create(make_subscription("second"))

    store.set_enabled(second.id, False)

    assert store.list(enabled_only=True) == [first]


def test_reorder_updates_list_order(tmp_path) -> None:
    store = SubscriptionStore(tmp_path / "subscriptions.toml", FakeSourceRegistry())
    first = store.create(make_subscription("first"))
    second = store.create(make_subscription("second"))

    store.reorder([second.id, first.id])

    assert [subscription.id for subscription in store.list()] == [second.id, first.id]


def test_tag_conflict_raises() -> None:
    with pytest.raises(ValueError):
        Subscription(
            id=0,
            name="bad",
            source="fake",
            include_tags=["cat"],
            exclude_tags=["cat"],
            resolution=Resolution(1920, 1080),
        )


def test_invalid_source_raises_config_error(tmp_path) -> None:
    store = SubscriptionStore(tmp_path / "subscriptions.toml", FakeSourceRegistry())

    with pytest.raises(ConfigError):
        store.create(make_subscription(source="missing"))


def test_write_then_read_is_equal(tmp_path) -> None:
    path = tmp_path / "subscriptions.toml"
    store = SubscriptionStore(path, FakeSourceRegistry())
    created = store.create(
        make_subscription().model_copy(
            update={
                "crawl_strategy": "random",
                "max_scan_pages": 7,
                "max_scan_candidates": 123,
            }
        )
    )

    loaded_store = SubscriptionStore(path, FakeSourceRegistry())

    assert loaded_store.list() == [created]
    loaded = loaded_store.list()[0]
    assert loaded.crawl_strategy == "random"
    assert loaded.max_scan_pages == 7
    assert loaded.max_scan_candidates == 123


def test_missing_file_lists_empty(tmp_path) -> None:
    store = SubscriptionStore(tmp_path / "subscriptions.toml", FakeSourceRegistry())

    assert store.list() == []


def test_missing_v011_fields_load_with_defaults(tmp_path) -> None:
    path = tmp_path / "subscriptions.toml"
    path.write_text(
        """[[subscriptions]]
id = 1
name = "old"
source = "fake"
enabled = true
include_tags = ["cat"]
exclude_tags = []
resolution = { width = 1920, height = 1080 }
formats = ["jpg"]
order = 0
""",
        encoding="utf-8",
    )
    store = SubscriptionStore(path, FakeSourceRegistry())

    loaded = store.list()[0]

    assert loaded.crawl_strategy == "latest_fill"
    assert loaded.max_scan_pages == 5
    assert loaded.max_scan_candidates == 200


def test_invalid_scan_limits_raise() -> None:
    with pytest.raises(ValueError):
        Subscription(
            id=0,
            name="bad",
            source="fake",
            resolution=Resolution(1920, 1080),
            max_scan_pages=0,
        )
    with pytest.raises(ValueError):
        Subscription(
            id=0,
            name="bad",
            source="fake",
            resolution=Resolution(1920, 1080),
            max_scan_candidates=0,
        )

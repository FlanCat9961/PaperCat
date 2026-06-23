import importlib

from papercat.core import paths


def test_paths_follow_xdg_environment(tmp_xdg_dirs) -> None:
    reloaded = importlib.reload(paths)

    assert tmp_xdg_dirs / "config" / "papercat" == reloaded.CONFIG_DIR
    assert tmp_xdg_dirs / "data" / "papercat" == reloaded.DATA_DIR
    assert reloaded.CONFIG_FILE == reloaded.CONFIG_DIR / "config.toml"
    assert reloaded.SUBSCRIPTIONS_FILE == reloaded.CONFIG_DIR / "subscriptions.toml"
    assert reloaded.DB_FILE == reloaded.DATA_DIR / "papercat.db"
    assert reloaded.LOCK_FILE == reloaded.DATA_DIR / "papercat.lock"
    assert reloaded.LOG_DIR == reloaded.DATA_DIR / "logs"
    assert reloaded.THUMB_DIR == reloaded.DATA_DIR / "thumbnails"

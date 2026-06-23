import os
from pathlib import Path

XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
XDG_DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")

CONFIG_DIR = XDG_CONFIG / "papercat"
DATA_DIR = XDG_DATA / "papercat"

CONFIG_FILE = CONFIG_DIR / "config.toml"
SUBSCRIPTIONS_FILE = CONFIG_DIR / "subscriptions.toml"
DB_FILE = DATA_DIR / "papercat.db"
LOCK_FILE = DATA_DIR / "papercat.lock"
LOG_DIR = DATA_DIR / "logs"
THUMB_DIR = DATA_DIR / "thumbnails"

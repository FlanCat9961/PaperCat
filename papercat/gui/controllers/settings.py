from __future__ import annotations

from papercat.core.config import Config, ConfigStore
from papercat.core.monitor import MonitorDetector, MonitorInfo


class SettingsController:
    def __init__(self, config_store: ConfigStore, monitor_detector: MonitorDetector) -> None:
        self.config_store = config_store
        self.monitor_detector = monitor_detector

    def load(self) -> Config:
        return self.config_store.load()

    def save(self, config: Config) -> None:
        self.config_store.save(config)

    def detect_monitors(self) -> list[MonitorInfo]:
        return self.monitor_detector.detect()

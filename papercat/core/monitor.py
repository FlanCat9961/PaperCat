from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from papercat.core.exceptions import MonitorError
from papercat.core.types import Resolution


@dataclass(frozen=True)
class MonitorInfo:
    name: str
    resolution: Resolution


Runner = Callable[..., subprocess.CompletedProcess[str]]


class MonitorDetector:
    def __init__(self, runner: Runner = subprocess.run) -> None:
        self.runner = runner

    def detect(self) -> list[MonitorInfo]:
        attempts = [
            (["hyprctl", "monitors", "-j"], self._parse_hyprctl),
            (["swaymsg", "-t", "get_outputs"], self._parse_swaymsg),
            (["wlr-randr", "--json"], self._parse_wlr_randr),
        ]
        failures: list[str] = []
        for command, parser in attempts:
            try:
                result = self.runner(command, capture_output=True, text=True, timeout=5)
                if result.returncode != 0:
                    raise MonitorError(result.stderr)
                monitors = parser(result.stdout)
                if monitors:
                    return monitors
            except Exception as exc:
                failures.append(f"{' '.join(command)}: {exc}")
        raise MonitorError("all monitor detection commands failed: " + "; ".join(failures))

    def all_resolutions(self, user_resolutions: list[Resolution]) -> list[Resolution]:
        resolutions = {monitor.resolution for monitor in self.detect()}
        resolutions.update(user_resolutions)
        return sorted(resolutions, key=lambda item: (item.width, item.height), reverse=True)

    @staticmethod
    def _parse_hyprctl(payload: str) -> list[MonitorInfo]:
        data = json.loads(payload)
        return [
            MonitorInfo(str(item["name"]), Resolution(int(item["width"]), int(item["height"])))
            for item in data
        ]

    @staticmethod
    def _parse_swaymsg(payload: str) -> list[MonitorInfo]:
        data = json.loads(payload)
        monitors = []
        for item in data:
            mode = item.get("current_mode") or {}
            if mode:
                monitors.append(
                    MonitorInfo(
                        str(item["name"]), Resolution(int(mode["width"]), int(mode["height"]))
                    )
                )
        return monitors

    @staticmethod
    def _parse_wlr_randr(payload: str) -> list[MonitorInfo]:
        data = json.loads(payload)
        monitors = []
        for item in data:
            mode = item.get("current_mode") or {}
            if mode:
                monitors.append(
                    MonitorInfo(
                        str(item["name"]), Resolution(int(mode["width"]), int(mode["height"]))
                    )
                )
        return monitors

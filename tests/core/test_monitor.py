import json
import subprocess

import pytest

from papercat.core.exceptions import MonitorError
from papercat.core.monitor import MonitorDetector
from papercat.core.types import Resolution


def completed(payload: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")


def test_hyprctl_json_is_parsed() -> None:
    detector = MonitorDetector(
        lambda *args, **kwargs: completed([{"name": "DP-1", "width": 2560, "height": 1440}])
    )

    monitors = detector.detect()

    assert monitors[0].name == "DP-1"
    assert monitors[0].resolution == Resolution(2560, 1440)


def test_falls_back_to_swaymsg() -> None:
    calls = []

    def runner(command, *args, **kwargs):
        calls.append(command)
        if command[0] == "hyprctl":
            raise FileNotFoundError("hyprctl")
        return completed([{"name": "HDMI-A-1", "current_mode": {"width": 1920, "height": 1080}}])

    assert MonitorDetector(runner).detect()[0].resolution == Resolution(1920, 1080)
    assert calls[0][0] == "hyprctl"
    assert calls[1][0] == "swaymsg"


def test_wlr_randr_json_is_parsed_after_fallback() -> None:
    def runner(command, *args, **kwargs):
        if command[0] in {"hyprctl", "swaymsg"}:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")
        return completed([{"name": "eDP-1", "current_mode": {"width": 1366, "height": 768}}])

    assert MonitorDetector(runner).detect()[0].resolution == Resolution(1366, 768)


def test_all_failures_raise_monitor_error() -> None:
    def runner(*args, **kwargs):
        raise FileNotFoundError("missing")

    with pytest.raises(MonitorError):
        MonitorDetector(runner).detect()


def test_all_resolutions_merges_and_sorts() -> None:
    detector = MonitorDetector(
        lambda *args, **kwargs: completed([{"name": "DP-1", "width": 1920, "height": 1080}])
    )

    resolutions = detector.all_resolutions([Resolution(2560, 1440), Resolution(1920, 1080)])

    assert resolutions == [Resolution(2560, 1440), Resolution(1920, 1080)]

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from papercat.core.exceptions import ConfigError, LockBusyError
from papercat.core.types import Resolution
from papercat.daemon import cli


def test_lock_busy_returns_2(monkeypatch) -> None:
    monkeypatch.setattr(cli.ConfigStore, "load", lambda self: cli.Config())
    monkeypatch.setattr(cli, "setup_logger", lambda *args, **kwargs: cli.logging.getLogger("test"))
    monkeypatch.setattr(cli, "_select_subs", lambda args, store: [])
    monkeypatch.setattr(cli, "_build_crawler", lambda cfg, logger: raise_lock())

    assert cli.main(["crawl", "--all"]) == 2


def test_config_error_returns_3(monkeypatch) -> None:
    monkeypatch.setattr(cli.ConfigStore, "load", lambda self: raise_config())

    assert cli.main(["cleanup"]) == 3


def raise_lock():
    raise LockBusyError("busy")


def raise_config():
    raise ConfigError("bad")


# ---------------------------------------------------------------------------
# Additional coverage: full dispatch + every exit code path
# ---------------------------------------------------------------------------


class _StubReport:
    def __init__(self, failures: int) -> None:
        self.total_failures = failures


class _StubCrawler:
    def __init__(self, failures: int = 0) -> None:
        self._failures = failures

    async def crawl(self, subs: list[object]) -> _StubReport:
        return _StubReport(self._failures)


class _StubCleaner:
    def __init__(self) -> None:
        self.called = False

    def cleanup_auto(self) -> None:
        self.called = True


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "setup_logger", lambda *a, **k: logging.getLogger("test-cli"))
    monkeypatch.setattr(cli.ConfigStore, "load", lambda self: cli.Config())


def test_config_error_during_main_dispatch_returns_3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_select_subs", lambda a, s: (_ for _ in ()).throw(ConfigError("x")))
    assert cli.main(["crawl", "--all"]) == 3


def test_unhandled_exception_returns_4(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(cfg: Any, logger: Any) -> Any:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "_select_subs", lambda a, s: [])
    monkeypatch.setattr(cli, "_build_crawler", boom)
    assert cli.main(["crawl", "--all"]) == 4


def test_crawl_success_returns_0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_select_subs", lambda a, s: [])
    monkeypatch.setattr(cli, "_build_crawler", lambda cfg, logger: _StubCrawler(failures=0))
    assert cli.main(["crawl", "--all"]) == 0


def test_crawl_failures_returns_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_select_subs", lambda a, s: [])
    monkeypatch.setattr(cli, "_build_crawler", lambda cfg, logger: _StubCrawler(failures=2))
    assert cli.main(["crawl", "--all"]) == 1


def test_cleanup_command_runs_and_returns_0(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubCleaner()
    monkeypatch.setattr(cli, "_build_cleaner", lambda cfg, logger: stub)
    assert cli.main(["cleanup"]) == 0
    assert stub.called


def test_scan_monitors_prints_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _M:
        name = "HDMI-1"
        resolution = Resolution(width=2560, height=1440)

    monkeypatch.setattr(cli.MonitorDetector, "detect", lambda self: [_M()])
    assert cli.main(["scan-monitors"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [{"name": "HDMI-1", "width": 2560, "height": 1440}]


# ---------------------------------------------------------------------------
# _select_subs branches
# ---------------------------------------------------------------------------


class _Sub:
    def __init__(self, name: str) -> None:
        self.name = name


class _Store:
    def __init__(self, subs: list[_Sub]) -> None:
        self._subs = subs

    def list(self, enabled_only: bool = True) -> list[_Sub]:
        return list(self._subs)


def test_select_subs_all_returns_everything() -> None:
    args = type("A", (), {"all": True, "subscription": []})()
    store = _Store([_Sub("a"), _Sub("b")])
    assert [s.name for s in cli._select_subs(args, store)] == ["a", "b"]  # type: ignore[arg-type]


def test_select_subs_empty_request_returns_everything() -> None:
    args = type("A", (), {"all": False, "subscription": []})()
    store = _Store([_Sub("a"), _Sub("b")])
    assert len(cli._select_subs(args, store)) == 2  # type: ignore[arg-type]


def test_select_subs_explicit_filters() -> None:
    args = type("A", (), {"all": False, "subscription": ["b"]})()
    store = _Store([_Sub("a"), _Sub("b"), _Sub("c")])
    assert [s.name for s in cli._select_subs(args, store)] == ["b"]  # type: ignore[arg-type]


def test_select_subs_unknown_raises_config_error() -> None:
    args = type("A", (), {"all": False, "subscription": ["x"]})()
    store = _Store([_Sub("a")])
    with pytest.raises(ConfigError):
        cli._select_subs(args, store)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# argparse top-level
# ---------------------------------------------------------------------------


def test_missing_subcommand_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as info:
        cli.main([])
    assert info.value.code != 0


def test_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        cli.main(["--version"])
    assert info.value.code == 0
    assert "PaperCat" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _build_crawler / _build_cleaner assemble real wiring
# ---------------------------------------------------------------------------


def test_build_crawler_assembles(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "db.sqlite"
    wallpapers = tmp_path / "wp"
    thumbs = tmp_path / "thumbs"
    monkeypatch.setattr(cli, "DB_FILE", db)
    monkeypatch.setattr(cli, "THUMB_DIR", thumbs)
    monkeypatch.setattr(cli, "LOCK_FILE", tmp_path / "lock")
    cfg = cli.Config()
    cfg.wallpaper_dir = wallpapers
    crawler = cli._build_crawler(cfg, logging.getLogger("test"))
    assert crawler is not None


def test_build_cleaner_assembles(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "db.sqlite"
    wallpapers = tmp_path / "wp"
    thumbs = tmp_path / "thumbs"
    monkeypatch.setattr(cli, "DB_FILE", db)
    monkeypatch.setattr(cli, "THUMB_DIR", thumbs)
    monkeypatch.setattr(cli, "LOCK_FILE", tmp_path / "lock")
    cfg = cli.Config()
    cfg.wallpaper_dir = wallpapers
    cleaner = cli._build_cleaner(cfg, logging.getLogger("test"))
    assert cleaner is not None

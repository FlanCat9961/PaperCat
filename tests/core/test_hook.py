import subprocess
from dataclasses import dataclass
from pathlib import Path

from papercat.core.hook import HookRunner


@dataclass
class FakeHookConfig:
    post_download_command: str = ""
    timeout_seconds: int = 10


def test_empty_hook_does_not_call_runner(tmp_path) -> None:
    calls = []
    hook_runner = HookRunner(
        FakeHookConfig(), tmp_path, lambda *args, **kwargs: calls.append((args, kwargs))
    )

    hook_runner.run_post_download(tmp_path / "a.jpg")

    assert calls == []


def test_hook_replaces_placeholders(tmp_path) -> None:
    calls = []

    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0)

    downloaded = tmp_path / "wallpaper.jpg"
    HookRunner(FakeHookConfig("set {path} in {dir}"), tmp_path, runner).run_post_download(
        downloaded
    )

    assert calls[0][0][0] == f"set {downloaded} in {tmp_path}"
    assert calls[0][1]["shell"] is True
    assert calls[0][1]["timeout"] == 10
    assert calls[0][1]["capture_output"] is True


def test_hook_runner_exceptions_do_not_escape(tmp_path) -> None:
    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired("cmd", 1)

    HookRunner(FakeHookConfig("cmd"), Path(tmp_path), runner).run_post_download(tmp_path / "a.jpg")


def test_hook_nonzero_return_does_not_escape(tmp_path) -> None:
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 2)

    HookRunner(FakeHookConfig("cmd"), Path(tmp_path), runner).run_post_download(tmp_path / "a.jpg")

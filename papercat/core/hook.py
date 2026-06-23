import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol


class HookConfigLike(Protocol):
    post_download_command: str
    timeout_seconds: int


Runner = Callable[..., subprocess.CompletedProcess[str]]


class HookRunner:
    def __init__(
        self,
        cfg: HookConfigLike,
        wallpaper_dir: Path,
        runner: Runner = subprocess.run,
        logger: logging.Logger | None = None,
    ) -> None:
        self.cfg = cfg
        self.wallpaper_dir = wallpaper_dir
        self.runner = runner
        self.logger = logger or logging.getLogger(__name__)

    def run_post_download(self, downloaded_path: Path) -> None:
        command = self.cfg.post_download_command.strip()
        if not command:
            return

        command = command.replace("{path}", str(downloaded_path)).replace(
            "{dir}", str(self.wallpaper_dir)
        )
        try:
            result = self.runner(
                command,
                shell=True,
                timeout=self.cfg.timeout_seconds,
                capture_output=True,
            )
        except Exception as exc:
            self.logger.warning("post-download hook failed: %s", exc)
            return

        if result.returncode != 0:
            self.logger.warning("post-download hook exited with code %s", result.returncode)

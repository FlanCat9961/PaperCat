import os

import pytest

from papercat.core.exceptions import LockBusyError
from papercat.core.lock import ProcessLock


def test_process_lock_context_writes_pid_and_releases(tmp_path) -> None:
    path = tmp_path / "papercat.lock"

    with ProcessLock(path):
        assert path.read_text(encoding="utf-8") == f"{os.getpid()}\n"

    with ProcessLock(path):
        assert path.exists()


def test_second_lock_in_same_process_is_busy(tmp_path) -> None:
    path = tmp_path / "papercat.lock"
    first = ProcessLock(path)
    first.acquire()
    try:
        with pytest.raises(LockBusyError):
            ProcessLock(path).acquire()
    finally:
        first.release()

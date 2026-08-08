from __future__ import annotations

import fcntl
from pathlib import Path

from ...core.config import app_data_dir


class SingleInstanceLock:
    def __init__(self) -> None:
        lock_dir = app_data_dir()
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._path = lock_dir / "s2t.lock"
        self._fd = None

    def acquire(self) -> bool:
        try:
            self._fd = open(self._path, "w")
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            if self._fd:
                self._fd.close()
                self._fd = None
            return False

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
        except Exception:
            pass
        finally:
            self._fd = None
        try:
            self._path.unlink(missing_ok=True)
        except Exception:
            pass

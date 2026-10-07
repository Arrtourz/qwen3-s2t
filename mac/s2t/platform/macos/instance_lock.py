from __future__ import annotations

import fcntl
import logging
import os
from pathlib import Path

from ...core.config import app_data_dir


log = logging.getLogger(__name__)


class SingleInstanceLock:
    """Advisory whole-process lock so only one s2t runs at a time.

    The lock lives in the flock held on an open descriptor, not in the file's
    existence, and the kernel drops it when the process dies — including on
    SIGKILL. So the file is deliberately never deleted: unlinking it lets the
    next launch create a fresh inode and lock that successfully while the
    current holder still owns the old one, which is two running instances.
    A leftover zero-length lock file is harmless.
    """

    def __init__(self) -> None:
        lock_dir = app_data_dir()
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._path = lock_dir / "s2t.lock"
        self._fd: int | None = None

    def acquire(self) -> bool:
        fd = None
        try:
            # O_CREAT without O_TRUNC: a failed acquirer must not wipe the
            # holder's recorded pid on its way out.
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if fd is not None:
                holder = self._read_pid(fd)
                os.close(fd)
                if holder:
                    log.info("Another s2t instance is running (pid %s)", holder)
            return False

        # Record our pid only once the lock is ours, so the file always names
        # the real holder and `cat s2t.lock` answers "who has it?".
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.fsync(fd)
        except OSError:
            log.debug("Could not record pid in the lock file", exc_info=True)

        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            log.debug("Could not unlock the instance lock", exc_info=True)
        try:
            os.close(fd)
        except OSError:
            pass
        # Intentionally no unlink here — see the class docstring.

    @staticmethod
    def _read_pid(fd: int) -> str:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            return os.read(fd, 32).decode(errors="replace").strip()
        except OSError:
            return ""

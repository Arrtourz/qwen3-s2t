from __future__ import annotations

import ctypes
from ctypes import wintypes


ERROR_ALREADY_EXISTS = 183


class SingleInstanceLock:
    def __init__(self, name: str = "Local\\s2t-win") -> None:
        self.name = name
        self._handle = None

    def acquire(self) -> bool:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise OSError("CreateMutexW failed")

        self._handle = handle
        return ctypes.GetLastError() != ERROR_ALREADY_EXISTS

    def release(self) -> None:
        if not self._handle:
            return

        kernel32 = ctypes.windll.kernel32
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(self._handle)
        self._handle = None

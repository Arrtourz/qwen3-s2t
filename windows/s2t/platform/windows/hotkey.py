from __future__ import annotations

import logging
import threading
import time


log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
HOTKEY_ID = 1

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

SPECIAL_KEYS = {
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
}


class KeyboardHotkeyService:
    def __init__(self) -> None:
        self._binding = None
        self._hook = None
        self._hotkey = None
        self._callback = None
        self._last_ctrl_release = 0.0
        self._lock = threading.Lock()

    def register(self, hotkey: str, callback) -> None:
        if self._hotkey == hotkey and self._binding is not None:
            return

        self.unregister()

        self._callback = callback
        if hotkey == "double_ctrl":
            import keyboard

            self._hook = keyboard.hook(self._handle_key_event, suppress=False)
            self._binding = True
        else:
            self._binding = self._register_windows_hotkey(hotkey)
        self._hotkey = hotkey
        log.info("Registered hotkey %s", hotkey)

    def unregister(self) -> None:
        if self._binding is None and self._hook is None:
            return

        if self._hook is not None:
            import keyboard

            keyboard.unhook(self._hook)
            self._hook = None

        if isinstance(self._binding, _WindowsHotkeyBinding):
            self._unregister_windows_hotkey(self._binding)

        with self._lock:
            self._last_ctrl_release = 0.0
        log.info("Unregistered hotkey %s", self._hotkey)
        self._binding = None
        self._hotkey = None
        self._callback = None

    def _handle_key_event(self, event) -> None:
        if event.name not in {"ctrl", "left ctrl", "right ctrl"}:
            return

        if event.event_type != "up":
            return
        if self._hotkey != "double_ctrl":
            return

        now = time.monotonic()
        should_fire = False
        with self._lock:
            if now - self._last_ctrl_release <= 0.5:
                self._last_ctrl_release = 0.0
                should_fire = True
            else:
                self._last_ctrl_release = now

        if should_fire and self._callback is not None:
            self._callback()

    def _register_windows_hotkey(self, hotkey: str) -> "_WindowsHotkeyBinding":
        modifiers, vk = _parse_windows_hotkey(hotkey)
        binding = _WindowsHotkeyBinding(
            hotkey=hotkey,
            callback=self._callback,
            modifiers=modifiers,
            vk=vk,
        )
        binding.start()
        return binding

    @staticmethod
    def _unregister_windows_hotkey(binding: "_WindowsHotkeyBinding") -> None:
        binding.stop()


class _WindowsHotkeyBinding:
    def __init__(self, *, hotkey: str, callback, modifiers: int, vk: int) -> None:
        self.hotkey = hotkey
        self.callback = callback
        self.modifiers = modifiers
        self.vk = vk
        self.thread: threading.Thread | None = None
        self.thread_id: int | None = None
        self._started = threading.Event()
        self._error: Exception | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._started.wait(timeout=2.0)
        if self._error is not None:
            raise self._error
        if self.thread is None or not self.thread.is_alive():
            raise RuntimeError(f"Could not register hotkey {self.hotkey}")

    def stop(self) -> None:
        if self.thread_id is None:
            return

        import ctypes

        user32 = ctypes.windll.user32
        user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        if self.thread is not None:
            self.thread.join(timeout=1.0)

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt_x", wintypes.LONG),
                ("pt_y", wintypes.LONG),
            ]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self.thread_id = kernel32.GetCurrentThreadId()

        # Force a message queue on this thread before registering the hotkey.
        msg = MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)

        if not user32.RegisterHotKey(None, HOTKEY_ID, self.modifiers, self.vk):
            self._error = RuntimeError(f"Could not register hotkey {self.hotkey}: {ctypes.WinError()}")
            self._started.set()
            return

        self._started.set()

        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID and self.callback is not None:
                self.callback()

        user32.UnregisterHotKey(None, HOTKEY_ID)


def _parse_windows_hotkey(hotkey: str) -> tuple[int, int]:
    parts = [part.strip().lower() for part in hotkey.split("+") if part.strip()]
    if len(parts) < 2:
        raise RuntimeError(f"Unsupported hotkey format: {hotkey}")

    modifiers = 0
    key_name = parts[-1]
    for part in parts[:-1]:
        if part == "ctrl":
            modifiers |= MOD_CONTROL
        elif part == "alt":
            modifiers |= MOD_ALT
        elif part == "shift":
            modifiers |= MOD_SHIFT
        elif part in {"win", "windows"}:
            modifiers |= MOD_WIN
        else:
            raise RuntimeError(f"Unsupported hotkey modifier: {part}")

    if modifiers == 0:
        raise RuntimeError(f"Hotkey must include at least one modifier: {hotkey}")

    if len(key_name) == 1 and key_name.isalpha():
        return modifiers, ord(key_name.upper())
    if len(key_name) == 1 and key_name.isdigit():
        return modifiers, ord(key_name)
    if key_name.startswith("f") and key_name[1:].isdigit():
        index = int(key_name[1:])
        if 1 <= index <= 24:
            return modifiers, 0x70 + index - 1
    if key_name in SPECIAL_KEYS:
        return modifiers, SPECIAL_KEYS[key_name]

    raise RuntimeError(f"Unsupported hotkey key: {key_name}")

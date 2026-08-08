from __future__ import annotations

import logging
import threading
import time

from pynput import keyboard


log = logging.getLogger(__name__)

_MODIFIER_NAMES = {
    "ctrl": keyboard.Key.ctrl,
    "control": keyboard.Key.ctrl,
    "alt": keyboard.Key.alt,
    "option": keyboard.Key.alt,
    "shift": keyboard.Key.shift,
    "cmd": keyboard.Key.cmd,
    "command": keyboard.Key.cmd,
    "super": keyboard.Key.cmd,
}


class GlobalHotkeyService:
    def __init__(self) -> None:
        self._hotkey: str | None = None
        self._callback = None
        self._listener: keyboard.GlobalHotKeys | None = None
        self._double_ctrl_hook: keyboard.Listener | None = None
        self._last_ctrl_release = 0.0
        self._dc_lock = threading.Lock()

    def register(self, hotkey: str, callback) -> None:
        if self._hotkey == hotkey and (self._listener is not None or self._double_ctrl_hook is not None):
            return

        self.unregister()
        self._callback = callback
        self._hotkey = hotkey

        if hotkey == "double_ctrl":
            self._double_ctrl_hook = keyboard.Listener(on_release=self._on_release)
            self._double_ctrl_hook.start()
        else:
            combo = _parse_pynput_hotkey(hotkey)
            self._listener = keyboard.GlobalHotKeys({combo: self._fire})
            self._listener.start()

        log.info("Registered hotkey %s", hotkey)

    def unregister(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._double_ctrl_hook is not None:
            self._double_ctrl_hook.stop()
            self._double_ctrl_hook = None
        with self._dc_lock:
            self._last_ctrl_release = 0.0
        self._hotkey = None
        self._callback = None

    def _fire(self) -> None:
        if self._callback is not None:
            self._callback()

    def _on_release(self, key) -> None:
        if key not in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            return
        now = time.monotonic()
        should_fire = False
        with self._dc_lock:
            if now - self._last_ctrl_release <= 0.5:
                self._last_ctrl_release = 0.0
                should_fire = True
            else:
                self._last_ctrl_release = now
        if should_fire and self._callback is not None:
            self._callback()


def _parse_pynput_hotkey(hotkey: str) -> str:
    """Convert 'ctrl+alt+h' → '<ctrl>+<alt>+h' for pynput GlobalHotKeys."""
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    if len(parts) < 2:
        raise RuntimeError(f"Unsupported hotkey format: {hotkey}")

    result_parts: list[str] = []
    for part in parts[:-1]:
        if part not in _MODIFIER_NAMES:
            raise RuntimeError(f"Unsupported hotkey modifier: {part}")
        key_obj = _MODIFIER_NAMES[part]
        result_parts.append(f"<{key_obj.name}>")

    key_name = parts[-1]
    if len(key_name) == 1:
        result_parts.append(key_name)
    elif key_name.startswith("f") and key_name[1:].isdigit():
        result_parts.append(f"<f{key_name[1:]}>")
    else:
        try:
            key_obj = keyboard.Key[key_name]
            result_parts.append(f"<{key_obj.name}>")
        except KeyError:
            raise RuntimeError(f"Unsupported hotkey key: {key_name}")

    return "+".join(result_parts)

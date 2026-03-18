from __future__ import annotations

import logging
import threading
import time


log = logging.getLogger(__name__)


class KeyboardHotkeyService:
    def __init__(self, long_press_seconds: float = 2.0) -> None:
        self._binding = None
        self._hook = None
        self._hotkey = None
        self._callback = None
        self._long_press_callback = None
        self._last_ctrl_release = 0.0
        self._lock = threading.Lock()
        self._long_press_seconds = long_press_seconds
        self._long_press_timer = None
        self._long_press_fired = False

    def register(self, hotkey: str, callback, on_long_press=None) -> None:
        if self._hotkey == hotkey and self._binding is not None and self._hook is not None:
            return

        self.unregister()

        import keyboard

        self._callback = callback
        self._long_press_callback = on_long_press
        self._hook = keyboard.hook(self._handle_key_event, suppress=False)
        if hotkey != "double_ctrl":
            self._binding = keyboard.add_hotkey(hotkey, callback, suppress=False, trigger_on_release=False)
        else:
            self._binding = True
        self._hotkey = hotkey
        log.info("Registered hotkey %s", hotkey)

    def unregister(self) -> None:
        if self._binding is None and self._hook is None:
            return

        import keyboard

        if self._hook is not None:
            keyboard.unhook(self._hook)
        if self._binding not in {None, True}:
            keyboard.remove_hotkey(self._binding)
        self._cancel_long_press_timer()
        with self._lock:
            self._last_ctrl_release = 0.0
            self._long_press_fired = False
        log.info("Unregistered hotkey %s", self._hotkey)
        self._binding = None
        self._hook = None
        self._hotkey = None
        self._callback = None
        self._long_press_callback = None

    def _handle_key_event(self, event) -> None:
        if event.name not in {"ctrl", "left ctrl", "right ctrl"}:
            return

        if event.event_type == "down":
            self._handle_ctrl_down()
            return
        if event.event_type != "up":
            return

        if self._long_press_fired:
            self._cancel_long_press_timer()
            with self._lock:
                self._long_press_fired = False
                self._last_ctrl_release = 0.0
            return

        self._cancel_long_press_timer()
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

    def _handle_ctrl_down(self) -> None:
        if self._long_press_callback is None:
            return
        if self._long_press_timer is not None:
            return
        self._long_press_timer = threading.Timer(self._long_press_seconds, self._fire_long_press)
        self._long_press_timer.daemon = True
        self._long_press_timer.start()

    def _fire_long_press(self) -> None:
        self._long_press_timer = None
        with self._lock:
            self._long_press_fired = True
            self._last_ctrl_release = 0.0
        if self._long_press_callback is not None:
            self._long_press_callback()

    def _cancel_long_press_timer(self) -> None:
        if self._long_press_timer is None:
            return
        self._long_press_timer.cancel()
        self._long_press_timer = None

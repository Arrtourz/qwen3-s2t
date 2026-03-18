from __future__ import annotations

import time
from types import SimpleNamespace

from s2t.platform.windows.hotkey import KeyboardHotkeyService


def test_double_ctrl_triggers_callback() -> None:
    fired: list[str] = []
    service = KeyboardHotkeyService()
    service._hotkey = "double_ctrl"
    service._callback = lambda: fired.append("hotkey")

    service._handle_key_event(SimpleNamespace(name="ctrl", event_type="up"))
    service._handle_key_event(SimpleNamespace(name="ctrl", event_type="up"))

    assert fired == ["hotkey"]


def test_long_press_triggers_exit_callback() -> None:
    fired: list[str] = []
    service = KeyboardHotkeyService(long_press_seconds=0.05)
    service._hotkey = "double_ctrl"
    service._long_press_callback = lambda: fired.append("exit")

    service._handle_key_event(SimpleNamespace(name="ctrl", event_type="down"))
    time.sleep(0.08)
    service._handle_key_event(SimpleNamespace(name="ctrl", event_type="up"))

    assert fired == ["exit"]

from __future__ import annotations

from types import SimpleNamespace

import pytest

from s2t.platform.windows.hotkey import KeyboardHotkeyService, _WindowsHotkeyBinding, _parse_windows_hotkey


def test_double_ctrl_triggers_callback() -> None:
    fired: list[str] = []
    service = KeyboardHotkeyService()
    service._hotkey = "double_ctrl"
    service._callback = lambda: fired.append("hotkey")

    service._handle_key_event(SimpleNamespace(name="ctrl", event_type="up"))
    service._handle_key_event(SimpleNamespace(name="ctrl", event_type="up"))

    assert fired == ["hotkey"]


def test_parse_windows_hotkey_ctrl_alt_h() -> None:
    modifiers, vk = _parse_windows_hotkey("ctrl+alt+h")
    assert modifiers != 0
    assert vk == ord("H")


def test_parse_windows_hotkey_rejects_unknown_key() -> None:
    with pytest.raises(RuntimeError):
        _parse_windows_hotkey("ctrl+alt+unknown")


def test_standard_combo_uses_windows_binding(monkeypatch) -> None:
    service = KeyboardHotkeyService()
    captured: dict[str, object] = {}

    def fake_register(hotkey: str) -> _WindowsHotkeyBinding:
        captured["hotkey"] = hotkey
        return _WindowsHotkeyBinding(hotkey=hotkey, callback=lambda: None, modifiers=0, vk=0)

    monkeypatch.setattr(service, "_register_windows_hotkey", fake_register)
    monkeypatch.setattr(service, "_unregister_windows_hotkey", lambda _binding: None)

    service.register("ctrl+alt+h", lambda: None)

    assert captured["hotkey"] == "ctrl+alt+h"
    assert isinstance(service._binding, _WindowsHotkeyBinding)

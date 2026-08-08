from __future__ import annotations

import pytest

from s2t.platform.macos.hotkey import _parse_pynput_hotkey


def test_ctrl_alt_h():
    combo = _parse_pynput_hotkey("ctrl+alt+h")
    assert "<ctrl>" in combo
    assert "<alt>" in combo
    assert combo.endswith("+h")


def test_ctrl_shift_space():
    combo = _parse_pynput_hotkey("ctrl+shift+space")
    assert "<ctrl>" in combo
    assert "<shift>" in combo


def test_f_key():
    combo = _parse_pynput_hotkey("ctrl+f5")
    assert "<f5>" in combo


def test_missing_modifier_raises():
    with pytest.raises(RuntimeError):
        _parse_pynput_hotkey("h")


def test_unknown_modifier_raises():
    with pytest.raises(RuntimeError):
        _parse_pynput_hotkey("hyper+h")


def test_unknown_key_raises():
    with pytest.raises(RuntimeError):
        _parse_pynput_hotkey("ctrl+unknownkey999")

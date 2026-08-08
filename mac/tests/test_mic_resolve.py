from __future__ import annotations

from unittest.mock import patch

from s2t.platform.macos.meeting_audio import _looks_bluetooth, resolve_mic_device


def test_looks_bluetooth():
    assert _looks_bluetooth("Zhenyu's AirPods") is True
    assert _looks_bluetooth("Beats Studio") is True
    assert _looks_bluetooth("MacBook Pro Microphone") is False
    assert _looks_bluetooth("EVA-IP Microphone") is False


def test_configured_device_is_honored():
    # A pinned device must be returned as-is, no auto logic.
    assert resolve_mic_device("EVA-IP Microphone") == "EVA-IP Microphone"


def test_auto_picks_builtin_when_output_is_bluetooth():
    devices = [
        {"name": "AirPods", "max_input_channels": 1},
        {"name": "MacBook Pro Microphone", "max_input_channels": 1},
    ]

    def fake_query(kind=None):
        if kind == "output":
            return {"name": "Zhenyu's AirPods"}
        return devices

    with patch("sounddevice.query_devices", side_effect=fake_query):
        idx = resolve_mic_device("")
    assert idx == 1  # index of MacBook Pro Microphone


def test_auto_uses_default_when_output_not_bluetooth():
    def fake_query(kind=None):
        if kind == "output":
            return {"name": "MacBook Pro Speakers"}
        return [{"name": "MacBook Pro Microphone", "max_input_channels": 1}]

    with patch("sounddevice.query_devices", side_effect=fake_query):
        assert resolve_mic_device("") is None  # system default

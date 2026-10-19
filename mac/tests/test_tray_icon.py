from __future__ import annotations

import pytest

pytest.importorskip("rumps")

from s2t.platform.macos import tray


def _tray(monkeypatch, images_available=True):
    if not images_available:
        monkeypatch.setattr(tray, "_symbol_image", lambda name: None)
    noop = lambda: None
    return tray.MacTrayApp(noop, noop, noop, noop, noop, noop, noop, noop)


def test_uses_monochrome_symbols_and_no_text(monkeypatch):
    app = _tray(monkeypatch)
    for state in ("idle", "recording", "error", "loading"):
        app._show(state)
        assert app.title is None
        assert app._icon_nsimage is app._state_images[state]
        assert app._icon_nsimage.isTemplate()  # tinted by the system, not red


def test_recording_is_a_filled_circle_not_a_red_dot(monkeypatch):
    app = _tray(monkeypatch)
    app.set_recording(True)
    assert app._icon_nsimage is app._state_images["recording"]
    app.set_recording(False)
    assert app._icon_nsimage is app._state_images["idle"]


def test_falls_back_to_emoji_without_sf_symbols(monkeypatch):
    app = _tray(monkeypatch, images_available=False)
    app.set_recording(True)
    assert app.title == "🔴" and app._icon_nsimage is None

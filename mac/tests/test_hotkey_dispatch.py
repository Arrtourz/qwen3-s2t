from __future__ import annotations

import threading

from s2t.core.controller import SpeechToTextController


def _bare_controller():
    """Only the pieces the hotkey dispatch path touches."""
    c = object.__new__(SpeechToTextController)
    c._toggle_requested = threading.Event()
    c._init_status = None
    c.tray = None
    calls = []
    c.toggle_meeting = lambda: calls.append(threading.current_thread())
    return c, calls


def test_hotkey_from_listener_thread_does_not_toggle_there():
    # pynput invokes the callback on its own thread; toggling there would touch
    # AppKit (the status-bar title) off the main thread.
    c, calls = _bare_controller()
    t = threading.Thread(target=c._request_toggle)
    t.start(); t.join()
    assert calls == []
    assert c._toggle_requested.is_set()


def test_main_thread_tick_performs_the_toggle_once():
    c, calls = _bare_controller()
    c._request_toggle()
    c._main_thread_tick()
    c._main_thread_tick()  # flag consumed: no second toggle
    assert calls == [threading.current_thread()]


def test_tick_without_request_does_nothing():
    c, calls = _bare_controller()
    c._main_thread_tick()
    assert calls == []

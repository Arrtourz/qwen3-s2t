from __future__ import annotations

import sys
import types

from s2t.platform.macos import system_tap


def test_aggregate_never_autostarts_the_tap(monkeypatch):
    # tapautostart=1 made every other app's audio start stall ~35s while a
    # meeting ran here (Zoom failed to join). Capture the aggregate description
    # the tap builds and pin the setting.
    captured = {}

    class FakeDesc:
        def initStereoGlobalTapButExcludeProcesses_(self, _): return self
        def setName_(self, _): pass
        def setPrivate_(self, _): pass
        def UUID(self): return types.SimpleNamespace(UUIDString=lambda: "11111111-2222-3333-4444-555555555555")

    fake_objc = types.SimpleNamespace(lookUpClass=lambda _: types.SimpleNamespace(alloc=lambda: FakeDesc()))

    def create_agg(desc, _):
        captured.update(desc)
        return 1, None  # report failure so prepare() stops before touching PortAudio

    fake_ca = types.SimpleNamespace(
        AudioHardwareCreateProcessTap=lambda d, _: (0, 7),
        AudioHardwareCreateAggregateDevice=create_agg,
        AudioHardwareDestroyProcessTap=lambda _: None,
    )
    monkeypatch.setitem(sys.modules, "objc", fake_objc)
    monkeypatch.setitem(sys.modules, "CoreAudio", fake_ca)
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace())

    assert system_tap.SystemAudioTap().prepare() is False
    assert captured["tapautostart"] == 0
    assert captured["private"] == 1

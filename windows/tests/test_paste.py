from __future__ import annotations

import sys
from types import SimpleNamespace

from s2t.core.config import PasteConfig
from s2t.platform.windows.paste import build_paste_actions
from s2t.platform.windows.paste import WindowsPasteService


def test_block_strategy_keeps_text_as_single_paste() -> None:
    actions = build_paste_actions("hello\nworld", "block", terminal=False)
    assert actions == [("paste", "hello\nworld")]


def test_line_by_line_strategy_inserts_newline_steps() -> None:
    actions = build_paste_actions("hello\nworld", "line_by_line", terminal=False)
    assert actions == [("paste", "hello"), ("newline", None), ("paste", "world")]


def test_terminal_window_forces_single_block_paste() -> None:
    actions = build_paste_actions("hello\nworld", "line_by_line", terminal=True)
    assert actions == [("paste", "hello\nworld")]


def test_windows_paste_service_always_uses_ctrl_shift_v(monkeypatch) -> None:
    sent: list[str] = []
    copied: list[str] = []

    monkeypatch.setitem(sys.modules, "keyboard", SimpleNamespace(send=lambda combo: sent.append(combo)))
    monkeypatch.setitem(sys.modules, "pyperclip", SimpleNamespace(copy=lambda text: copied.append(text)))
    monkeypatch.setattr("s2t.platform.windows.paste.time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(WindowsPasteService, "_is_terminal_window", staticmethod(lambda: False))

    service = WindowsPasteService(PasteConfig(multiline_strategy="block", settle_delay_ms=0, line_delay_ms=0))
    service.paste_text("hello")

    assert copied == ["hello"]
    assert sent == ["ctrl+shift+v"]

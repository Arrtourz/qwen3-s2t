from __future__ import annotations

from s2t.platform.windows.paste import build_paste_actions


def test_block_strategy_keeps_text_as_single_paste() -> None:
    actions = build_paste_actions("hello\nworld", "block", terminal=False)
    assert actions == [("paste", "hello\nworld")]


def test_line_by_line_strategy_inserts_newline_steps() -> None:
    actions = build_paste_actions("hello\nworld", "line_by_line", terminal=False)
    assert actions == [("paste", "hello"), ("newline", None), ("paste", "world")]


def test_terminal_window_forces_single_block_paste() -> None:
    actions = build_paste_actions("hello\nworld", "line_by_line", terminal=True)
    assert actions == [("paste", "hello\nworld")]

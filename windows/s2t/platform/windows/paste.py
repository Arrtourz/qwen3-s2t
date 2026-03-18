from __future__ import annotations

import ctypes
from ctypes import wintypes
import time

from ...core.config import PasteConfig


TERMINAL_PROCESS_NAMES = {
    "windowsterminal.exe",
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
    "conhost.exe",
}


def build_paste_actions(
    text: str,
    multiline_strategy: str,
    *,
    terminal: bool,
) -> list[tuple[str, str | None]]:
    if terminal or multiline_strategy == "block" or "\n" not in text:
        return [("paste", text)]

    actions: list[tuple[str, str | None]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line:
            actions.append(("paste", line))
        if index < len(lines) - 1:
            actions.append(("newline", None))
    return actions


class WindowsPasteService:
    def __init__(self, config: PasteConfig) -> None:
        self.config = config

    def paste_text(self, text: str) -> None:
        import keyboard
        import pyperclip

        terminal = self._is_terminal_window()
        actions = build_paste_actions(
            text,
            self.config.multiline_strategy,
            terminal=terminal,
        )
        for action, payload in actions:
            if action == "paste":
                pyperclip.copy(payload or "")
                time.sleep(self.config.settle_delay_ms / 1000.0)
                keyboard.send("ctrl+shift+v" if terminal else "ctrl+v")
            elif action == "newline":
                keyboard.send("shift+enter")
            time.sleep(self.config.line_delay_ms / 1000.0)

    @staticmethod
    def _is_terminal_window() -> bool:
        try:
            import psutil
        except Exception:
            return False

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if not process_id.value:
            return False

        try:
            process_name = psutil.Process(process_id.value).name().lower()
        except Exception:
            return False
        return process_name in TERMINAL_PROCESS_NAMES

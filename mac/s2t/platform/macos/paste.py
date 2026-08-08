from __future__ import annotations

import subprocess
import time

import pyperclip
from pynput.keyboard import Controller as KeyboardController, Key

from ...core.config import PasteConfig


_keyboard = KeyboardController()


class MacPasteService:
    def __init__(self, config: PasteConfig) -> None:
        self.config = config

    def paste_text(self, text: str) -> None:
        if self.config.multiline_strategy == "block" or "\n" not in text:
            self._paste_block(text)
            return

        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line:
                self._paste_block(line)
            if index < len(lines) - 1:
                _keyboard.press(Key.shift)
                _keyboard.tap(Key.enter)
                _keyboard.release(Key.shift)
            time.sleep(self.config.line_delay_ms / 1000.0)

    def _paste_block(self, text: str) -> None:
        pyperclip.copy(text)
        time.sleep(self.config.settle_delay_ms / 1000.0)
        with _keyboard.pressed(Key.cmd):
            _keyboard.tap("v")

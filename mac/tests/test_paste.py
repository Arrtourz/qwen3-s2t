from __future__ import annotations

from unittest.mock import MagicMock, patch

from s2t.core.config import PasteConfig
from s2t.platform.macos.paste import MacPasteService


def test_paste_single_line():
    cfg = PasteConfig(multiline_strategy="block", settle_delay_ms=0, line_delay_ms=0)
    service = MacPasteService(cfg)
    copied = []
    with patch("s2t.platform.macos.paste.pyperclip.copy", side_effect=copied.append), \
         patch("s2t.platform.macos.paste._keyboard") as kb:
        kb.pressed.return_value.__enter__ = lambda s: s
        kb.pressed.return_value.__exit__ = MagicMock(return_value=False)
        service.paste_text("hello world")

    assert copied == ["hello world"]


def test_paste_multiline_block_strategy():
    cfg = PasteConfig(multiline_strategy="block", settle_delay_ms=0, line_delay_ms=0)
    service = MacPasteService(cfg)
    copied = []
    with patch("s2t.platform.macos.paste.pyperclip.copy", side_effect=copied.append), \
         patch("s2t.platform.macos.paste._keyboard") as kb:
        kb.pressed.return_value.__enter__ = lambda s: s
        kb.pressed.return_value.__exit__ = MagicMock(return_value=False)
        service.paste_text("line1\nline2")

    # block strategy: entire text pasted at once
    assert copied == ["line1\nline2"]

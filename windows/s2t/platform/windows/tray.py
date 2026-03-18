from __future__ import annotations

import threading
from typing import Callable

from PIL import Image, ImageDraw
import pystray


class WindowsTrayService:
    def __init__(
        self,
        on_trigger: Callable[[], None],
        on_stop: Callable[[], None],
        on_settings: Callable[[], None],
        on_reload: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self._on_exit = on_exit
        self._ready = threading.Event()
        self._icon = pystray.Icon(
            "s2t",
            icon=_build_icon(),
            title="s2t",
            menu=pystray.Menu(
                pystray.MenuItem("Start / Snapshot", lambda _icon, _item: on_trigger()),
                pystray.MenuItem("Stop", lambda _icon, _item: on_stop()),
                pystray.MenuItem("Settings", lambda _icon, _item: on_settings()),
                pystray.MenuItem("Reload Config", lambda _icon, _item: on_reload()),
                pystray.MenuItem("Open Logs", lambda _icon, _item: on_open_logs()),
                pystray.MenuItem("Exit", self._handle_exit),
            ),
        )

    def run(self) -> None:
        self._icon.run_detached(setup=self._setup_icon)
        self._ready.wait(timeout=5)

    def stop(self) -> None:
        self._icon.stop()

    def notify(self, title: str, message: str) -> None:
        try:
            self._icon.notify(message, title=title)
        except Exception:
            pass

    def _handle_exit(self, _icon, _item) -> None:
        self._on_exit()

    def _setup_icon(self, icon) -> None:
        icon.visible = True
        self._ready.set()


def _build_icon() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (23, 38, 44, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 56, 56), radius=14, fill=(236, 180, 77, 255))
    draw.ellipse((22, 16, 42, 36), fill=(23, 38, 44, 255))
    draw.rectangle((29, 34, 35, 48), fill=(23, 38, 44, 255))
    draw.rectangle((22, 46, 42, 50), fill=(23, 38, 44, 255))
    return image

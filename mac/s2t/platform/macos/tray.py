from __future__ import annotations

import logging
import subprocess
from typing import Callable

import rumps


log = logging.getLogger(__name__)

# Menu-bar look (user's pick from rendered options): a small monochrome circle,
# hollow when ready and filled while recording, so the menu bar stays quiet. As
# template images they follow light/dark menu bars; nothing is ever red.
# (state: SF Symbol, drawn greyed-out, emoji fallback if the symbol is missing)
_STATES = {
    "loading": ("circle", True, "⏳"),
    "idle": ("circle", False, "🎙"),
    "recording": ("circle.fill", False, "🔴"),
    "error": ("exclamationmark.circle", False, "⚠️"),
}
_SYMBOL_POINT_SIZE = 9.0


def _symbol_image(name: str):
    """A template NSImage for an SF Symbol, or None if unavailable."""
    try:
        from AppKit import NSFontWeightRegular, NSImage, NSImageSymbolConfiguration

        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, "s2t")
        if image is None:
            return None
        config = NSImageSymbolConfiguration.configurationWithPointSize_weight_(
            _SYMBOL_POINT_SIZE, NSFontWeightRegular
        )
        image = image.imageWithSymbolConfiguration_(config) or image
        image.setTemplate_(True)  # tinted by the system to match the menu bar
        return image
    except Exception:
        log.debug("SF Symbol %s unavailable", name, exc_info=True)
        return None


class MacTrayApp(rumps.App):
    def __init__(
        self,
        on_start_meeting: Callable[[], None],
        on_end_meeting: Callable[[], None],
        on_settings: Callable[[], None],
        on_reload: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_open_transcript_folder: Callable[[], None],
        on_memory_report: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        super().__init__("s2t", title=None, quit_button=None)
        self._state_images = {state: _symbol_image(symbol) for state, (symbol, _, _) in _STATES.items()}
        self._show("loading")
        self._on_start_meeting = on_start_meeting
        self._on_end_meeting = on_end_meeting
        self._on_settings = on_settings
        self._on_reload = on_reload
        self._on_open_logs = on_open_logs
        self._on_open_transcript_folder = on_open_transcript_folder
        self._on_memory_report = on_memory_report
        self._on_exit = on_exit

        self._start_item = rumps.MenuItem("Start Meeting", callback=self._start_meeting)
        self._end_item = rumps.MenuItem("End Meeting", callback=self._end_meeting)
        self.menu = [
            self._start_item,
            self._end_item,
            None,
            rumps.MenuItem("Settings", callback=self._settings),
            rumps.MenuItem("Reload Config", callback=self._reload),
            rumps.MenuItem("Open Logs", callback=self._open_logs),
            rumps.MenuItem("Open Transcript Folder", callback=self._open_transcript_folder),
            rumps.MenuItem("Memory Report", callback=self._memory_report),
            None,
            rumps.MenuItem("Exit", callback=self._exit),
        ]
        self._set_meeting_menu_state(active=False)

    def _start_meeting(self, _) -> None:
        self._on_start_meeting()

    def _end_meeting(self, _) -> None:
        self._on_end_meeting()

    def _settings(self, _) -> None:
        self._on_settings()

    def _reload(self, _) -> None:
        self._on_reload()

    def _open_logs(self, _) -> None:
        self._on_open_logs()

    def _open_transcript_folder(self, _) -> None:
        self._on_open_transcript_folder()

    def _memory_report(self, _) -> None:
        self._on_memory_report()

    def _exit(self, _) -> None:
        self._on_exit()
        rumps.quit_application()

    def notify(self, title: str, message: str) -> None:
        try:
            rumps.notification(title=title, subtitle="", message=message, sound=False)
        except Exception:
            log.debug("Notification failed", exc_info=True)

    def set_recording(self, active: bool) -> None:
        self._show("recording" if active else "idle")
        self._set_meeting_menu_state(active=active)

    def set_loading(self, loading: bool) -> None:
        self._show("loading" if loading else "idle")

    def set_error(self) -> None:
        self._show("error")

    def _show(self, state: str) -> None:
        """Switch the status item to `state`. Main thread only."""
        _symbol, greyed, emoji = _STATES[state]
        image = self._state_images.get(state)
        if image is None:  # no SF Symbols: keep the old emoji look
            self._icon_nsimage = None
            self.title = emoji
        else:
            # rumps reads _icon_nsimage when the status item is first built and
            # on setStatusBarIcon(); set the image before clearing the title so
            # rumps never falls back to showing the app name.
            self._icon_nsimage = image
            self.title = None
        nsapp = getattr(self, "_nsapp", None)
        if nsapp is None:  # before run(): applied when the status item is created
            return
        try:
            nsapp.setStatusBarIcon()
            button = nsapp.nsstatusitem.button()
            if button is not None:
                button.setAppearsDisabled_(greyed)
        except Exception:
            log.debug("Could not update status item", exc_info=True)

    def set_ready_poller(self, callback) -> None:
        """Register a callback polled on the main thread (~4x/sec).

        Background threads must not touch AppKit UI directly; they set flags and
        this timer applies them on the main run loop.
        """
        self._ready_timer = rumps.Timer(lambda _sender: callback(), 0.25)
        self._ready_timer.start()

    def _set_meeting_menu_state(self, *, active: bool) -> None:
        try:
            self._start_item.set_callback(None if active else self._start_meeting)
            self._end_item.set_callback(self._end_meeting if active else None)
        except Exception:
            log.debug("Could not update meeting menu state", exc_info=True)

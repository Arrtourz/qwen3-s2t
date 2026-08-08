from __future__ import annotations

import logging
import subprocess
from typing import Callable

import rumps


log = logging.getLogger(__name__)


class MacTrayApp(rumps.App):
    def __init__(
        self,
        on_start_meeting: Callable[[], None],
        on_end_meeting: Callable[[], None],
        on_settings: Callable[[], None],
        on_reload: Callable[[], None],
        on_open_logs: Callable[[], None],
        on_open_transcript_folder: Callable[[], None],
        on_enroll_voice: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        super().__init__("s2t", title="🎙", quit_button=None)
        self._on_start_meeting = on_start_meeting
        self._on_end_meeting = on_end_meeting
        self._on_settings = on_settings
        self._on_reload = on_reload
        self._on_open_logs = on_open_logs
        self._on_open_transcript_folder = on_open_transcript_folder
        self._on_enroll_voice = on_enroll_voice
        self._on_exit = on_exit

        self._start_item = rumps.MenuItem("Start Meeting", callback=self._start_meeting)
        self._end_item = rumps.MenuItem("End Meeting", callback=self._end_meeting)
        self.menu = [
            self._start_item,
            self._end_item,
            None,
            rumps.MenuItem("Enroll My Voice", callback=self._enroll_voice),
            rumps.MenuItem("Settings", callback=self._settings),
            rumps.MenuItem("Reload Config", callback=self._reload),
            rumps.MenuItem("Open Logs", callback=self._open_logs),
            rumps.MenuItem("Open Transcript Folder", callback=self._open_transcript_folder),
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

    def _enroll_voice(self, _) -> None:
        self._on_enroll_voice()

    def _exit(self, _) -> None:
        self._on_exit()
        rumps.quit_application()

    def notify(self, title: str, message: str) -> None:
        try:
            rumps.notification(title=title, subtitle="", message=message, sound=False)
        except Exception:
            log.debug("Notification failed", exc_info=True)

    def set_recording(self, active: bool) -> None:
        self.title = "🔴" if active else "🎙"
        self._set_meeting_menu_state(active=active)

    def set_loading(self, loading: bool) -> None:
        self.title = "⏳" if loading else "🎙"

    def set_error(self) -> None:
        self.title = "⚠️"

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

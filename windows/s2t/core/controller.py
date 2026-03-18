from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path
import queue
import signal
import threading
import time

import numpy as np

from ..logging_utils import configure_logging
from ..platform.windows.audio import SoundDeviceAudioCapture
from ..platform.windows.hotkey import KeyboardHotkeyService
from ..platform.windows.paste import WindowsPasteService
from ..platform.windows.settings import SettingsWindow
from ..platform.windows.tray import WindowsTrayService
from .backend import ASRBackend, build_backend
from .config import AppConfig, ConfigError, default_config_path, default_log_file, load_config


log = logging.getLogger(__name__)


class SpeechToTextController:
    def __init__(
        self,
        config_path: Path | None = None,
        recording_mode_override: str | None = None,
        model_variant_override: str | None = None,
        device_override: str | None = None,
    ) -> None:
        if config_path is None or str(config_path) in {"", "."} or config_path.is_dir():
            self.config_path = default_config_path()
        else:
            self.config_path = config_path
        self.recording_mode_override = recording_mode_override
        self.model_variant_override = model_variant_override
        self.device_override = device_override
        self.config: AppConfig | None = None

        self.backend: ASRBackend | None = None
        self.audio = None
        self.paste = None
        self.hotkey = None
        self.tray = None
        self.settings_window = None

        self._toggle_lock = threading.Lock()
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_started = False

    def run(self) -> None:
        self._load_runtime(initial=True)
        assert self.tray is not None
        self._install_signal_handlers()
        self.tray.run()
        try:
            while not self._stop_event.wait(0.2):
                pass
        except KeyboardInterrupt:
            self.shutdown()

    def _load_runtime(self, initial: bool) -> None:
        config = load_config(self.config_path)
        if self.recording_mode_override is not None:
            config = replace(
                config,
                recording=replace(config.recording, mode=self.recording_mode_override),
            )
        if self.model_variant_override is not None:
            variant_map = {
                "0.6b": "Qwen/Qwen3-ASR-0.6B",
                "1.7b": "Qwen/Qwen3-ASR-1.7B",
            }
            config = replace(
                config,
                model=replace(
                    config.model,
                    variant=self.model_variant_override,
                    path_or_id=variant_map[self.model_variant_override],
                ),
            )
        if self.device_override is not None:
            config = replace(
                config,
                model=replace(config.model, device=self.device_override),
            )
        configure_logging(default_log_file(), config.logging.level)

        previous = self.config
        self.config = config

        if self.backend is None or previous is None or previous.model != config.model:
            self.backend = build_backend(config.model)
            self.backend.load_model()

        if self.audio is None or previous is None or previous.recording != config.recording:
            if self.audio is not None:
                self.audio.close()
            self.audio = SoundDeviceAudioCapture(config.recording)

        if self.paste is None or previous is None or previous.paste != config.paste:
            self.paste = WindowsPasteService(config.paste)

        if self.hotkey is None:
            self.hotkey = KeyboardHotkeyService()
        self.hotkey.register(config.hotkey, self.handle_hotkey, on_long_press=self.handle_long_press_exit)

        if self.tray is None:
            self.settings_window = SettingsWindow(
                config=config,
                config_path=self.config_path,
                on_saved=self.reload_config,
            )
            self.tray = WindowsTrayService(
                on_trigger=self.handle_hotkey,
                on_stop=self.stop_recording,
                on_settings=self.open_settings,
                on_reload=self.reload_config,
                on_open_logs=self.open_logs,
                on_exit=self.shutdown,
            )
        elif self.settings_window is not None:
            self.settings_window._config = config

        if initial and not self._worker_started:
            self._worker.start()
            self._worker_started = True

        self._notify("s2t", f"Ready. Hotkey: {config.hotkey}")
        log.info("Runtime loaded from %s", self.config_path)

    def reload_config(self) -> None:
        try:
            if self.audio is not None:
                self.audio.close()
            if self.hotkey is not None:
                self.hotkey.unregister()
            self._load_runtime(initial=False)
        except ConfigError as exc:
            log.exception("Failed to reload config")
            self._notify("Config error", str(exc))
        except Exception as exc:
            log.exception("Unexpected reload failure")
            self._notify("Reload failed", str(exc))

    def handle_hotkey(self) -> None:
        if self.config is None or self.audio is None:
            return

        with self._toggle_lock:
            if self.config.recording.mode == "manual":
                if self.audio.is_recording():
                    self.stop_recording()
                else:
                    self.start_recording()
                return

            if not self.audio.is_recording():
                self.start_recording()
            else:
                self.snapshot_recording()

    def start_recording(self) -> None:
        if self.config is None or self.audio is None:
            return
        ok = self.audio.start_recording(windowed=self.config.recording.mode == "continuous")
        if not ok:
            self._notify("Microphone error", "Could not open the default microphone")
            return
        self._beep(620, 120)
        log.info("Recording started")

    def stop_recording(self) -> None:
        if self.audio is None:
            return
        data = self.audio.stop_recording()
        self._queue_audio(data)

    def snapshot_recording(self) -> None:
        if self.audio is None:
            return
        data = self.audio.snapshot_recording()
        self._queue_audio(data)

    def _queue_audio(self, data: np.ndarray | None) -> None:
        if data is None or len(data) < 1600:
            log.warning("Captured audio too short; ignoring")
            self._beep(320, 180)
            return
        rms = float(np.sqrt(np.mean(data**2)))
        log.info("Queued %.2fs of audio (RMS=%.5f)", len(data) / 16000.0, rms)
        self._queue.put(data)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                audio_data = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                assert self.backend is not None
                assert self.paste is not None
                assert self.config is not None

                text = self.backend.transcribe(audio_data, language=self.config.language)
                if not text:
                    self._beep(280, 180)
                    self._notify("No speech detected", "The recording did not produce text")
                    continue

                self.paste.paste_text(text)
                self._beep(880, 160)
                self._notify("Transcription ready", text[:120])
                log.info("Transcribed text: %r", text)
            except Exception as exc:
                log.exception("Processing failed")
                self._notify("Transcription failed", str(exc))

    def open_logs(self) -> None:
        log_file = default_log_file()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(log_file.parent))

    def open_settings(self) -> None:
        if self.config is None:
            return
        if self.settings_window is None:
            self.settings_window = SettingsWindow(
                config=self.config,
                config_path=self.config_path,
                on_saved=self.reload_config,
            )
        else:
            self.settings_window._config = self.config
        self.settings_window.show()

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        log.info("Shutting down")
        self._stop_event.set()
        if self.hotkey is not None:
            self.hotkey.unregister()
        if self.audio is not None:
            self.audio.close()
        if self.tray is not None:
            self.tray.stop()

    def handle_long_press_exit(self) -> None:
        log.info("Long-press Ctrl detected; exiting")
        self._beep(440, 250)
        self.shutdown()

    def _install_signal_handlers(self) -> None:
        def _handle_signal(signum, _frame) -> None:
            log.info("Received signal %s", signum)
            self.shutdown()

        signal.signal(signal.SIGINT, _handle_signal)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handle_signal)

    def _notify(self, title: str, message: str) -> None:
        if self.tray is not None:
            self.tray.notify(title, message)
        else:
            log.info("%s: %s", title, message)

    @staticmethod
    def _beep(freq: int, duration_ms: int) -> None:
        def _play() -> None:
            try:
                import winsound

                winsound.Beep(freq, duration_ms)
            except Exception:
                time.sleep(duration_ms / 1000.0)

        threading.Thread(target=_play, daemon=True).start()

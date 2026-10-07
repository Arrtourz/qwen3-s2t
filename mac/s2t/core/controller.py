from __future__ import annotations

import logging
import queue
import signal
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np

from ..logging_utils import configure_logging
from ..platform.macos.hotkey import GlobalHotkeyService
from ..platform.macos.meeting_audio import MeetingRecorder
from ..platform.macos.tray import MacTrayApp
from .backend import ASRBackend, build_backend
from .config import (
    AppConfig,
    ConfigError,
    default_config_path,
    default_log_file,
    default_transcript_dir,
    load_config,
    normalize_model_config,
)
from .memory_debug import MemoryMonitor, enabled_from_env
from .transcript import TranscriptWriter
from .voice import is_filler, voice_metrics


log = logging.getLogger(__name__)

# Upper bound on utterances waiting to be transcribed. Transcription is much
# faster than real time, so reaching this means something is badly wrong.
MAX_PENDING_SEGMENTS = 32


class SpeechToTextController:
    def __init__(
        self,
        config_path: Path | None = None,
        provider_override: str | None = None,
        model_variant_override: str | None = None,
        device_override: str | None = None,
    ) -> None:
        self.config_path = config_path or default_config_path()
        self.provider_override = provider_override
        self.model_variant_override = model_variant_override
        self.device_override = device_override
        self.config: AppConfig | None = None

        self.backend: ASRBackend | None = None
        self.recorder: MeetingRecorder | None = None
        self.hotkey: GlobalHotkeyService | None = None
        self.tray: MacTrayApp | None = None
        self.transcript: TranscriptWriter | None = None
        self.memory_monitor: MemoryMonitor | None = None

        self._meeting_lock = threading.Lock()
        self._meeting_active = False
        self._model_ready = False
        self._hotkey_registered = False
        # Queue of (speaker_label, audio_16k) utterances awaiting transcription.
        # Bounded: a segment can be up to max_segment_seconds of float32 audio
        # (~1.3MB at 20s), so an unbounded queue would grow without limit if
        # transcription ever fell behind speech. Oldest waiting segments are
        # dropped first — a stale backlog is worth less than keeping up.
        self._queue: queue.Queue[tuple[str, np.ndarray]] = queue.Queue(maxsize=MAX_PENDING_SEGMENTS)
        self._stop_event = threading.Event()
        self._toggle_requested = threading.Event()
        self._idle_timer: threading.Timer | None = None
        self._finisher: threading.Thread | None = None
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_started = False

    def run(self) -> None:
        # Build the menu-bar UI immediately so the icon appears at once, then
        # load the (slow) ASR model on a background thread. rumps.run() must own
        # the main thread, and AppKit UI (the status-bar title) may only be
        # touched on the main thread — so the background thread only sets flags,
        # and a main-thread rumps timer applies the icon/notification changes.
        self._resolve_config()
        self._build_ui()
        self._install_signal_handlers()
        assert self.tray is not None

        # (status, message) set by the background thread, consumed on main thread.
        self._init_status: str | None = None
        self._init_message: str = ""
        self.tray.set_ready_poller(self._main_thread_tick)

        threading.Thread(target=self._background_init, daemon=True).start()
        self.tray.run()

    def _main_thread_tick(self) -> None:
        """Runs on the main thread (rumps timer, ~4x/sec)."""
        self._apply_init_status()
        # A hotkey press arrives on pynput's listener thread; acting on it there
        # would update the status-bar title off the main thread. It only sets
        # this flag, and the toggle happens here instead.
        if self._toggle_requested.is_set():
            self._toggle_requested.clear()
            self.toggle_meeting()

    def _request_toggle(self) -> None:
        """Hotkey callback: safe to call from any thread."""
        self._toggle_requested.set()

    def _apply_init_status(self) -> None:
        """Applies the pending background-init result. Main thread only."""
        status = getattr(self, "_init_status", None)
        if status is None:
            return
        self._init_status = None
        if self.tray is None:
            return
        if status == "ok":
            self.tray.set_loading(False)
            self._register_hotkey_main_thread()
            # Launch silently: the menu-bar icon switching from ⏳ to 🎙 already
            # says "ready". Only a failed startup gets a notification.
        elif status == "error":
            self.tray.set_error()
            self.tray.notify("s2t startup failed", self._init_message)

    def _resolve_config(self) -> None:
        config = load_config(self.config_path)

        if self.provider_override is not None:
            reset = config.model.provider != self.provider_override
            config = replace(
                config,
                model=replace(
                    config.model,
                    provider=self.provider_override,
                    path_or_id="" if reset else config.model.path_or_id,
                    binary_path="" if reset else config.model.binary_path,
                ),
            )
        if self.model_variant_override is not None:
            variant_map = {"0.6b": "Qwen/Qwen3-ASR-0.6B", "1.7b": "Qwen/Qwen3-ASR-1.7B"}
            path_or_id = variant_map[self.model_variant_override] if config.model.provider == "qwen3_asr" else ""
            config = replace(config, model=replace(config.model, variant=self.model_variant_override, path_or_id=path_or_id))
        if self.device_override is not None:
            config = replace(config, model=replace(config.model, device=self.device_override))

        config = replace(config, model=normalize_model_config(config.model))
        configure_logging(default_log_file(), config.logging.level)
        self.config = config

    def _build_ui(self) -> None:
        assert self.config is not None
        if self.tray is None:
            self.tray = MacTrayApp(
                on_start_meeting=self.start_meeting,
                on_end_meeting=self.end_meeting,
                on_settings=self.open_settings,
                on_reload=self.reload_config,
                on_open_logs=self.open_logs,
                on_open_transcript_folder=self.open_transcript_folder,
                on_memory_report=self.log_memory_report,
                on_exit=self.shutdown,
            )
        self.tray.set_loading(True)

    def _background_init(self) -> None:
        try:
            self._load_heavy(previous=None)
            self._model_ready = True
            self._init_status = "ok"
            self._schedule_idle_unload()
            log.info("Runtime loaded from %s", self.config_path)
        except Exception as exc:
            log.exception("Background init failed")
            self._init_message = str(exc)
            self._init_status = "error"

    def _load_heavy(self, previous: AppConfig | None) -> None:
        config = self.config
        assert config is not None

        if self.backend is None or previous is None or previous.model != config.model:
            self.backend = build_backend(config.model)
            self.backend.load_model()

        # Recorder is rebuilt on any recording/meeting change (only while idle).
        if self.recorder is None or previous is None or previous.recording != config.recording or previous.meeting != config.meeting:
            self.recorder = MeetingRecorder(config.recording, config.meeting)

        if self.transcript is None or previous is None or previous.transcript != config.transcript:
            if self.transcript is not None:
                self.transcript.close_session()
            self.transcript = TranscriptWriter(config.transcript)


        if not self._worker_started:
            self._worker.start()
            self._worker_started = True

        self._start_memory_monitor()

    def _start_memory_monitor(self) -> None:
        """Start the memory monitor if config or S2T_MEMORY_DEBUG asks for it."""
        if self.memory_monitor is not None or self.config is None:
            return
        if not (self.config.debug.memory_monitor or enabled_from_env()):
            return
        self.memory_monitor = MemoryMonitor(
            self, interval_seconds=self.config.debug.memory_monitor_interval_seconds
        )
        self.memory_monitor.start()

    def _register_hotkey_main_thread(self) -> None:
        """Register the OPTIONAL global hotkey.

        The app is designed to be driven entirely from the menu bar, so the
        hotkey is opt-in: set hotkey = "" (or "none") in config to disable it.
        pynput's macOS listener installs a CoreGraphics event tap which is
        fragile inside a packaged .app (sandbox/Accessibility), so we default to
        OFF and never let a hotkey failure take down the app."""
        if self.config is None or self._hotkey_registered:
            return
        self._hotkey_registered = True
        hk = (self.config.hotkey or "").strip().lower()
        if hk in {"", "none", "off", "disabled"}:
            log.info("Hotkey disabled; use the menu to control meetings")
            return
        if self.hotkey is None:
            self.hotkey = GlobalHotkeyService()
        try:
            self.hotkey.register(self.config.hotkey, self._request_toggle)
        except Exception:
            log.warning("Hotkey registration failed (Accessibility not granted?); use the menu instead", exc_info=True)

    def reload_config(self) -> None:
        try:
            if self._meeting_active:
                self._notify("s2t", "End the current meeting before reloading config")
                return
            if self.hotkey is not None:
                self.hotkey.unregister()
                self._hotkey_registered = False
            previous = self.config
            self._resolve_config()
            self._load_heavy(previous=previous)
            # reload_config runs on the main thread (menu action), so re-registering
            # the hotkey here is safe.
            self._register_hotkey_main_thread()
            self._schedule_idle_unload()
            self._notify("s2t", "Config reloaded.")
        except ConfigError as exc:
            log.exception("Failed to reload config")
            self._notify("Config error", str(exc))
        except Exception as exc:
            log.exception("Unexpected reload failure")
            self._notify("Reload failed", str(exc))

    def toggle_meeting(self) -> None:
        if self._meeting_active:
            self.end_meeting()
        else:
            self.start_meeting()

    def start_meeting(self) -> None:
        with self._meeting_lock:
            if self._meeting_active or self.config is None:
                return
            if not self._model_ready or self.recorder is None:
                self._notify("s2t", "Still loading the model… try again in a moment.")
                return

            # The previous meeting may still be transcribing its last segments
            # into its own file; let it finish before a new file is opened.
            if self._finisher is not None and self._finisher.is_alive():
                self._finisher.join(timeout=30)
            self._cancel_idle_unload()
            if self.backend is not None and not self.backend.is_loaded:
                # Unloaded while idle. Reload in the background so recording
                # starts now; early segments wait in the queue (the worker blocks
                # on the backend lock until the model is back).
                log.info("Reloading ASR model for the new meeting")
                threading.Thread(target=self.backend.load_model, daemon=True, name="asr-reload").start()

            if self.config.transcript.enabled and self.transcript is not None:
                self.transcript.open_session()

            started, labels = self.recorder.start(self._on_segment)
            if not started:
                self._notify("Audio error", "Could not open any input device")
                if self.transcript is not None:
                    self.transcript.close_session()
                return

            self._meeting_active = True
            if self.tray is not None:
                self.tray.set_recording(True)
            # The app makes no sound at all (user preference); the menu-bar
            # icon turning 🔴 is the signal. Start shows no banner either.
            log.info("Meeting started with streams: %s", labels)

    def end_meeting(self) -> None:
        with self._meeting_lock:
            if not self._meeting_active or self.recorder is None:
                return
            self.recorder.stop()
            self._meeting_active = False
            if self.tray is not None:
                self.tray.set_recording(False)
            log.info("Meeting ended")
            # recorder.stop() just flushed each stream's last utterance into the
            # queue. Closing the transcript here dropped those: the worker wrote
            # them after the file was closed, so a meeting's final sentence
            # vanished. Finish on a thread so the menu stays responsive.
            self._finisher = threading.Thread(target=self._finish_meeting, daemon=True, name="meeting-finish")
            self._finisher.start()

    def _finish_meeting(self) -> None:
        """Drain the queue into this meeting's file, close it, then free memory."""
        self._queue.join()
        if self.transcript is not None:
            self.transcript.close_session()
        self._notify("Meeting ended", "Transcript saved")
        # The app stays resident between meetings: give back the GPU cache now,
        # and the model itself after the idle timeout.
        if self.backend is not None:
            self.backend.release_cached_memory(min_slack_bytes=0)
        if self.memory_monitor is not None:
            self.memory_monitor.log_once()
        self._schedule_idle_unload()

    def _schedule_idle_unload(self) -> None:
        self._cancel_idle_unload()
        minutes = self.config.memory.idle_unload_minutes if self.config is not None else 0
        if minutes <= 0 or self._stop_event.is_set():
            return
        self._idle_timer = threading.Timer(minutes * 60, self._idle_unload)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _cancel_idle_unload(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _idle_unload(self) -> None:
        # Under the meeting lock so a meeting cannot start mid-unload.
        with self._meeting_lock:
            if self._meeting_active or self.backend is None or not self._queue.empty():
                return
            self.backend.unload()
        if self.memory_monitor is not None:
            self.memory_monitor.log_once()

    def _on_segment(self, speaker: str, audio: np.ndarray) -> None:
        """Called from an audio thread when a segmenter completes an utterance."""
        if audio is None or len(audio) < 1600:
            return
        # Drop blank / noise / distant-voice segments so the ASR model isn't fed
        # non-speech (Qwen-ASR hallucinates filler like "嗯"/"The." on it).
        m = self.config.meeting if self.config is not None else None
        frame_rms = m.voice_frame_rms if m is not None else 0.045
        max_zcr = m.voice_max_zcr if m is not None else 0.32
        min_ratio = m.voice_min_voiced_ratio if m is not None else 0.30
        rms, zcr, ratio, ok = voice_metrics(
            audio, frame_rms=frame_rms, max_zcr=max_zcr, min_voiced_ratio=min_ratio
        )
        dur = len(audio) / 16000.0
        if not ok:
            log.info(
                "Dropped non-voice %.2fs from %s (voiced=%.0f%% RMS=%.5f ZCR=%.3f; "
                "need voiced>=%.0f%% frame_rms>=%.3f)",
                dur, speaker, ratio * 100, rms, zcr, min_ratio * 100, frame_rms,
            )
            return
        log.info(
            "Queued %.2fs from %s (voiced=%.0f%% RMS=%.5f ZCR=%.3f)",
            dur, speaker, ratio * 100, rms, zcr,
        )
        self._enqueue(speaker, audio)

    def _enqueue(self, speaker: str, audio: np.ndarray) -> None:
        """Queue an utterance, evicting the oldest if the backlog is full."""
        while True:
            try:
                self._queue.put_nowait((speaker, audio))
                return
            except queue.Full:
                try:
                    dropped, stale = self._queue.get_nowait()
                except queue.Empty:
                    continue  # the worker drained it first; retry the put
                self._queue.task_done()  # evicted: count it as handled for join()
                log.warning(
                    "Transcription backlog full (%d); dropped oldest %.2fs segment from %s",
                    MAX_PENDING_SEGMENTS, len(stale) / 16000.0, dropped,
                )

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                speaker, audio_data = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                assert self.backend is not None
                assert self.config is not None

                lang = self.config.language
                text = self.backend.transcribe(audio_data, language=None if lang == "auto" else lang)
                if not text:
                    log.info("Segment from %s produced no text", speaker)
                    continue
                if is_filler(text):
                    log.info("Dropped filler transcript from %s: %r", speaker, text)
                    continue

                log.info("[%s] %r", speaker, text)
                if self.transcript is not None:
                    self.transcript.append(text, speaker=speaker)
            except Exception as exc:
                log.exception("Processing failed")
                self._notify("Transcription failed", str(exc))
            finally:
                # Caught up on the backlog: a good moment to hand back cached GPU
                # memory, since the small rebuild cost lands on an utterance that
                # nothing is waiting behind. Without this the cache keeps every
                # shape a long meeting ever produced.
                try:
                    if self._queue.empty() and self.backend is not None:
                        self.backend.release_cached_memory()
                finally:
                    # Must run for every item, or End Meeting's queue.join()
                    # would wait forever.
                    self._queue.task_done()

    def log_memory_report(self) -> None:
        """Log a memory snapshot on demand, whether or not the monitor is on."""
        from .memory_debug import sample

        if self.memory_monitor is not None:
            snapshot = self.memory_monitor.log_once()
        else:
            snapshot = sample(self)
            log.info("MEM (on demand) %s", snapshot.format())
        self._notify("Memory", f"{snapshot.footprint_mb:.0f}MB — details in the log")

    def open_logs(self) -> None:
        log_file = default_log_file()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        subprocess.call(["open", str(log_file.parent)])

    def open_transcript_folder(self) -> None:
        """Open the folder that holds all meeting transcripts."""
        transcript_dir = self._transcript_dir()
        transcript_dir.mkdir(parents=True, exist_ok=True)
        subprocess.call(["open", str(transcript_dir)])

    def _transcript_dir(self) -> Path:
        if self.config is not None and self.config.transcript.output_dir:
            return Path(self.config.transcript.output_dir)
        return default_transcript_dir()

    def open_settings(self) -> None:
        """Open the config file for editing.

        A Tkinter settings window crashes when run under rumps' NSApplication
        (Tk and rumps fight over the main run loop → unrecognized-selector abort),
        so instead we open config.toml in the default editor. The user edits it,
        saves, then picks "Reload Config" from the menu to apply changes.
        """
        from .config import ensure_config

        path = ensure_config(self.config_path)
        if self.tray is not None:
            self.tray.notify("s2t", "Edit config.toml, then choose Reload Config.")
        subprocess.call(["open", "-t", str(path)])

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        log.info("Shutting down")
        self._stop_event.set()
        if self.memory_monitor is not None:
            self.memory_monitor.stop()
        self._cancel_idle_unload()
        if self.hotkey is not None:
            self.hotkey.unregister()
        if self.recorder is not None and self._meeting_active:
            self.recorder.stop()
        if self.transcript is not None:
            self.transcript.close_session()

    def _install_signal_handlers(self) -> None:
        def _handle(signum, _frame) -> None:
            log.info("Received signal %s", signum)
            self.shutdown()

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)

    def _notify(self, title: str, message: str) -> None:
        if self.tray is not None:
            self.tray.notify(title, message)
        else:
            log.info("%s: %s", title, message)

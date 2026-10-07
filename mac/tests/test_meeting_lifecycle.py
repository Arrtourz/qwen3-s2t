from __future__ import annotations

import queue
import threading
import time
import types

import numpy as np

from s2t.core.config import MeetingConfig, MemoryConfig
from s2t.core.controller import SpeechToTextController
from s2t.core.echo import EchoFilter


class FakeBackend:
    def __init__(self, delay: float = 0.0):
        self.loaded = True
        self.delay = delay
        self.unloads = 0
        self.loads = 0
        self._lock = threading.RLock()

    @property
    def is_loaded(self):
        return self.loaded

    def load_model(self):
        with self._lock:
            if not self.loaded:
                self.loads += 1
                self.loaded = True

    def transcribe(self, audio, language=None):
        with self._lock:
            if not self.loaded:
                self.load_model()
            time.sleep(self.delay)
            return f"utterance {len(audio)}"

    def release_cached_memory(self, min_slack_bytes=0):
        return 0

    def unload(self):
        with self._lock:
            self.loaded = False
            self.unloads += 1


class FakeTranscript:
    def __init__(self):
        self.open = False
        self.lines: list[str] = []
        self.lost: list[str] = []

    def open_session(self):
        self.open = True

    def append(self, text, speaker=None):
        (self.lines if self.open else self.lost).append(text)

    def close_session(self):
        self.open = False


class FakeRecorder:
    """stop() flushes one trailing utterance, like a real segmenter."""

    def __init__(self):
        self.on_segment = None

    def start(self, on_segment):
        self.on_segment = on_segment
        return True, ["me"]

    def stop(self):
        self.on_segment("me", np.zeros(16000 * 2, dtype=np.float32))


def _controller(backend, idle_minutes=10.0):
    c = SpeechToTextController.__new__(SpeechToTextController)
    c.config = types.SimpleNamespace(
        language=None,
        transcript=types.SimpleNamespace(enabled=True),
        memory=MemoryConfig(idle_unload_minutes=idle_minutes),
        meeting=MeetingConfig(),
    )
    c.backend = backend
    c.recorder = FakeRecorder()
    c.transcript = FakeTranscript()
    c.tray = None
    c.memory_monitor = None
    c._meeting_lock = threading.Lock()
    c._meeting_active = False
    c._model_ready = True
    c._queue = queue.Queue(maxsize=32)
    c._stop_event = threading.Event()
    c._toggle_requested = threading.Event()
    c._idle_timer = None
    c._finisher = None
    c._echo = EchoFilter()
    # VAD is out of scope here: queue every segment.
    c._on_segment = lambda speaker, audio: c._enqueue(speaker, audio)
    c._notify = lambda *a: None
    threading.Thread(target=c._worker_loop, daemon=True).start()
    return c


def _shutdown(c):
    c._stop_event.set()
    c._cancel_idle_unload()


def test_final_utterance_reaches_the_transcript(monkeypatch):
    c = _controller(FakeBackend(delay=0.2))  # slow enough that the old code lost it
    c.start_meeting()
    c.end_meeting()
    c._finisher.join(timeout=5)
    assert c.transcript.lines == ["utterance 32000"]
    assert c.transcript.lost == []
    assert c.transcript.open is False
    _shutdown(c)


def test_idle_unload_fires_after_timeout(monkeypatch):
    backend = FakeBackend()
    c = _controller(backend, idle_minutes=0.5 / 60)  # 0.5 s
    c.start_meeting()
    c.end_meeting()
    c._finisher.join(timeout=5)
    time.sleep(1.0)
    assert backend.unloads == 1 and backend.loaded is False
    _shutdown(c)


def test_start_meeting_cancels_pending_unload_and_reloads(monkeypatch):
    backend = FakeBackend()
    c = _controller(backend, idle_minutes=0.5 / 60)
    c.start_meeting(); c.end_meeting(); c._finisher.join(timeout=5)
    time.sleep(1.0)  # unloaded now
    c.start_meeting()
    time.sleep(0.2)
    assert backend.loaded is True and backend.loads == 1
    time.sleep(1.0)  # no stale timer may unload mid-meeting
    assert backend.loaded is True
    c.end_meeting(); c._finisher.join(timeout=5)
    _shutdown(c)


def test_zero_minutes_never_unloads(monkeypatch):
    backend = FakeBackend()
    c = _controller(backend, idle_minutes=0)
    c.start_meeting(); c.end_meeting(); c._finisher.join(timeout=5)
    assert c._idle_timer is None and backend.unloads == 0
    _shutdown(c)


def test_evicted_segments_do_not_block_join():
    c = SpeechToTextController.__new__(SpeechToTextController)
    c._queue = queue.Queue(maxsize=2)
    for i in range(5):
        c._enqueue("me", np.zeros(10, dtype=np.float32))
    for _ in range(2):
        c._queue.get_nowait(); c._queue.task_done()
    done = threading.Event()
    threading.Thread(target=lambda: (c._queue.join(), done.set()), daemon=True).start()
    assert done.wait(2), "queue.join() hung: evicted items were never marked done"


def test_meeting_makes_no_sound(monkeypatch):
    # No tone on start or end (user preference). Intercept the only audio-out
    # path, so any future beep is caught, not just one named beep().
    import sounddevice
    played = []
    monkeypatch.setattr(sounddevice, "play", lambda *a, **k: played.append(a))
    c = _controller(FakeBackend())
    notes = []
    c._notify = lambda *a: notes.append(a)
    c.start_meeting()
    assert notes == []  # start: no banner either
    c.end_meeting(); c._finisher.join(timeout=5)
    time.sleep(0.3)
    assert played == []
    _shutdown(c)


def test_successful_launch_is_silent():
    c = SpeechToTextController.__new__(SpeechToTextController)
    notes = []
    c.tray = types.SimpleNamespace(set_loading=lambda _: None, notify=lambda *a: notes.append(a), set_error=lambda: None)
    c._register_hotkey_main_thread = lambda: None
    c._init_status = "ok"
    c._apply_init_status()
    assert notes == []

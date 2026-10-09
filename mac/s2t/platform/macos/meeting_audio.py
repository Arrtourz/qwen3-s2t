from __future__ import annotations

import logging
import os
import threading
import time
import wave
from pathlib import Path
from typing import Callable

import numpy as np

from ...core.config import MeetingConfig, RecordingConfig
from ...core.segmenter import SilenceSegmenter


log = logging.getLogger(__name__)

# Debug only: with S2T_RECORD_RAW=1 each stream's raw 16 kHz audio is written
# straight to disk (no buffering in memory), for offline echo-cancellation tests.
def _raw_recorder(label: str, recording) -> "_RawWav | None":
    if os.environ.get("S2T_RECORD_RAW", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    from ...core.config import app_data_dir
    d = app_data_dir() / "raw-audio"; d.mkdir(parents=True, exist_ok=True)
    safe = "mic" if "Me" in label else "system"
    return _RawWav(d / f"{time.strftime('%Y%m%d-%H%M%S')}_{safe}.wav", recording.sample_rate)


class _RawWav:
    def __init__(self, path: Path, sample_rate: int) -> None:
        self.path = path
        self._w = wave.open(str(path), "wb")
        self._w.setnchannels(1); self._w.setsampwidth(2); self._w.setframerate(sample_rate)
        self._lock = threading.Lock()
        self.first_sample_monotonic: float | None = None
        log.info("Recording raw audio to %s", path)

    def write(self, block: np.ndarray) -> None:
        with self._lock:
            if self._w is None:
                return
            if self.first_sample_monotonic is None:
                self.first_sample_monotonic = time.monotonic()
                log.info("Raw audio %s first sample at monotonic %.3f", self.path.name, self.first_sample_monotonic)
            self._w.writeframes((np.clip(block, -1.0, 1.0) * 32767).astype(np.int16).tobytes())

    def close(self) -> None:
        with self._lock:
            if self._w is not None:
                self._w.close(); self._w = None


# A completed utterance: (speaker_label, audio_16k_float32)
SegmentCallback = Callable[[str, np.ndarray], None]

# Name fragments that identify a Bluetooth headset. When such a device is the
# OUTPUT, using its microphone as INPUT puts it in HFP mode, which loops the
# played audio (Zoom / video) back into the mic — polluting the "Me" stream.
_BLUETOOTH_HINTS = ("airpods", "buds", "beats", "headphone", "bluetooth", "wh-", "wf-", "qc", "sony")


def _looks_bluetooth(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in _BLUETOOTH_HINTS)


def resolve_mic_device(configured: str) -> str | int | None:
    """Pick the mic device for the "Me" stream.

    If the user pinned a device in config, honor it. Otherwise auto-select:
    when the current OUTPUT is a Bluetooth headset (AirPods), avoid its own mic
    (HFP loopback) and fall back to the built-in Mac microphone. This keeps the
    "Me" stream free of the other party's audio without any manual setup.
    """
    if configured:
        return configured

    try:
        import sounddevice as sd

        out = sd.query_devices(kind="output")
        if _looks_bluetooth(out.get("name", "")):
            builtin = next(
                (
                    i
                    for i, d in enumerate(sd.query_devices())
                    if d.get("max_input_channels", 0) > 0
                    and "macbook" in d["name"].lower()
                    and "microphone" in d["name"].lower()
                ),
                None,
            )
            if builtin is not None:
                log.info(
                    "Output is Bluetooth (%s); using built-in mic for the Me stream to avoid HFP loopback",
                    out.get("name", ""),
                )
                return builtin
    except Exception:
        log.debug("Mic auto-resolve failed; using default input", exc_info=True)

    return None  # system default input


class _StreamWorker:
    """Owns one sounddevice input stream + its silence segmenter."""

    def __init__(
        self,
        *,
        device: str | int | None,
        label: str,
        recording: RecordingConfig,
        meeting: MeetingConfig,
        on_segment: SegmentCallback,
        echo_canceller=None,
        is_reference: bool = False,
    ) -> None:
        self.device = device
        # With a canceller, the mic stream is cleaned by it; a system stream
        # (e.g. BlackHole) instead feeds it as the reference.
        self._aec = echo_canceller
        self._is_reference = is_reference
        self.label = label
        self.recording = recording
        self.on_segment = on_segment
        self._stream = None
        self._resampler_ratio = 1.0
        self._segmenter = SilenceSegmenter(
            sample_rate=recording.sample_rate,
            silence_hold_ms=meeting.silence_hold_ms,
            min_segment_ms=meeting.min_segment_ms,
            max_segment_seconds=meeting.max_segment_seconds,
        )
        self._blocksize = max(1, int(recording.sample_rate * recording.block_duration_ms / 1000))
        self._lock = threading.Lock()
        self._raw = _raw_recorder(label, recording)

    def start(self) -> bool:
        import sounddevice as sd

        try:
            self._stream = sd.InputStream(
                device=self.device,
                samplerate=self.recording.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self._blocksize,
                callback=self._callback,
            )
            self._stream.start()
            log.info("Meeting stream started: device=%r label=%s", self.device, self.label)
            return True
        except Exception as exc:
            log.warning("Could not start stream for device=%r (%s); skipping", self.device, exc)
            self._stream = None
            return False

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                finally:
                    self._stream.close()
                    self._stream = None
        if self._raw is not None:
            self._raw.close()
        # Flush any trailing speech as a final segment.
        tail = self._segmenter.flush()
        if tail is not None and tail.size:
            self.on_segment(self.label, tail)

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("Meeting stream status (%s): %s", self.label, status)
        block = indata.copy().reshape(-1)
        if self._raw is not None:
            self._raw.write(block)  # raw = before echo cancellation
        if self._aec is not None:
            if self._is_reference:
                self._aec.feed_reference(block)
            else:
                block = self._aec.process_mic(block)
        for segment in self._segmenter.push(block):
            self.on_segment(self.label, segment)


class _TapWorker:
    """Owns a Core Audio system tap + segmenter, resampling to 16k."""

    def __init__(self, *, label: str, recording: RecordingConfig, meeting: MeetingConfig, on_segment: SegmentCallback, echo_canceller=None) -> None:
        from .system_tap import SystemAudioTap

        self._aec = echo_canceller

        self.label = label
        self.target_sr = recording.sample_rate
        self.on_segment = on_segment
        self._tap = SystemAudioTap()
        self._raw = _raw_recorder(label, recording)
        self._segmenter = SilenceSegmenter(
            sample_rate=recording.sample_rate,
            silence_hold_ms=meeting.silence_hold_ms,
            min_segment_ms=meeting.min_segment_ms,
            max_segment_seconds=meeting.max_segment_seconds,
        )

    def prepare(self) -> bool:
        """Create tap device + refresh PortAudio (restarts PortAudio ONCE)."""
        return self._tap.prepare()

    def open_stream(self) -> bool:
        """Open the tap stream (no PortAudio restart)."""
        return self._tap.open_stream(self._on_block)

    def start(self) -> bool:
        return self.prepare() and self.open_stream()

    def stop(self) -> None:
        self._tap.stop()
        if self._raw is not None:
            self._raw.close()
        tail = self._segmenter.flush()
        if tail is not None and tail.size:
            self.on_segment(self.label, tail)

    def _on_block(self, mono: np.ndarray, sample_rate: int) -> None:
        block = _resample_mono(mono, sample_rate, self.target_sr)
        if self._raw is not None:
            self._raw.write(block)
        if self._aec is not None:
            self._aec.feed_reference(block)
        for segment in self._segmenter.push(block):
            self.on_segment(self.label, segment)


class MeetingRecorder:
    """Records mic + system audio simultaneously and emits labeled utterances."""

    def __init__(self, recording: RecordingConfig, meeting: MeetingConfig) -> None:
        self.recording = recording
        self.meeting = meeting
        self._workers: list = []
        self._active = False
        self._lock = threading.Lock()

    def start(self, on_segment: SegmentCallback) -> tuple[bool, list[str]]:
        """Start mic + (tap|device) streams. Returns (any_started, active_labels)."""
        with self._lock:
            if self._active:
                return True, [w.label for w in self._workers]

            self._workers = []
            active_labels: list[str] = []

            # CRITICAL ORDERING. The system tap creates a Core Audio aggregate
            # device and must restart PortAudio (sd._terminate/_initialize) once
            # so the device becomes visible. That restart invalidates any already
            # open sounddevice stream. So the sequence is:
            #   1. tap.prepare()      — create device + the single PortAudio restart
            #   2. open the mic stream — after the restart, stays valid
            #   3. tap.open_stream()   — no restart; coexists with the mic stream
            src = self.meeting.system_source
            # One canceller per meeting, shared by the mic (cleaned) and the
            # system stream (reference). Only useful when there is a reference.
            aec = None
            if self.meeting.echo_cancellation and src in ("tap", "device"):
                from ...core.aec import make_echo_canceller

                aec = make_echo_canceller(self.recording.sample_rate)
            tap: _TapWorker | None = None
            if src == "tap":
                candidate = _TapWorker(
                    label=self.meeting.system_label,
                    recording=self.recording,
                    meeting=self.meeting,
                    on_segment=on_segment,
                    echo_canceller=aec,
                )
                if candidate.prepare():
                    tap = candidate
                else:
                    log.warning("System tap failed to prepare; continuing mic-only")

            # Mic (or a named system device) — opened AFTER the tap's PortAudio restart.
            # Auto-avoid the AirPods mic (HFP loopback) when it's also the output.
            mic_device = resolve_mic_device(self.meeting.mic_device)
            mic = _StreamWorker(
                device=mic_device,
                label=self.meeting.mic_label,
                recording=self.recording,
                meeting=self.meeting,
                on_segment=on_segment,
                echo_canceller=aec,
            )
            if mic.start():
                self._workers.append(mic)
                active_labels.append(self.meeting.mic_label)

            if src == "device" and self.meeting.system_device:
                sysw = _StreamWorker(
                    device=self.meeting.system_device,
                    label=self.meeting.system_label,
                    recording=self.recording,
                    meeting=self.meeting,
                    on_segment=on_segment,
                    echo_canceller=aec,
                    is_reference=True,
                )
                if sysw.start():
                    self._workers.append(sysw)
                    active_labels.append(self.meeting.system_label)

            # Now open the tap stream (no further PortAudio restart).
            if tap is not None and tap.open_stream():
                self._workers.append(tap)
                active_labels.append(self.meeting.system_label)
            elif tap is not None:
                log.warning("System tap stream failed to open; continuing without it")
                tap.stop()

            self._active = bool(self._workers)
            return self._active, active_labels

    def stop(self) -> None:
        with self._lock:
            for worker in self._workers:
                worker.stop()
            self._workers = []
            self._active = False

    def is_active(self) -> bool:
        with self._lock:
            return self._active


def _resample_mono(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Lightweight linear resample of mono float32 audio."""
    if src_sr == dst_sr or audio.size == 0:
        return audio.astype(np.float32, copy=False)
    duration = audio.size / src_sr
    dst_n = int(round(duration * dst_sr))
    if dst_n <= 0:
        return np.zeros(0, dtype=np.float32)
    src_idx = np.linspace(0, audio.size - 1, dst_n)
    return np.interp(src_idx, np.arange(audio.size), audio).astype(np.float32)


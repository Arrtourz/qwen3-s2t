from __future__ import annotations

import collections
import logging
import threading

import numpy as np

from ...core.config import RecordingConfig


log = logging.getLogger(__name__)


class SoundDeviceAudioCapture:
    def __init__(self, config: RecordingConfig) -> None:
        self.config = config
        self._stream = None
        self._lock = threading.Lock()
        self._is_recording = False
        self._chunks: collections.deque[np.ndarray] = collections.deque()
        self._blocksize = max(1, int(self.config.sample_rate * self.config.block_duration_ms / 1000))
        max_blocks = max(
            1,
            int(self.config.continuous_window_seconds * 1000 / self.config.block_duration_ms),
        )
        self._windowed_maxlen = max_blocks

    def start_recording(self, windowed: bool) -> bool:
        with self._lock:
            if self._stream is None:
                try:
                    import sounddevice as sd

                    self._stream = sd.InputStream(
                        samplerate=self.config.sample_rate,
                        channels=self.config.channels,
                        dtype="float32",
                        blocksize=self._blocksize,
                        callback=self._audio_callback,
                    )
                    self._stream.start()
                except Exception as exc:
                    log.exception("Failed to start microphone stream")
                    self._stream = None
                    return False

            maxlen = self._windowed_maxlen if windowed else None
            self._chunks = collections.deque(maxlen=maxlen)
            self._is_recording = True
            return True

    def stop_recording(self) -> np.ndarray | None:
        with self._lock:
            self._is_recording = False
            chunks = list(self._chunks)
            self._chunks.clear()
            self._stop_stream()

        return _flatten_chunks(chunks, self.config.sample_rate)

    def snapshot_recording(self) -> np.ndarray | None:
        with self._lock:
            chunks = list(self._chunks)
            self._chunks.clear()
        return _flatten_chunks(chunks, self.config.sample_rate)

    def is_recording(self) -> bool:
        with self._lock:
            return self._is_recording

    def close(self) -> None:
        with self._lock:
            self._is_recording = False
            self._chunks.clear()
            self._stop_stream()

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.warning("Audio callback status: %s", status)
        with self._lock:
            if not self._is_recording:
                return
            self._chunks.append(indata.copy().reshape(-1))

    def _stop_stream(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
        finally:
            self._stream.close()
            self._stream = None


def _flatten_chunks(chunks: list[np.ndarray], sample_rate: int) -> np.ndarray | None:
    if not chunks:
        return None
    audio = np.concatenate(chunks).astype(np.float32, copy=False)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    log.info("Captured %.2fs of audio (peak=%.4f)", len(audio) / sample_rate, peak)
    return audio

from __future__ import annotations

import logging
import threading

import numpy as np


log = logging.getLogger(__name__)

# WebRTC's audio processing module only accepts 10 ms frames.
_FRAME_MS = 10


class EchoCanceller:
    """Removes speaker playback from the mic using WebRTC AEC3 (via livekit).

    With laptop speakers the mic re-records the other party, so each remote
    sentence was transcribed twice. The system-audio stream is exactly what the
    speakers play, which makes it the reference AEC needs: feed it through
    feed_reference(), pass the mic through process_mic().

    Chosen by A/B on two real speaker-playback recordings: AEC3 removed 4 of 5
    echoed lines both times; Speex (pyaec) removed none. Costs ~16-18 MB and
    ~0.05 ms per 10 ms frame. AEC3's weak spot is both sides talking at once.

    The two streams arrive on different audio threads; one lock serialises them.
    Any failure disables the canceller and passes the mic through unchanged, so
    a problem here can never stop recording.
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        from livekit import rtc  # lazy: only paid for when echo cancellation is on

        self._rtc = rtc
        self.sample_rate = sample_rate
        self._frame = sample_rate * _FRAME_MS // 1000
        self._apm = rtc.AudioProcessingModule(echo_cancellation=True, high_pass_filter=True)
        self._lock = threading.Lock()
        self._ref_rest = np.zeros(0, dtype=np.int16)
        self._mic_rest = np.zeros(0, dtype=np.int16)
        self._failed = False

    @property
    def active(self) -> bool:
        return not self._failed

    def feed_reference(self, block: np.ndarray) -> None:
        """System audio (what the speakers play), float32 mono at sample_rate."""
        if self._failed:
            return
        with self._lock:
            try:
                buf = np.concatenate([self._ref_rest, _to_int16(block)])
                n = (buf.size // self._frame) * self._frame
                for i in range(0, n, self._frame):
                    self._apm.process_reverse_stream(self._make_frame(buf[i:i + self._frame]))
                self._ref_rest = buf[n:]
            except Exception:
                self._fail("reference")

    def process_mic(self, block: np.ndarray) -> np.ndarray:
        """Mic audio in, echo-cancelled audio out (float32).

        Output is whole 10 ms frames, so a call may return up to one frame less
        or more than it was given; the remainder carries over to the next call.
        """
        if self._failed:
            return block
        with self._lock:
            try:
                buf = np.concatenate([self._mic_rest, _to_int16(block)])
                n = (buf.size // self._frame) * self._frame
                out = np.empty(n, dtype=np.int16)
                for i in range(0, n, self._frame):
                    frame = self._make_frame(buf[i:i + self._frame])
                    self._apm.process_stream(frame)
                    out[i:i + self._frame] = np.frombuffer(frame.data, dtype=np.int16)
                self._mic_rest = buf[n:]
                return out.astype(np.float32) / 32767.0
            except Exception:
                self._fail("mic")
                return block

    def _make_frame(self, samples: np.ndarray):
        frame = self._rtc.AudioFrame.create(self.sample_rate, 1, self._frame)
        np.frombuffer(frame.data, dtype=np.int16)[:] = samples
        return frame

    def _fail(self, where: str) -> None:
        self._failed = True
        log.exception("Echo cancellation failed on the %s stream; continuing without it", where)


def make_echo_canceller(sample_rate: int) -> EchoCanceller | None:
    """Build the canceller, or return None (with a log line) if unavailable."""
    try:
        aec = EchoCanceller(sample_rate)
        log.info("Echo cancellation on (WebRTC AEC3)")
        return aec
    except Exception:
        log.warning("Echo cancellation unavailable; recording without it", exc_info=True)
        return None


def _to_int16(block: np.ndarray) -> np.ndarray:
    return (np.clip(np.asarray(block, dtype=np.float32).reshape(-1), -1.0, 1.0) * 32767).astype(np.int16)

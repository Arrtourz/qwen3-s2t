from __future__ import annotations

import logging

import numpy as np


log = logging.getLogger(__name__)


class SilenceSegmenter:
    """Splits a continuous audio stream into utterances using silence detection.

    Audio blocks are fed in via :meth:`push`. When a run of silence longer than
    ``silence_hold_ms`` follows some speech, the buffered speech is emitted as a
    finished segment. A segment is also force-flushed once it grows past
    ``max_segment_seconds`` so a non-stop speaker never causes an unbounded buffer.

    Latency is not a concern for this use case (transcripts are a reference), so
    the silence threshold is intentionally generous to avoid chopping sentences.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        *,
        silence_rms: float = 0.008,
        silence_hold_ms: int = 800,
        min_segment_ms: int = 400,
        max_segment_seconds: float = 20.0,
        preroll_ms: int = 300,
        adaptive: bool = True,
        speech_factor: float = 2.5,
        target_peak: float = 0.35,
    ) -> None:
        self.sample_rate = sample_rate
        self.silence_rms = silence_rms
        self.silence_hold_samples = int(sample_rate * silence_hold_ms / 1000)
        self.min_segment_samples = int(sample_rate * min_segment_ms / 1000)
        self.max_segment_samples = int(sample_rate * max_segment_seconds)
        # While no speech has been seen yet, only this much trailing audio is
        # retained — enough to keep an utterance's onset, but bounded, so a
        # silent stream cannot grow the buffer without limit.
        self.preroll_samples = int(sample_rate * preroll_ms / 1000)

        # Adaptive mode tracks the ambient noise floor and treats a block as
        # speech when it rises clearly above it. This makes capture work across
        # very different mic levels (low-output AirPods vs a loud built-in mic)
        # without per-device tuning. `silence_rms` becomes an absolute floor.
        self.adaptive = adaptive
        self.speech_factor = speech_factor
        self.target_peak = target_peak
        # Start the noise floor very low and learn it from the first quiet blocks,
        # so a low-level mic (AirPods) isn't shut out by a too-high initial guess.
        self._noise_floor = 0.0005
        self._floor_initialized = False

        self._buffer: list[np.ndarray] = []
        self._buffered_samples = 0
        self._trailing_silence = 0
        self._has_speech = False

    def push(self, block: np.ndarray) -> list[np.ndarray]:
        """Feed one audio block; return any completed segments (usually empty)."""
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        if block.size == 0:
            return []

        segments: list[np.ndarray] = []
        rms = float(np.sqrt(np.mean(block**2)))

        if self.adaptive:
            # Start from a very low floor and learn it only from quiet blocks, so
            # a low-level mic (AirPods) is never shut out and a loud utterance
            # can't drag the floor up into the speech range. A small absolute
            # threshold keeps pure digital silence from counting as speech.
            threshold = max(0.0015, self._noise_floor * self.speech_factor)
            is_silent = rms < threshold
            if is_silent:
                self._noise_floor = 0.9 * self._noise_floor + 0.1 * rms
        else:
            is_silent = rms < self.silence_rms

        self._buffer.append(block)
        self._buffered_samples += block.size

        if is_silent:
            self._trailing_silence += block.size
        else:
            self._trailing_silence = 0
            self._has_speech = True

        # Nothing has been spoken yet, so everything buffered so far is silence.
        # Discard all but a short pre-roll: without this the buffer grows for as
        # long as the stream stays quiet (a muted system tap emits pure digital
        # silence indefinitely), and the eventual first utterance would drag all
        # of that accumulated silence into one oversized segment.
        if not self._has_speech:
            self._trim_to_preroll()

        # Emit when a speech run is followed by enough trailing silence.
        if (
            self._has_speech
            and self._trailing_silence >= self.silence_hold_samples
            and self._buffered_samples - self._trailing_silence >= self.min_segment_samples
        ):
            seg = self._drain()
            if seg is not None:
                segments.append(seg)
        # Force-flush an over-long segment (someone talking non-stop).
        elif self._has_speech and self._buffered_samples >= self.max_segment_samples:
            seg = self._drain()
            if seg is not None:
                segments.append(seg)

        return segments

    def flush(self) -> np.ndarray | None:
        """Emit whatever speech remains buffered (e.g. when the meeting ends)."""
        if not self._has_speech:
            self._reset()
            return None
        return self._drain()

    def _trim_to_preroll(self) -> None:
        """Drop leading blocks so at most ``preroll_samples`` stay buffered."""
        while len(self._buffer) > 1 and self._buffered_samples - self._buffer[0].size >= self.preroll_samples:
            self._buffered_samples -= self._buffer.pop(0).size
        self._trailing_silence = min(self._trailing_silence, self._buffered_samples)

    def _drain(self) -> np.ndarray | None:
        if not self._buffer:
            self._reset()
            return None
        audio = np.concatenate(self._buffer)
        self._reset()
        if audio.size < self.min_segment_samples:
            return None
        return self._normalize(audio)

    def _normalize(self, audio: np.ndarray) -> np.ndarray:
        """Auto-gain: bring a quiet utterance (e.g. AirPods mic) up to a usable
        level so the ASR model gets a consistent input regardless of mic."""
        if not self.adaptive:
            return audio
        peak = float(np.max(np.abs(audio)))
        if peak <= 1e-4:
            return audio
        gain = self.target_peak / peak
        # Only ever amplify, and cap the gain so we don't blow up pure noise.
        gain = min(max(gain, 1.0), 20.0)
        return np.clip(audio * gain, -1.0, 1.0).astype(np.float32)

    def _reset(self) -> None:
        self._buffer = []
        self._buffered_samples = 0
        self._trailing_silence = 0
        self._has_speech = False

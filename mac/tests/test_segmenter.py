from __future__ import annotations

import numpy as np

from s2t.core.segmenter import SilenceSegmenter


SR = 16000


def _speech(seconds: float, amp: float = 0.3) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 200 * t) * amp).astype(np.float32)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.float32)


def _feed(seg: SilenceSegmenter, audio: np.ndarray, block_ms: int = 100):
    out = []
    step = int(SR * block_ms / 1000)
    for i in range(0, len(audio), step):
        out.extend(seg.push(audio[i:i + step]))
    return out


def test_emits_segment_after_silence():
    seg = SilenceSegmenter(SR, silence_hold_ms=500, min_segment_ms=300)
    audio = np.concatenate([_speech(1.0), _silence(0.8)])
    segments = _feed(seg, audio)
    assert len(segments) == 1
    assert segments[0].size >= int(SR * 0.3)


def test_no_segment_without_silence():
    seg = SilenceSegmenter(SR, silence_hold_ms=500)
    segments = _feed(seg, _speech(1.0))
    assert segments == []
    # but flush yields the trailing speech
    tail = seg.flush()
    assert tail is not None and tail.size > 0


def test_force_flush_on_max_length():
    seg = SilenceSegmenter(SR, silence_hold_ms=500, max_segment_seconds=2.0)
    segments = _feed(seg, _speech(3.0))
    assert len(segments) >= 1


def test_pure_silence_emits_nothing():
    seg = SilenceSegmenter(SR, silence_hold_ms=300)
    segments = _feed(seg, _silence(2.0))
    assert segments == []
    assert seg.flush() is None


def test_two_utterances_split():
    seg = SilenceSegmenter(SR, silence_hold_ms=500, min_segment_ms=300)
    audio = np.concatenate([_speech(0.8), _silence(0.8), _speech(0.8), _silence(0.8)])
    segments = _feed(seg, audio)
    assert len(segments) == 2


def _quiet_speech(seconds: float, amp: float) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    return ((np.sin(2 * np.pi * 180 * t) + 0.5 * np.sin(2 * np.pi * 360 * t)) * amp).astype(np.float32)


def test_adaptive_captures_low_level_airpods_audio():
    # AirPods-level speech (peak ~0.012) that a fixed 0.008 RMS threshold drops.
    seg = SilenceSegmenter(SR, silence_hold_ms=500, adaptive=True)
    audio = np.concatenate([_silence(0.6), _quiet_speech(1.5, 0.012), _silence(1.0)])
    segments = [s for s in _feed(seg, audio) if s is not None]
    tail = seg.flush()
    if tail is not None:
        segments.append(tail)
    assert len(segments) == 1


def test_adaptive_applies_auto_gain():
    seg = SilenceSegmenter(SR, silence_hold_ms=500, adaptive=True, target_peak=0.35)
    audio = np.concatenate([_silence(0.6), _quiet_speech(1.5, 0.012), _silence(1.0)])
    segments = [s for s in _feed(seg, audio) if s is not None]
    tail = seg.flush()
    if tail is not None:
        segments.append(tail)
    assert segments
    peak = float(np.max(np.abs(segments[0])))
    assert 0.2 < peak <= 1.0  # amplified from ~0.012 toward target

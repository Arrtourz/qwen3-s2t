from __future__ import annotations

import numpy as np

from s2t.core.voice import has_voice, is_filler, voice_metrics


SR = 16000


def _speech(seconds: float, amp: float = 0.3) -> np.ndarray:
    """Bursty voice-like signal: syllables separated by short gaps."""
    t = np.arange(int(SR * seconds)) / SR
    tone = (np.sin(2 * np.pi * 180 * t) + 0.5 * np.sin(2 * np.pi * 360 * t)) * amp
    # amplitude-modulate at ~4 Hz to mimic syllable bursts
    env = (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)).astype(np.float32)
    return (tone * env).astype(np.float32)


def _noise(seconds: float, amp: float = 0.3) -> np.ndarray:
    return (np.random.randn(int(SR * seconds)) * amp).astype(np.float32)


def _near_silence(seconds: float) -> np.ndarray:
    return (np.random.randn(int(SR * seconds)) * 0.001).astype(np.float32)


def test_has_voice_accepts_speech():
    assert has_voice(_speech(1.5)) is True


def test_has_voice_rejects_amplified_noise():
    # White noise amplified to full scale must NOT be treated as voice (high ZCR).
    assert has_voice(_noise(1.5, 0.35)) is False


def test_has_voice_rejects_near_silence():
    assert has_voice(_near_silence(1.5)) is False


def test_has_voice_rejects_too_short():
    assert has_voice(_speech(0.05)) is False


def test_is_filler_common_fillers():
    for t in ["嗯", "嗯。", " 嗯 ", "you", "Thanks for watching!", "。", "um"]:
        assert is_filler(t) is True


def test_is_filler_rejects_real_text():
    assert is_filler("我们讨论第三季度的路线图") is False
    assert is_filler("Let's start the meeting") is False


def test_quiet_voice_below_rms_floor_is_rejected():
    # A spectrally speech-like but quiet segment (office chatter / hallucination
    # level, RMS ~0.02) must be dropped by the default proximity gate.
    t = np.arange(SR) / SR
    quiet = ((np.sin(2 * np.pi * 180 * t) + 0.4 * np.sin(2 * np.pi * 360 * t)) * 0.03).astype(np.float32)
    assert has_voice(quiet) is False


def test_loud_direct_voice_passes():
    t = np.arange(SR) / SR
    loud = ((np.sin(2 * np.pi * 180 * t) + 0.4 * np.sin(2 * np.pi * 360 * t)) * 0.12).astype(np.float32)
    assert has_voice(loud) is True


def test_voice_metrics_returns_values():
    t = np.arange(SR) / SR
    a = (np.sin(2 * np.pi * 180 * t) * 0.1).astype(np.float32)
    rms, zcr, ratio, ok = voice_metrics(a)
    assert rms > 0 and 0 <= zcr <= 1 and 0 <= ratio <= 1 and isinstance(ok, bool)


def test_is_filler_single_word_hallucinations():
    for t in ["The.", "Hmm.", "Okay.", "So.", "Yeah.", "One.", "The", "OKAY", "嗯。", "好。"]:
        assert is_filler(t) is True, f"{t!r} should be filler"


def test_is_filler_keeps_real_sentences():
    for t in [
        "Let's start the meeting",
        "The quick brown fox",
        "我们讨论路线图",
        "Good morning everyone.",
        "The plan is ready.",
        "好的我明白了",
    ]:
        assert is_filler(t) is False, f"{t!r} should be kept"

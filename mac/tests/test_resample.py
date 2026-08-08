import numpy as np
from s2t.platform.macos.meeting_audio import _resample_mono


def test_downsample_length():
    audio = np.ones(48000, dtype=np.float32)
    out = _resample_mono(audio, 48000, 16000)
    assert abs(len(out) - 16000) <= 1


def test_same_rate_passthrough():
    audio = np.random.rand(1000).astype(np.float32)
    out = _resample_mono(audio, 16000, 16000)
    assert np.array_equal(out, audio)


def test_empty():
    assert _resample_mono(np.zeros(0, dtype=np.float32), 48000, 16000).size == 0


def test_preserves_signal_shape():
    t = np.linspace(0, 1, 48000, endpoint=False)
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    out = _resample_mono(audio, 48000, 16000)
    assert len(out) == 16000
    assert out.max() > 0.5 and out.min() < -0.5

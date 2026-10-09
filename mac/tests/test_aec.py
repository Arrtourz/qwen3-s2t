from __future__ import annotations

import sys

import numpy as np
import pytest

pytest.importorskip("livekit")

from s2t.core.aec import EchoCanceller, make_echo_canceller

SR = 16000


def _speechlike(seconds: float, seed: int) -> np.ndarray:
    # Amplitude-modulated harmonics with a wandering pitch: enough for AEC3 to adapt on.
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * seconds)) / SR
    f0 = 140 + 40 * np.sin(2 * np.pi * 0.7 * t + rng.uniform(0, 6))
    sig = sum(np.sin(2 * np.pi * k * np.cumsum(f0) / SR) / k for k in range(1, 6))
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t + rng.uniform(0, 6))
    return (0.15 * sig * env).astype(np.float32)


def _db(x):
    return 10 * np.log10(np.mean(np.asarray(x, np.float64) ** 2) + 1e-12)


def _run(aec, mic, ref, block=1600):
    out = []
    for i in range(0, mic.size, block):
        aec.feed_reference(ref[i:i + block])
        out.append(aec.process_mic(mic[i:i + block]))
    return np.concatenate(out)


def test_output_is_whole_frames_and_carries_remainder():
    # Cumulative output must always equal the whole 10 ms frames received so far.
    aec = EchoCanceller(SR)
    total_in = total_out = 0
    for size in (1000, 1000, 1600, 37, 1600, 123):
        total_in += size
        total_out += aec.process_mic(np.zeros(size, np.float32)).size
        assert total_out == (total_in // 160) * 160


def test_removes_speaker_echo():
    far = _speechlike(12, seed=1)
    delay = int(0.06 * SR)
    echo = np.concatenate([np.zeros(delay, np.float32), 0.5 * far[:-delay]])
    out = _run(EchoCanceller(SR), echo, far)
    tail = slice(6 * SR, 12 * SR)  # after adaptation
    assert _db(echo[tail]) - _db(out[tail]) > 15  # dB of echo removed


def test_near_end_alone_is_kept():
    # With nothing playing, the user's own voice must pass essentially intact.
    me = _speechlike(6, seed=2)
    out = _run(EchoCanceller(SR), me, np.zeros_like(me))
    tail = slice(2 * SR, 6 * SR)
    assert abs(_db(out[tail]) - _db(me[tail])) < 3


def test_failure_falls_back_to_passthrough():
    aec = EchoCanceller(SR)
    def boom(_frame):
        raise RuntimeError("apm went away")
    aec._apm.process_stream = boom
    block = np.full(1600, 0.1, np.float32)
    assert np.array_equal(aec.process_mic(block), block)
    assert aec.active is False
    assert np.array_equal(aec.process_mic(block), block)  # stays off, no retry storm


def test_unavailable_library_means_no_canceller(monkeypatch):
    monkeypatch.setitem(sys.modules, "livekit", None)  # import fails
    assert make_echo_canceller(SR) is None


class _FakeAec:
    def __init__(self):
        self.refs, self.mics = 0, 0
    def feed_reference(self, block):
        self.refs += 1
    def process_mic(self, block):
        self.mics += 1
        return block * 0


def test_recorder_wires_mic_and_reference_roles():
    from s2t.core.config import MeetingConfig, RecordingConfig
    from s2t.platform.macos.meeting_audio import _StreamWorker
    aec = _FakeAec()
    args = dict(recording=RecordingConfig(), meeting=MeetingConfig(), on_segment=lambda *a: None, echo_canceller=aec)
    mic = _StreamWorker(device=None, label="mic", **args)
    ref = _StreamWorker(device=None, label="sys", is_reference=True, **args)
    block = np.full((1600, 1), 0.2, np.float32)
    mic._callback(block, 1600, None, None)
    ref._callback(block, 1600, None, None)
    assert (aec.mics, aec.refs) == (1, 1)

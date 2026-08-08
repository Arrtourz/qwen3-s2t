from __future__ import annotations

import numpy as np

from s2t.core.speaker_id import SpeakerVerifier, VoiceProfile


def test_cosine_identical():
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert abs(SpeakerVerifier.cosine(v, v) - 1.0) < 1e-6


def test_cosine_orthogonal():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert abs(SpeakerVerifier.cosine(a, b)) < 1e-6


def test_cosine_zero_vector():
    a = np.zeros(4, dtype=np.float32)
    b = np.ones(4, dtype=np.float32)
    assert SpeakerVerifier.cosine(a, b) == 0.0


def test_profile_save_load_roundtrip(workspace_tmp_path):
    path = workspace_tmp_path / "profile.json"
    p = VoiceProfile(path)
    assert p.enrolled is False
    emb = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    p.save(emb)
    assert p.enrolled is True
    # fresh instance reads from disk
    p2 = VoiceProfile(path)
    assert np.allclose(p2.load(), emb)


def test_profile_clear(workspace_tmp_path):
    path = workspace_tmp_path / "profile.json"
    p = VoiceProfile(path)
    p.save(np.ones(3, dtype=np.float32))
    p.clear()
    assert p.enrolled is False

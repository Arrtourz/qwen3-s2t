from __future__ import annotations

import torch

from s2t.core.backend import _resolve_dtype


def test_cpu_uses_float32():
    assert _resolve_dtype("cpu") is torch.float32


def test_cuda_uses_checkpoint_bfloat16():
    assert _resolve_dtype("cuda:0") is torch.bfloat16


def test_mps_uses_bfloat16_on_macos_14_plus(monkeypatch):
    monkeypatch.setattr(torch.backends.mps, "is_macos_or_newer", lambda *_: True)
    assert _resolve_dtype("mps") is torch.bfloat16


def test_mps_falls_back_to_float16_before_macos_14(monkeypatch):
    # MPS has no bfloat16 kernels on macOS 12/13, which the app still supports.
    monkeypatch.setattr(torch.backends.mps, "is_macos_or_newer", lambda *_: False)
    assert _resolve_dtype("mps") is torch.float16

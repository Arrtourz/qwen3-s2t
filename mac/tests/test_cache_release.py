from __future__ import annotations

import types

import pytest
import torch

from s2t.core.backend import CACHE_SLACK_RELEASE_BYTES, Qwen3ASRBackend
from s2t.core.config import ModelConfig


MB = 1024 * 1024


def _backend(device: str) -> Qwen3ASRBackend:
    backend = Qwen3ASRBackend(config=ModelConfig())
    backend._device = device
    return backend


def _fake_mps(monkeypatch, *, reserved: int, in_use: int):
    """Stand in for torch.mps, recording whether empty_cache() was called."""
    state = {"reserved": reserved, "calls": 0}

    def empty_cache():
        state["calls"] += 1
        state["reserved"] = in_use  # a real flush returns the slack

    fake = types.SimpleNamespace(
        driver_allocated_memory=lambda: state["reserved"],
        current_allocated_memory=lambda: in_use,
        empty_cache=empty_cache,
    )
    monkeypatch.setattr(torch, "mps", fake)
    return state


def test_cpu_device_is_a_noop():
    assert _backend("cpu").release_cached_memory() == 0


def test_releases_when_slack_exceeds_threshold(monkeypatch):
    state = _fake_mps(monkeypatch, reserved=4000 * MB, in_use=1500 * MB)
    freed = _backend("mps").release_cached_memory()
    assert state["calls"] == 1
    assert freed == 2500 * MB


def test_skips_release_when_slack_is_small(monkeypatch):
    state = _fake_mps(monkeypatch, reserved=1600 * MB, in_use=1500 * MB)
    assert _backend("mps").release_cached_memory() == 0
    assert state["calls"] == 0  # cache kept; not worth the rebuild


def test_zero_threshold_always_releases(monkeypatch):
    state = _fake_mps(monkeypatch, reserved=1600 * MB, in_use=1500 * MB)
    _backend("mps").release_cached_memory(min_slack_bytes=0)
    assert state["calls"] == 1


def test_allocator_failure_is_swallowed(monkeypatch):
    def boom():
        raise RuntimeError("MPS allocator unavailable")

    monkeypatch.setattr(torch, "mps", types.SimpleNamespace(
        driver_allocated_memory=boom, current_allocated_memory=boom, empty_cache=boom))
    assert _backend("mps").release_cached_memory() == 0  # must not break the worker


def test_cuda_uses_its_own_api_names(monkeypatch):
    state = {"calls": 0}
    monkeypatch.setattr(torch, "cuda", types.SimpleNamespace(
        memory_reserved=lambda: 4000 * MB,
        memory_allocated=lambda: 1500 * MB,
        empty_cache=lambda: state.__setitem__("calls", state["calls"] + 1)))
    _backend("cuda:0").release_cached_memory()
    assert state["calls"] == 1


def test_default_threshold_is_documented_value():
    assert CACHE_SLACK_RELEASE_BYTES == 512 * MB


def test_reports_zero_when_cache_is_not_reclaimable(monkeypatch):
    # A freshly loaded model shows ~330MB of slack on MPS that empty_cache()
    # cannot hand back; returning 0 there is accurate, not a failure.
    state = {"calls": 0}
    monkeypatch.setattr(torch, "mps", types.SimpleNamespace(
        driver_allocated_memory=lambda: 1900 * MB,
        current_allocated_memory=lambda: 1570 * MB,
        empty_cache=lambda: state.__setitem__("calls", state["calls"] + 1)))
    assert _backend("mps").release_cached_memory(min_slack_bytes=0) == 0
    assert state["calls"] == 1  # it still tried

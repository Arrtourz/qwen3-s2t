from __future__ import annotations

import logging
import queue
import types

import numpy as np

from s2t.core.memory_debug import (
    MemoryMonitor,
    MemorySnapshot,
    enabled_from_env,
    phys_footprint_mb,
    sample,
)


def test_phys_footprint_is_plausible():
    # The point of this helper: RSS misses MPS memory, so footprint must come
    # from task_info(). A live process is always above zero.
    mb = phys_footprint_mb()
    assert mb > 1.0, f"footprint looked wrong: {mb}"


def test_snapshot_cache_is_the_gap_between_reserved_and_in_use():
    snap = MemorySnapshot(footprint_mb=100.0, mps_in_use_mb=1500.0, mps_reserved_mb=4000.0, python_objects=1)
    assert snap.mps_cache_mb == 2500.0


def test_snapshot_cache_unknown_when_mps_absent():
    snap = MemorySnapshot(footprint_mb=100.0, mps_in_use_mb=-1.0, mps_reserved_mb=-1.0, python_objects=1)
    assert snap.mps_cache_mb == -1.0


def test_format_omits_unavailable_fields():
    snap = MemorySnapshot(footprint_mb=650.0, mps_in_use_mb=-1.0, mps_reserved_mb=-1.0, python_objects=42)
    text = snap.format()
    assert "footprint=650MB" in text and "objects=42" in text
    assert "mps_in_use" not in text and "queue=" not in text


def _fake_controller(queue_depth: int, buffered_samples: list[int]):
    q = queue.Queue()
    for _ in range(queue_depth):
        q.put(("me", np.zeros(16, dtype=np.float32)))
    workers = [
        types.SimpleNamespace(_segmenter=types.SimpleNamespace(_buffered_samples=n, sample_rate=16000))
        for n in buffered_samples
    ]
    return types.SimpleNamespace(_queue=q, recorder=types.SimpleNamespace(_workers=workers))


def test_sample_reports_queue_and_buffered_audio():
    # buffered audio is the signal that caught the silence-retention bug
    snap = sample(_fake_controller(3, [16000 * 2, 16000 * 5]))
    assert snap.queue_depth == 3
    assert snap.buffered_audio_seconds == 7.0


def test_sample_without_controller_leaves_those_fields_unknown():
    snap = sample()
    assert snap.queue_depth == -1
    assert snap.buffered_audio_seconds == -1.0


def test_sample_tolerates_a_controller_without_a_recorder():
    snap = sample(types.SimpleNamespace(_queue=queue.Queue(), recorder=None))
    assert snap.buffered_audio_seconds == -1.0


def test_monitor_logs_on_demand(caplog):
    monitor = MemoryMonitor(_fake_controller(1, [16000]), interval_seconds=60.0)
    monitor._baseline = sample()
    with caplog.at_level(logging.INFO, logger="s2t.core.memory_debug"):
        monitor.log_once()
    assert any("MEM " in r.message for r in caplog.records)


def test_monitor_interval_has_a_floor():
    # A 1s monitor would itself distort what it measures (gc.get_objects()).
    assert MemoryMonitor(None, interval_seconds=0.1)._interval == 5.0


def test_env_toggle(monkeypatch):
    for value in ("1", "true", "YES", "on"):
        monkeypatch.setenv("S2T_MEMORY_DEBUG", value)
        assert enabled_from_env() is True
    for value in ("", "0", "false", "off"):
        monkeypatch.setenv("S2T_MEMORY_DEBUG", value)
        assert enabled_from_env() is False

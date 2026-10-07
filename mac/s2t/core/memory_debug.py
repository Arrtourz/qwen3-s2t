from __future__ import annotations

import ctypes
import ctypes.util
import gc
import logging
import os
import threading
from dataclasses import dataclass, field


log = logging.getLogger(__name__)

MB = 1e6

# macOS reports a process's true memory cost as phys_footprint — the number
# Activity Monitor shows. It is NOT resident_size (what ps/getrusage report):
# Metal/MPS buffers live in IOAccelerator memory, which never appears in RSS.
# A 3-hour s2t session measured 246MB RSS against 7701MB phys_footprint, so RSS
# is useless for this app. Read it through task_info() rather than shelling out
# to footprint(1), which costs ~50ms per sample.
_TASK_VM_INFO = 22
_mvs = ctypes.c_uint64  # mach_vm_size_t
_it = ctypes.c_int  # integer_t


class _TaskVMInfo(ctypes.Structure):
    """Prefix of mach/task_info.h's task_vm_info, up to phys_footprint."""

    _fields_ = [
        ("virtual_size", _mvs),
        ("region_count", _it),
        ("page_size", _it),
        ("resident_size", _mvs),
        ("resident_size_peak", _mvs),
        ("device", _mvs),
        ("device_peak", _mvs),
        ("internal", _mvs),
        ("internal_peak", _mvs),
        ("external", _mvs),
        ("external_peak", _mvs),
        ("reusable", _mvs),
        ("reusable_peak", _mvs),
        ("purgeable_volatile_pmap", _mvs),
        ("purgeable_volatile_resident", _mvs),
        ("purgeable_volatile_virtual", _mvs),
        ("compressed", _mvs),
        ("compressed_peak", _mvs),
        ("compressed_lifetime", _mvs),
        ("phys_footprint", _mvs),
    ]


_libc = None


def _load_libc():
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        _libc.mach_task_self.restype = ctypes.c_uint
    return _libc


def phys_footprint_mb() -> float:
    """Process footprint in MB as Activity Monitor reports it, or -1.0."""
    try:
        libc = _load_libc()
        info = _TaskVMInfo()
        count = ctypes.c_uint(ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_int))
        if libc.task_info(libc.mach_task_self(), _TASK_VM_INFO, ctypes.byref(info), ctypes.byref(count)) != 0:
            return -1.0
        return info.phys_footprint / MB
    except Exception:
        log.debug("Could not read phys_footprint", exc_info=True)
        return -1.0


def _mps_memory_mb() -> tuple[float, float]:
    """(in_use, reserved) MPS memory in MB; (-1, -1) when unavailable.

    The gap between them is cache: buffers torch keeps instead of returning to
    the system. A growing *in_use* means a real tensor leak; a growing gap is
    only the per-shape cache, which release_cached_memory() hands back.
    """
    try:
        import torch

        if not torch.backends.mps.is_available():
            return -1.0, -1.0
        return (
            torch.mps.current_allocated_memory() / MB,
            torch.mps.driver_allocated_memory() / MB,
        )
    except Exception:
        return -1.0, -1.0


@dataclass
class MemorySnapshot:
    footprint_mb: float
    mps_in_use_mb: float
    mps_reserved_mb: float
    python_objects: int
    queue_depth: int = -1
    buffered_audio_seconds: float = -1.0
    gc_counts: tuple[int, ...] = field(default_factory=tuple)

    @property
    def mps_cache_mb(self) -> float:
        if self.mps_reserved_mb < 0 or self.mps_in_use_mb < 0:
            return -1.0
        return self.mps_reserved_mb - self.mps_in_use_mb

    def format(self) -> str:
        parts = [f"footprint={self.footprint_mb:.0f}MB"]
        if self.mps_in_use_mb >= 0:
            parts.append(f"mps_in_use={self.mps_in_use_mb:.0f}MB")
            parts.append(f"mps_cache={self.mps_cache_mb:.0f}MB")
        if self.queue_depth >= 0:
            parts.append(f"queue={self.queue_depth}")
        if self.buffered_audio_seconds >= 0:
            parts.append(f"buffered={self.buffered_audio_seconds:.1f}s")
        parts.append(f"objects={self.python_objects}")
        if self.gc_counts:
            parts.append("gc=" + "/".join(str(c) for c in self.gc_counts))
        return "  ".join(parts)


def sample(controller=None) -> MemorySnapshot:
    """Take a memory snapshot, enriched with controller state when available."""
    in_use, reserved = _mps_memory_mb()
    snapshot = MemorySnapshot(
        footprint_mb=phys_footprint_mb(),
        mps_in_use_mb=in_use,
        mps_reserved_mb=reserved,
        python_objects=len(gc.get_objects()),
        gc_counts=gc.get_count(),
    )
    if controller is not None:
        snapshot.queue_depth = _queue_depth(controller)
        snapshot.buffered_audio_seconds = _buffered_audio_seconds(controller)
    return snapshot


def _queue_depth(controller) -> int:
    try:
        return controller._queue.qsize()
    except Exception:
        return -1


def _buffered_audio_seconds(controller) -> float:
    """Total audio sitting in every active stream's segmenter.

    This is the number that exposed the silence-retention bug: it used to climb
    without limit whenever a stream stayed quiet.
    """
    try:
        recorder = controller.recorder
        if recorder is None:
            return -1.0
        total = 0
        rate = 16000
        for worker in getattr(recorder, "_workers", []):
            segmenter = getattr(worker, "_segmenter", None)
            if segmenter is None:
                continue
            total += getattr(segmenter, "_buffered_samples", 0)
            rate = getattr(segmenter, "sample_rate", rate) or rate
        return total / rate
    except Exception:
        return -1.0


class MemoryMonitor:
    """Logs a memory snapshot on an interval. Off unless explicitly enabled.

    Enable with [debug] memory_monitor = true in config.toml, or by setting
    S2T_MEMORY_DEBUG=1. Both the baseline and the growth since it are logged, so
    a leak shows up as a footprint that climbs while mps_in_use stays flat.
    """

    def __init__(self, controller, interval_seconds: float = 60.0) -> None:
        self._controller = controller
        self._interval = max(5.0, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._baseline: MemorySnapshot | None = None
        self._peak_footprint_mb = 0.0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._baseline = sample(self._controller)
        self._peak_footprint_mb = self._baseline.footprint_mb
        log.info("Memory monitor on (every %.0fs). baseline: %s", self._interval, self._baseline.format())
        self._thread = threading.Thread(target=self._loop, daemon=True, name="memory-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self.log_once()

    def log_once(self) -> MemorySnapshot:
        """Log one snapshot immediately; also used by the tray's report action."""
        snapshot = sample(self._controller)
        self._peak_footprint_mb = max(self._peak_footprint_mb, snapshot.footprint_mb)
        growth = ""
        if self._baseline is not None and self._baseline.footprint_mb >= 0:
            delta = snapshot.footprint_mb - self._baseline.footprint_mb
            growth = f"  (since start {delta:+.0f}MB, peak {self._peak_footprint_mb:.0f}MB)"
        log.info("MEM %s%s", snapshot.format(), growth)
        return snapshot


def enabled_from_env() -> bool:
    return os.environ.get("S2T_MEMORY_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}

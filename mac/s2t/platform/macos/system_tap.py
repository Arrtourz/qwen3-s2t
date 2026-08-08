from __future__ import annotations

import logging
import threading
import time

import numpy as np


log = logging.getLogger(__name__)

# Aggregate/tap identifiers. Kept stable so a leaked device from a crashed run
# can be found and destroyed on the next launch.
_AGG_UID = "com.zhenyxu.s2t.tap.agg"
_AGG_NAME = "s2t System Audio"
_TAP_NAME = "s2t-system-tap"


def is_available() -> bool:
    """True if this macOS build exposes the Core Audio process-tap API."""
    try:
        import objc  # noqa: F401
        import CoreAudio as CA

        objc.lookUpClass("CATapDescription")
        return all(
            hasattr(CA, s)
            for s in (
                "AudioHardwareCreateProcessTap",
                "AudioHardwareCreateAggregateDevice",
                "AudioHardwareDestroyAggregateDevice",
                "AudioHardwareDestroyProcessTap",
            )
        )
    except Exception:
        return False


class SystemAudioTap:
    """Captures all system audio output via a Core Audio process tap.

    Unlike the BlackHole approach this does NOT change the user's output device:
    it taps whatever is currently playing (AirPods, built-in speakers, …) and
    automatically follows device switches. Emits downmixed mono float32 blocks
    at the tap's native rate through a callback.
    """

    def __init__(self) -> None:
        self._tap_id = None
        self._agg_id = None
        self._agg_idx = None
        self._agg_name = _AGG_NAME
        self._channels = 2
        self._stream = None
        self._on_block = None
        self._sample_rate = 48000
        self._lock = threading.Lock()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def prepare(self) -> bool:
        """Create the tap + aggregate device and refresh PortAudio ONCE.

        This is the only step that restarts PortAudio (sd._terminate/_initialize),
        which invalidates any already-open sounddevice stream. Callers must run
        prepare() BEFORE opening any other stream (e.g. the mic), then call
        open_stream() afterwards. Returns True on success.
        """
        import objc
        import CoreAudio as CA
        import sounddevice as sd

        with self._lock:
            if self._agg_idx is not None:
                return True

            CATapDescription = objc.lookUpClass("CATapDescription")
            tap_desc = CATapDescription.alloc().initStereoGlobalTapButExcludeProcesses_([])
            tap_desc.setName_(_TAP_NAME)
            try:
                tap_desc.setPrivate_(True)
            except Exception:
                pass

            err, tap_id = CA.AudioHardwareCreateProcessTap(tap_desc, None)
            if err != 0 or not tap_id:
                log.error("AudioHardwareCreateProcessTap failed: err=%s", err)
                return False
            self._tap_id = tap_id

            uid = str(tap_desc.UUID().UUIDString())
            # Unique uid+name per activation; reusing a fixed uid left CoreAudio
            # with a stale registration that PortAudio wouldn't re-expose.
            unique = uid.replace("-", "")[:12]
            agg_uid = f"{_AGG_UID}.{unique}"
            agg_name = f"{_AGG_NAME} {unique}"
            self._agg_name = agg_name
            desc = {
                "uid": agg_uid,
                "name": agg_name,
                "private": 1,
                "stacked": 0,
                "tapautostart": 1,
                "taps": [{"uid": uid, "drift": 0}],
                "subdevices": [],
            }
            err2, agg_id = CA.AudioHardwareCreateAggregateDevice(desc, None)
            if err2 != 0 or not agg_id:
                log.error("AudioHardwareCreateAggregateDevice failed: err=%s", err2)
                CA.AudioHardwareDestroyProcessTap(tap_id)
                self._tap_id = None
                return False
            self._agg_id = agg_id

            # Refresh PortAudio and wait for the aggregate device to appear.
            agg_idx = None
            for _ in range(10):
                sd._terminate()
                sd._initialize()
                agg_idx = next(
                    (i for i, d in enumerate(sd.query_devices()) if d["name"] == agg_name),
                    None,
                )
                if agg_idx is not None:
                    break
                time.sleep(0.15)
            if agg_idx is None:
                log.error("Aggregate device not visible to sounddevice after retries")
                self._teardown_devices()
                return False

            info = sd.query_devices(agg_idx)
            self._sample_rate = int(info["default_samplerate"])
            self._channels = max(1, info["max_input_channels"])
            self._agg_idx = agg_idx
            return True

    def open_stream(self, on_block) -> bool:
        """Open the tap input stream. Must be called AFTER prepare(). Does NOT
        restart PortAudio, so it is safe to open alongside the mic stream."""
        import sounddevice as sd

        with self._lock:
            if self._stream is not None:
                return True
            if self._agg_idx is None:
                log.error("open_stream() called before prepare()")
                return False
            self._on_block = on_block

            def _cb(indata, frames, time_info, status):
                if status:
                    log.debug("System tap status: %s", status)
                mono = np.asarray(indata, dtype=np.float32)
                if mono.ndim > 1 and mono.shape[1] > 1:
                    mono = mono.mean(axis=1)
                else:
                    mono = mono.reshape(-1)
                if self._on_block is not None:
                    self._on_block(mono, self._sample_rate)

            try:
                self._stream = sd.InputStream(
                    device=self._agg_idx,
                    channels=self._channels,
                    samplerate=self._sample_rate,
                    dtype="float32",
                    callback=_cb,
                )
                self._stream.start()
            except Exception:
                log.exception("Failed to open system tap stream")
                self._stream = None
                self._teardown_devices()
                return False

            log.info("System audio tap started at %dHz", self._sample_rate)
            return True

    def start(self, on_block) -> bool:
        """Convenience: prepare + open_stream in one call (single-stream use)."""
        return self.prepare() and self.open_stream(on_block)

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                finally:
                    self._stream.close()
                    self._stream = None
            self._teardown_devices()
            self._on_block = None

    def _teardown_devices(self) -> None:
        import CoreAudio as CA

        if self._agg_id:
            CA.AudioHardwareDestroyAggregateDevice(self._agg_id)
            self._agg_id = None
        if self._tap_id:
            CA.AudioHardwareDestroyProcessTap(self._tap_id)
            self._tap_id = None
        self._agg_idx = None


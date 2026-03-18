"""Audio capture at 16kHz for Qwen3-ASR via parec (PulseAudio direct).

Mic behavior (like Win+H):
  - Hotkey press: open stream + start recording
  - Hotkey press again: stop recording + close stream (mic released)
"""

import collections
import logging
import os
import subprocess
import threading

import numpy as np

log = logging.getLogger("s2t")

SAMPLE_RATE = 16000  # Qwen3-ASR expects 16kHz
_CHUNK_SIZE = 4096
# Max chunks for 60s window (continuous mode only)
_MAX_CHUNKS_60S = int(60 * SAMPLE_RATE * 2 / _CHUNK_SIZE)  # ~= 469

_proc = None
_reader_thread = None
_raw_chunks: collections.deque = collections.deque()  # maxlen set at start_recording
_is_recording = False


def _get_pulse_input_source():
    """Return the first real (non-monitor) PulseAudio input source name, or None."""
    try:
        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True,
            text=True,
            timeout=5,
            env=os.environ.copy(),
        )
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[1]
                if ".monitor" not in name and "input" in name:
                    return name
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[1]
                if ".monitor" not in name:
                    return name
    except Exception as exc:
        log.warning("pactl error: %s", exc)
    return None


def _reader_loop(proc):
    """Read s16le chunks from parec stdout; store when recording."""
    while True:
        chunk = proc.stdout.read(4096)
        if not chunk:
            break
        if _is_recording:
            _raw_chunks.append(chunk)


def check_mic_permission():
    """Try spawning parec briefly. Returns error string or None if OK."""
    source = _get_pulse_input_source()
    cmd = ["parec", "--rate=16000", "--channels=1", "--format=s16le"]
    if source:
        cmd += [f"--device={source}"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
        )
        import time as _t

        _t.sleep(0.2)
        proc.terminate()
        proc.wait(timeout=2)
        return None
    except Exception as exc:
        return str(exc)


def open_mic():
    """Spawn parec stream. Returns True on success."""
    global _proc, _reader_thread
    if _proc is not None:
        return True

    source = _get_pulse_input_source()
    cmd = ["parec", "--rate=16000", "--channels=1", "--format=s16le", "--latency-msec=50"]
    if source:
        cmd += [f"--device={source}"]
        log.info("Using mic: %s", source)
    else:
        log.warning("No mic source found, using PulseAudio default")

    try:
        _proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
        )
        _reader_thread = threading.Thread(target=_reader_loop, args=(_proc,), daemon=True)
        _reader_thread.start()
        return True
    except Exception as exc:
        log.error("Cannot open mic: %s", exc)
        _proc = None
        return False


def close_mic():
    """Terminate parec and release mic."""
    global _proc, _reader_thread
    if _proc is not None:
        try:
            _proc.terminate()
            _proc.wait(timeout=2)
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
        _proc = None
    if _reader_thread is not None:
        _reader_thread.join(timeout=2)
        _reader_thread = None


def start_recording(windowed: bool = False):
    """Open mic and start capturing. Returns False on mic error.

    windowed: if True, keep only the last 60s (continuous mode).
    """
    global _is_recording, _raw_chunks
    if not open_mic():
        return False
    maxlen = _MAX_CHUNKS_60S if windowed else None
    _raw_chunks = collections.deque(maxlen=maxlen)
    _is_recording = True
    return True


def stop_recording(debug_dir=None):
    """Stop capturing and close mic. Returns captured numpy array or None."""
    global _is_recording
    _is_recording = False
    close_mic()
    if not _raw_chunks:
        log.error("Buffer is EMPTY - no audio captured at all.")
        return None
    raw = b"".join(_raw_chunks)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(audio**2)))
    peak = float(np.max(np.abs(audio)))
    dur = len(audio) / SAMPLE_RATE
    log.info("Captured %s samples (%.2fs), RMS=%.6f, peak=%.6f", len(audio), dur, rms, peak)
    if debug_dir:
        import soundfile as sf
        import time as _t

        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, f"rec_{int(_t.time())}.wav")
        sf.write(path, audio, SAMPLE_RATE)
        log.info("Saved debug WAV: %s", path)
    return audio


def snapshot_recording(debug_dir=None):
    """Continuous mode: snapshot current buffer, clear it, keep mic open."""
    global _raw_chunks
    chunks = list(_raw_chunks)
    _raw_chunks.clear()
    if not chunks:
        return None
    raw = b"".join(chunks)
    audio_data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(audio_data**2)))
    dur = len(audio_data) / SAMPLE_RATE
    log.info("Snapshot %s samples (%.2fs), RMS=%.6f", len(audio_data), dur, rms)
    if debug_dir:
        import soundfile as sf
        import time as _t

        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, f"snap_{int(_t.time())}.wav")
        sf.write(path, audio_data, SAMPLE_RATE)
        log.info("Saved debug WAV: %s", path)
    return audio_data


def is_recording():
    return _is_recording

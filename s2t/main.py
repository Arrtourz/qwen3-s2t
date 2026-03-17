"""
s2t - Speech-to-Text app for Ubuntu using Qwen3-ASR-1.7B.

Hotkey: double-click Ctrl.

Modes (default: continuous):
  continuous (default): 1st double-click opens mic; each subsequent double-click
                        transcribes accumulated audio and keeps mic open.
  manual (--manual):    1st double-click starts recording, 2nd stops + transcribes.

Usage:
    python -m s2t                         # continuous mode
    python -m s2t --manual                # manual start/stop mode
    S2T_LANGUAGE=Chinese python -m s2t
    QWEN3_ASR_MODEL=/path/to/model python -m s2t
"""

import fcntl
import numpy as np
import logging
import os
import queue
import subprocess
import sys
import threading
import time

sys.path.append('/usr/lib/python3/dist-packages')

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tmp', 's2t.log')
_log_handlers = [logging.StreamHandler(sys.stdout)]
if '--debug' in sys.argv:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    _log_handlers.append(logging.FileHandler(LOG_FILE, encoding='utf-8'))
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=_log_handlers,
)
log = logging.getLogger('s2t')

from pynput import keyboard as kb

from . import audio, transcription
from .paste import paste_text

LANGUAGE = os.environ.get('S2T_LANGUAGE', 'Chinese')  # avoid collision with system LANGUAGE env var
MANUAL_MODE = '--manual' in sys.argv
DEBUG_MODE = '--debug' in sys.argv

# ── Double-tap Ctrl detection ────────────────────────────────────────────────
# Ctrl keys pynput reports as: 'ctrl_l', 'ctrl_r', 'ctrl'
_CTRL_NAMES = frozenset({'ctrl', 'ctrl_l', 'ctrl_r'})
_DOUBLE_TAP_WINDOW = 0.5   # seconds between two releases
_EXEC_DELAY       = 0.3    # wait this long after 2nd tap before firing

_tap_count     = 0
_last_tap_time = 0.0
_fire_timer    = None
_tap_lock      = threading.Lock()


def _key_name(key):
    if hasattr(key, 'name') and key.name:
        return key.name
    if hasattr(key, 'char') and key.char:
        return key.char.lower()
    return None


def _fire_action():
    """Called after double-tap confirmed."""
    global _tap_count
    with _tap_lock:
        _tap_count = 0
    _toggle_recording()


_LONG_PRESS_DURATION = 2.0   # seconds to hold Ctrl for quit
_ctrl_press_time = None      # when Ctrl was pressed down
_long_press_timer = None


def _quit():
    """Beep and exit."""
    log.info("Long-press Ctrl detected — quitting.")
    _beep(440, 400)
    time.sleep(0.5)
    os._exit(0)


def _on_press(key):
    global _ctrl_press_time, _long_press_timer
    name = _key_name(key)
    if name not in _CTRL_NAMES:
        return
    if _ctrl_press_time is None:
        _ctrl_press_time = time.monotonic()
        _long_press_timer = threading.Timer(_LONG_PRESS_DURATION, _quit)
        _long_press_timer.start()


def _on_release(key):
    global _tap_count, _last_tap_time, _fire_timer
    global _ctrl_press_time, _long_press_timer

    name = _key_name(key)
    if name not in _CTRL_NAMES:
        return

    # Cancel long-press timer on release
    if _long_press_timer is not None:
        _long_press_timer.cancel()
        _long_press_timer = None
    _ctrl_press_time = None

    now = time.monotonic()
    with _tap_lock:
        if now - _last_tap_time < _DOUBLE_TAP_WINDOW:
            _tap_count += 1
        else:
            _tap_count = 1
        _last_tap_time = now

        # Cancel any pending fire timer
        if _fire_timer is not None:
            _fire_timer.cancel()
            _fire_timer = None

        if _tap_count >= 2:
            _tap_count = 0
            _fire_timer = threading.Timer(_EXEC_DELAY, _fire_action)
            _fire_timer.start()


# ── Recording toggle ─────────────────────────────────────────────────────────
processing_queue: queue.Queue = queue.Queue()


DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tmp', 'recordings') if DEBUG_MODE else None


def _toggle_recording():
    if MANUAL_MODE:
        if audio.is_recording():
            _stop_and_queue()
        else:
            _start_recording()
    else:
        if not audio.is_recording():
            _start_recording()
        else:
            _snapshot_and_queue()


def _start_recording():
    ok = audio.start_recording(windowed=not MANUAL_MODE)
    if not ok:
        log.error("Cannot open microphone. Check permissions (pactl / audio group).")
        _notify("s2t", "Mic error: cannot open microphone.", urgency='critical')
        return
    log.info("Recording started.")
    _beep(600, 150)


def _stop_and_queue():
    data = audio.stop_recording(debug_dir=DEBUG_DIR)
    log.info("Recording stopped.")
    if data is None or len(data) < 1600:
        log.warning("Audio too short, ignoring.")
        return
    rms = float(np.sqrt(np.mean(data ** 2)))
    if rms < 0.002:
        log.warning(f"Mic level low (RMS={rms:.5f}), proceeding anyway.")
    processing_queue.put(data)


def _snapshot_and_queue():
    data = audio.snapshot_recording(debug_dir=DEBUG_DIR)
    if data is None or len(data) < 1600:
        log.warning("Audio too short, ignoring.")
        return
    rms = float(np.sqrt(np.mean(data ** 2)))
    if rms < 0.002:
        log.warning(f"Mic level low (RMS={rms:.5f}), proceeding anyway.")
    processing_queue.put(data)


# ── Processing thread ────────────────────────────────────────────────────────
def _processing_loop():
    while True:
        audio_data = processing_queue.get()
        try:
            log.info("Transcribing...")
            text = transcription.transcribe(audio_data, language=LANGUAGE)
            if text:
                log.info(f"Transcribed: {text!r}")
                paste_text(text)
                _beep(880, 200)  # high beep = success
            else:
                log.warning("No speech detected.")
                _beep(300, 250)  # low tone = no speech
        except Exception as e:
            log.exception(f"Transcription error: {e}")
            _notify("s2t", f"Error: {e}", urgency='critical')


# ── Audio feedback (beeps) ───────────────────────────────────────────────────
def _beep(freq: int, duration_ms: int):
    """Play a beep via paplay (non-blocking)."""
    def _play():
        import io, wave, tempfile, os as _os
        n = int(44100 * duration_ms / 1000)
        t = np.linspace(0, duration_ms / 1000, n, False)
        data = np.sin(2 * np.pi * freq * t)
        fade = int(44100 * 0.01)
        if n > fade * 2:
            data[:fade] *= np.linspace(0, 1, fade)
            data[-fade:] *= np.linspace(1, 0, fade)
        pcm = (data * 32767 * 0.5).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(44100)
            wf.writeframes(pcm.tobytes())
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(buf.getvalue()); tmp = f.name
        try:
            subprocess.run(['paplay', tmp], timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        finally:
            try: _os.unlink(tmp)
            except: pass
    threading.Thread(target=_play, daemon=True).start()


def _notify(summary: str, body: str = '', urgency: str = 'normal'):
    """Visual fallback for errors only; normal feedback is audio beeps."""
    if urgency == 'normal':
        return
    try:
        subprocess.Popen(
            ['notify-send', '-u', urgency, '-t', '3000', summary, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        print(f"[notify] {summary}: {body}")


# ── Single-instance lock ─────────────────────────────────────────────────────
_lock_file = None


def _acquire_lock():
    global _lock_file
    f = open('/tmp/s2t.lock', 'w')
    try:
        fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file = f
        return True
    except IOError:
        return False


# ── Entry point ──────────────────────────────────────────────────────────────
def main():
    if not _acquire_lock():
        print("s2t is already running.")
        sys.exit(1)

    mode_str = "manual" if MANUAL_MODE else "continuous"
    print(f"[s2t] Starting. Mode: {mode_str} | Hotkey: double-click Ctrl | Language: {LANGUAGE or 'auto'}")
    print(f"[s2t] Model: {os.environ.get('QWEN3_ASR_MODEL', 'Qwen/Qwen3-ASR-1.7B')}")

    # Check mic availability upfront
    err = audio.check_mic_permission()
    if err:
        log.warning(f"Mic check failed: {err}. Ensure you are in the 'audio' group and PulseAudio/PipeWire is running.")
    else:
        log.info("Mic check OK.")

    transcription.load_model()

    threading.Thread(target=_processing_loop, daemon=True).start()

    _notify("s2t", "Ready. Double-click Ctrl to record.")
    log.info(f"Ready. Log: {LOG_FILE}")

    with kb.Listener(on_press=_on_press, on_release=_on_release) as listener:
        listener.join()

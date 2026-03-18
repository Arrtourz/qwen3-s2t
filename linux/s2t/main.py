"""Linux speech-to-text app for Ubuntu using Qwen3-ASR."""

import argparse
from dataclasses import replace
import fcntl
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

import numpy as np

sys.path.append("/usr/lib/python3/dist-packages")

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tmp", "s2t.log")
_log_handlers = [logging.StreamHandler(sys.stdout)]
if "--debug" in sys.argv:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    _log_handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=_log_handlers,
)
log = logging.getLogger("s2t")

from pynput import keyboard as kb

from . import audio, transcription
from .config import ConfigError, infer_model_variant, load_config
from .paste import paste_text

DEBUG_MODE = "--debug" in sys.argv
LANGUAGE = "Chinese"
MANUAL_MODE = False

_CTRL_NAMES = frozenset({"ctrl", "ctrl_l", "ctrl_r"})
_DOUBLE_TAP_WINDOW = 0.5
_EXEC_DELAY = 0.3

_tap_count = 0
_last_tap_time = 0.0
_fire_timer = None
_tap_lock = threading.Lock()


def _key_name(key):
    if hasattr(key, "name") and key.name:
        return key.name
    if hasattr(key, "char") and key.char:
        return key.char.lower()
    return None


def _fire_action():
    global _tap_count
    with _tap_lock:
        _tap_count = 0
    _toggle_recording()


_LONG_PRESS_DURATION = 2.0
_ctrl_press_time = None
_long_press_timer = None


def _quit():
    log.info("Long-press Ctrl detected - quitting.")
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

        if _fire_timer is not None:
            _fire_timer.cancel()
            _fire_timer = None

        if _tap_count >= 2:
            _tap_count = 0
            _fire_timer = threading.Timer(_EXEC_DELAY, _fire_action)
            _fire_timer.start()


processing_queue: queue.Queue = queue.Queue()

DEBUG_DIR = (
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "tmp", "recordings")
    if DEBUG_MODE
    else None
)


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
        _notify("s2t", "Mic error: cannot open microphone.", urgency="critical")
        return
    log.info("Recording started.")
    _beep(600, 150)


def _stop_and_queue():
    data = audio.stop_recording(debug_dir=DEBUG_DIR)
    log.info("Recording stopped.")
    if data is None or len(data) < 1600:
        log.warning("Audio too short, ignoring.")
        return
    rms = float(np.sqrt(np.mean(data**2)))
    if rms < 0.002:
        log.warning("Mic level low (RMS=%.5f), proceeding anyway.", rms)
    processing_queue.put(data)


def _snapshot_and_queue():
    data = audio.snapshot_recording(debug_dir=DEBUG_DIR)
    if data is None or len(data) < 1600:
        log.warning("Audio too short, ignoring.")
        return
    rms = float(np.sqrt(np.mean(data**2)))
    if rms < 0.002:
        log.warning("Mic level low (RMS=%.5f), proceeding anyway.", rms)
    processing_queue.put(data)


def _processing_loop():
    while True:
        audio_data = processing_queue.get()
        try:
            log.info("Transcribing...")
            text = transcription.transcribe(audio_data, language=LANGUAGE)
            if text:
                log.info("Transcribed: %r", text)
                paste_text(text)
                _beep(880, 200)
            else:
                log.warning("No speech detected.")
                _beep(300, 250)
        except Exception as exc:
            log.exception("Transcription error: %s", exc)
            _notify("s2t", f"Error: {exc}", urgency="critical")


def _beep(freq: int, duration_ms: int):
    def _play():
        import io
        import os as _os
        import tempfile
        import wave

        n = int(44100 * duration_ms / 1000)
        t = np.linspace(0, duration_ms / 1000, n, False)
        data = np.sin(2 * np.pi * freq * t)
        fade = int(44100 * 0.01)
        if n > fade * 2:
            data[:fade] *= np.linspace(0, 1, fade)
            data[-fade:] *= np.linspace(1, 0, fade)
        pcm = (data * 32767 * 0.5).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(pcm.tobytes())
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(buf.getvalue())
            tmp = f.name
        try:
            subprocess.run(
                ["paplay", tmp],
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
        finally:
            try:
                _os.unlink(tmp)
            except Exception:
                pass

    threading.Thread(target=_play, daemon=True).start()


def _notify(summary: str, body: str = "", urgency: str = "normal"):
    if urgency == "normal":
        return
    try:
        subprocess.Popen(
            ["notify-send", "-u", urgency, "-t", "3000", summary, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        print(f"[notify] {summary}: {body}")


_lock_file = None


def _acquire_lock():
    global _lock_file
    f = open("/tmp/s2t.lock", "w")
    try:
        fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file = f
        return True
    except IOError:
        return False


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Linux speech-to-text app")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--manual",
        action="store_true",
        help="Use manual start/stop recording instead of continuous mode",
    )
    mode_group.add_argument(
        "--continuous",
        action="store_true",
        help="Force continuous recording mode",
    )
    parser.add_argument(
        "--model",
        choices=["0.6b", "1.7b"],
        help="Temporarily choose the ASR model variant for this run",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "gpu"],
        help="Temporarily choose whether the ASR model runs on auto/cpu/gpu",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable log file output and save WAV recordings",
    )
    return parser


def _runtime_config(args: argparse.Namespace):
    config_override = os.environ.get("S2T_CONFIG_PATH", "").strip()
    config_path = Path(config_override) if config_override else None
    config = load_config(config_path)

    if "S2T_LANGUAGE" in os.environ:
        config = replace(config, language=os.environ["S2T_LANGUAGE"].strip())

    model_id_override = os.environ.get("QWEN3_ASR_MODEL", "").strip()
    if model_id_override:
        config = replace(
            config,
            model=replace(
                config.model,
                variant=infer_model_variant(model_id_override),
                path_or_id=model_id_override,
            ),
        )

    device_override = os.environ.get("S2T_DEVICE", "").strip().lower()
    if device_override:
        if device_override not in {"auto", "cpu", "gpu"}:
            raise ConfigError("S2T_DEVICE must be 'auto', 'cpu', or 'gpu'")
        config = replace(config, model=replace(config.model, device=device_override))

    if args.manual:
        config = replace(config, recording=replace(config.recording, mode="manual"))
    elif args.continuous:
        config = replace(config, recording=replace(config.recording, mode="continuous"))

    if args.model:
        model_id = {
            "0.6b": "Qwen/Qwen3-ASR-0.6B",
            "1.7b": "Qwen/Qwen3-ASR-1.7B",
        }[args.model]
        config = replace(
            config,
            model=replace(config.model, variant=args.model, path_or_id=model_id),
        )

    if args.device:
        config = replace(config, model=replace(config.model, device=args.device))

    return config


def main():
    global LANGUAGE, MANUAL_MODE

    parser = build_arg_parser()
    args = parser.parse_args()

    if not _acquire_lock():
        print("s2t is already running.")
        sys.exit(1)

    try:
        config = _runtime_config(args)
    except ConfigError as exc:
        print(f"s2t config error: {exc}", file=sys.stderr)
        sys.exit(2)

    LANGUAGE = config.language
    MANUAL_MODE = config.recording.mode == "manual"
    mode_str = config.recording.mode
    print(
        f"[s2t] Starting. Mode: {mode_str} | Hotkey: double-click Ctrl | Language: {LANGUAGE or 'auto'}"
    )
    print(
        f"[s2t] Model: {config.model.path_or_id} | Variant: {config.model.variant or 'custom'} | Device: {config.model.device}"
    )

    err = audio.check_mic_permission()
    if err:
        log.warning(
            "Mic check failed: %s. Ensure you are in the 'audio' group and PulseAudio/PipeWire is running.",
            err,
        )
    else:
        log.info("Mic check OK.")

    transcription.load_model(config.model)

    threading.Thread(target=_processing_loop, daemon=True).start()

    _notify("s2t", "Ready. Double-click Ctrl to record.")
    log.info("Ready. Log: %s", LOG_FILE)

    with kb.Listener(on_press=_on_press, on_release=_on_release) as listener:
        listener.join()

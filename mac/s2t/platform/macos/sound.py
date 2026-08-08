from __future__ import annotations

import subprocess
import threading


_TONES = {
    "start":    ("start", 620, 0.12),
    "snapshot": ("snapshot", 760, 0.09),
    "done":     ("done", 880, 0.16),
    "error":    ("error", 280, 0.18),
    "short":    ("short", 320, 0.18),
}


def beep(tone: str) -> None:
    threading.Thread(target=_play, args=(tone,), daemon=True).start()


def _play(tone: str) -> None:
    try:
        import numpy as np
        import sounddevice as sd

        _, freq, duration = _TONES.get(tone, ("_", 440, 0.1))
        sample_rate = 22050
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave = (np.sin(2 * np.pi * freq * t) * 0.35).astype(np.float32)
        # fade out last 20%
        fade_len = int(len(wave) * 0.2)
        wave[-fade_len:] *= np.linspace(1, 0, fade_len)
        sd.play(wave, samplerate=sample_rate)
        sd.wait()
    except Exception:
        pass

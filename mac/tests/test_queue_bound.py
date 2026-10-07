from __future__ import annotations

import queue

import numpy as np

from s2t.core.controller import MAX_PENDING_SEGMENTS, SpeechToTextController


def _bare_controller(maxsize: int) -> SpeechToTextController:
    """A controller with only the queue wired up.

    Full __init__ builds the tray, hotkey and audio stack; the backlog policy is
    independent of all of it, so the queue is attached directly.
    """
    controller = object.__new__(SpeechToTextController)
    controller._queue = queue.Queue(maxsize=maxsize)
    return controller


def _segment(seconds: float = 1.0) -> np.ndarray:
    return np.zeros(int(16000 * seconds), dtype=np.float32)


def test_enqueue_keeps_queue_bounded():
    controller = _bare_controller(4)
    for i in range(50):
        controller._enqueue(f"spk{i}", _segment())
    assert controller._queue.qsize() == 4


def test_enqueue_drops_oldest_first():
    controller = _bare_controller(2)
    for label in ("a", "b", "c"):
        controller._enqueue(label, _segment())
    remaining = [controller._queue.get_nowait()[0] for _ in range(2)]
    assert remaining == ["b", "c"]  # "a" evicted, order preserved


def test_enqueue_passes_audio_through_unchanged():
    controller = _bare_controller(MAX_PENDING_SEGMENTS)
    audio = _segment(0.5)
    controller._enqueue("me", audio)
    speaker, got = controller._queue.get_nowait()
    assert speaker == "me"
    assert got is audio

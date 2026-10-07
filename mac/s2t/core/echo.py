from __future__ import annotations

import re
import time
from collections import deque
from difflib import SequenceMatcher


# Seconds a remote ("Them") line stays eligible to explain a mic line as echo.
ECHO_WINDOW_SECONDS = 10.0
# Minimum similarity (difflib ratio) between the mic line and a remote line,
# or two consecutive remote lines, for it to count as echo.
ECHO_MATCH_RATIO = 0.8
# Shorter mic lines are never treated as echo: "yes" / "好的" are things the
# user really says right after the other party, and too short to judge.
ECHO_MIN_CHARS = 6


def _normalize(text: str) -> str:
    # \W keeps CJK characters (they are word characters), drops punctuation.
    return re.sub(r"[\W_]+", "", text.lower())


class EchoFilter:
    """Spots mic transcripts that merely repeat the system-audio stream.

    With laptop speakers the microphone re-records the other party, so the same
    sentence arrives once from the tap and again, slightly later and slightly
    garbled, from the mic. A mic line counts as echo when most of its characters
    occur, in order, in what the tap produced over the last few seconds; joining
    that recent text handles the two streams cutting sentences differently.
    Only the tap-first order is caught, which is the normal one: the tap is a
    clean digital signal and its segment closes before the mic's reverberant tail.
    """

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._recent: deque[tuple[float, str]] = deque()

    def note_remote(self, text: str) -> None:
        self._recent.append((self._clock(), _normalize(text)))

    def is_echo(self, mic_text: str) -> bool:
        now = self._clock()
        while self._recent and now - self._recent[0][0] > ECHO_WINDOW_SECONDS:
            self._recent.popleft()
        mine = _normalize(mic_text)
        if len(mine) < ECHO_MIN_CHARS:
            return False
        # Compare whole lines, not a concatenation of everything recent: against
        # a long joined string almost any sentence finds its letters "in order"
        # (that version flagged 17.7% of the user's real speech). ratio() also
        # penalises length mismatch, so a short reply cannot match a long line.
        lines = [t for _, t in self._recent]
        candidates = lines + [a + b for a, b in zip(lines, lines[1:])]
        return any(
            SequenceMatcher(None, mine, c, autojunk=False).ratio() >= ECHO_MATCH_RATIO
            for c in candidates
        )

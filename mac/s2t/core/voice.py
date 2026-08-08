from __future__ import annotations

import re

import numpy as np


# Qwen-ASR (and most ASR models) "hallucinate" filler tokens on blank/near-silent
# audio. When a segment is acoustically weak AND the transcript is just such a
# filler, we drop it instead of writing it to the meeting notes.
_FILLER_TRANSCRIPTS = {
    "嗯", "嗯。", "嗯嗯", "呃", "啊", "哦", "唉", "额", "呢", "吧",
    "。", "，", "、", "…", "......", "...",
    "you", "yeah", "uh", "um", "hmm", "mm", "mhm", "ah", "oh", ".",
    "thank you.", "thanks for watching!", "谢谢观看", "谢谢大家",
}


def has_voice(
    audio_16k: np.ndarray,
    *,
    sample_rate: int = 16000,
    frame_rms: float = 0.045,
    max_zcr: float = 0.32,
    min_voiced_ratio: float = 0.30,
) -> bool:
    """Frame-based voice-activity detection; True if the segment is real speech.

    Follows the standard VAD approach (WebRTC/G.729-style): split the segment
    into short frames, classify EACH frame as voiced/unvoiced, then decide the
    whole segment by the fraction of voiced frames. This is far more robust than
    a single whole-segment average — a real utterance contains pauses that drag
    the average down, while steady background noise has few genuinely voiced
    frames even when its average energy is comparable.
    """
    _rms, _zcr, ratio, ok = voice_metrics(
        audio_16k,
        sample_rate=sample_rate,
        frame_rms=frame_rms,
        max_zcr=max_zcr,
        min_voiced_ratio=min_voiced_ratio,
    )
    return ok


def voice_metrics(
    audio_16k: np.ndarray,
    *,
    sample_rate: int = 16000,
    frame_rms: float = 0.045,
    max_zcr: float = 0.32,
    min_voiced_ratio: float = 0.30,
) -> tuple[float, float, float, bool]:
    """Return (rms, zcr, voiced_ratio, is_voice) for logging the VAD decision.

    Per-frame rule (20 ms frames): a frame is "voiced" when its RMS clears
    ``frame_rms`` AND its zero-crossing rate is speech-like (< ``max_zcr``; hiss
    sits near 0.5, voiced speech far lower). The segment is speech when at least
    ``min_voiced_ratio`` of its frames are voiced.

    ``rms``/``zcr`` in the return are whole-segment values, kept only for logs.
    """
    audio = np.asarray(audio_16k, dtype=np.float32).reshape(-1)
    if audio.size < sample_rate // 10:  # < 100 ms
        return 0.0, 0.0, 0.0, False

    seg_rms = float(np.sqrt(np.mean(audio**2)))
    seg_signs = np.sign(audio)
    seg_signs[seg_signs == 0] = 1
    seg_zcr = float(np.mean(np.abs(np.diff(seg_signs)) > 0))

    # Split into 20 ms frames.
    frame = max(1, int(sample_rate * 0.02))
    n = audio.size // frame
    if n < 3:
        return seg_rms, seg_zcr, 0.0, False
    frames = audio[: n * frame].reshape(n, frame)

    # Per-frame RMS.
    f_rms = np.sqrt(np.mean(frames**2, axis=1))
    # Per-frame zero-crossing rate.
    f_signs = np.sign(frames)
    f_signs[f_signs == 0] = 1
    f_zcr = np.mean(np.abs(np.diff(f_signs, axis=1)) > 0, axis=1)

    voiced = (f_rms >= frame_rms) & (f_zcr < max_zcr)
    voiced_ratio = float(np.mean(voiced))

    is_voice = voiced_ratio >= min_voiced_ratio
    return seg_rms, seg_zcr, voiced_ratio, is_voice


def is_filler(text: str) -> bool:
    """True if the transcript is an ASR filler/hallucination worth dropping.

    Beyond a fixed list of known fillers, we drop any transcript that, after
    stripping punctuation, is just a SINGLE short token — a lone "The.", "Hmm.",
    "Okay.", "嗯。" etc. These almost always come from noise/near-silence that
    slipped past the VAD, never from a real sentence worth keeping.
    """
    t = text.strip().lower()
    if not t:
        return True
    normalized = re.sub(r"\s+", " ", t)
    if normalized in _FILLER_TRANSCRIPTS:
        return True

    # Strip surrounding/embedded punctuation, keep word boundaries.
    core = re.sub(r"[。，、．・…!?！？.,;:；：\"'“”‘’()\[\]]+", " ", normalized).strip()
    if not core:
        return True

    # A single English word (no spaces, alphabetic) is a hallucination.
    if " " not in core and core.replace("'", "").isalpha() and core.isascii():
        return True

    # One or two lone CJK characters with no other content.
    cjk = re.findall(r"[一-鿿]", core)
    non_cjk = re.sub(r"[一-鿿\s]", "", core)
    if cjk and not non_cjk and len(cjk) <= 2:
        return True

    return False

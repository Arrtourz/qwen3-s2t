from __future__ import annotations

from dataclasses import dataclass
import gc
import logging
import os
from pathlib import Path
import subprocess
import threading
import uuid
import wave

import numpy as np

from .config import ModelConfig, runtime_temp_dir


SAMPLE_RATE = 16000

log = logging.getLogger(__name__)


# A GPU backend keeps freed buffers in a per-shape cache rather than returning
# them to the system. Utterances vary in length, so every new duration mints a
# new shape, and across a long meeting the cache grows far beyond what is live —
# measured at 2.4GB of slack after 40 turns, which does not show up in RSS at all
# (it is IOAccelerator memory, visible only as phys_footprint / Activity Monitor).
# Released when the slack exceeds this much and there is no queued work.
CACHE_SLACK_RELEASE_BYTES = 512 * 1024 * 1024

# The GPU backend compiles and caches one compute graph per distinct input
# shape and never evicts them. Utterance lengths are effectively continuous, so
# over hours the graph cache grows without bound (a 5h session held 2116 graphs,
# ~1.6GB of heap). Zero-padding audio up to a whole number of these steps caps
# the shapes at ~20 for 0.5-20s utterances. Trailing silence does not change
# Qwen3-ASR output: 10/10 real recorded segments transcribed identically.
SHAPE_BUCKET_SAMPLES = SAMPLE_RATE  # 1 s


class ASRBackend:
    def load_model(self) -> None:
        raise NotImplementedError

    def transcribe(self, audio_16k: np.ndarray, language: str | None) -> str:
        raise NotImplementedError

    def release_cached_memory(self, min_slack_bytes: int = CACHE_SLACK_RELEASE_BYTES) -> int:
        """Return unused cached GPU memory to the system. Returns bytes freed."""
        return 0

    @property
    def is_loaded(self) -> bool:
        return True

    def unload(self) -> None:
        """Drop the model from memory; the next transcribe reloads it."""


@dataclass
class Qwen3ASRBackend(ASRBackend):
    config: ModelConfig

    def __post_init__(self) -> None:
        self._model = None
        self._device = "cpu"
        # Serializes load / transcribe / unload / cache release: they run on the
        # worker, the idle-unload timer and meeting start, and none of them may
        # see the model half-built or yanked away mid-inference.
        self._lock = threading.RLock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load_model(self) -> None:
        with self._lock:
            self._load_locked()

    def _load_locked(self) -> None:
        if self._model is not None:
            return

        import torch

        from .lazy_imports import defer_unused_imports, disable_unused_transformers_integrations

        defer_unused_imports()
        disable_unused_transformers_integrations()
        from qwen_asr import Qwen3ASRModel

        device = _resolve_device(self.config.device)
        self._device = device
        dtype = _resolve_dtype(device)

        log.info(
            "Loading ASR model %s (variant=%s) on %s",
            self.config.path_or_id,
            self.config.variant or "custom",
            device,
        )
        self._model = Qwen3ASRModel.from_pretrained(
            self.config.path_or_id,
            dtype=dtype,
            device_map=device,
            max_new_tokens=256,
        )

    def transcribe(self, audio_16k: np.ndarray, language: str | None) -> str:
        with self._lock:
            # Reload on demand after an idle unload; segments that arrived
            # meanwhile simply wait in the queue.
            self._load_locked()
            audio = _pad_to_bucket(audio_16k) if self._device != "cpu" else audio_16k
            results = self._model.transcribe(audio=(audio, SAMPLE_RATE), language=language)
        if not results:
            return ""
        return results[0].text.strip()

    def unload(self) -> None:
        """Free the model's weights (~2GB on MPS) until it is next needed."""
        with self._lock:
            if self._model is None:
                return
            self._model = None
            gc.collect()
            self._empty_cache()
        log.info("Unloaded ASR model while idle")

    def _empty_cache(self) -> None:
        import torch

        try:
            if self._device == "mps":
                torch.mps.empty_cache()
            elif self._device.startswith("cuda"):
                torch.cuda.empty_cache()
        except Exception:
            log.debug("Could not empty %s cache", self._device, exc_info=True)

    def release_cached_memory(self, min_slack_bytes: int = CACHE_SLACK_RELEASE_BYTES) -> int:
        """Drop cached-but-unused GPU buffers once the slack is worth reclaiming.

        Costs ~35ms here plus ~40ms of cache rebuild on the next transcribe, so
        callers should only invoke it when no work is queued. Transcription in
        this app runs well ahead of real time, so that is a trade worth making.
        """
        with self._lock:
            return self._release_locked(min_slack_bytes)

    def _release_locked(self, min_slack_bytes: int) -> int:
        import torch

        # The two allocators report the same two numbers under different names.
        if self._device == "mps":
            module = torch.mps
            reserved, in_use = module.driver_allocated_memory, module.current_allocated_memory
        elif self._device.startswith("cuda"):
            module = torch.cuda
            reserved, in_use = module.memory_reserved, module.memory_allocated
        else:
            return 0  # CPU tensors go straight back to the allocator

        try:
            slack = reserved() - in_use()
            if slack < min_slack_bytes:
                return 0
            module.empty_cache()
            freed = max(slack - (reserved() - in_use()), 0)
            # Freeing nothing is normal, not a failure: a freshly loaded model
            # already shows ~330MB of slack on MPS that is internal
            # fragmentation the allocator cannot hand back. Only the cache built
            # up by varying utterance shapes is actually reclaimable.
            if freed:
                log.info("Released %.0fMB of cached %s memory", freed / 1e6, self._device)
            else:
                log.debug("No reclaimable %s cache (slack %.0fMB is not releasable)", self._device, slack / 1e6)
            return freed
        except Exception:
            log.debug("Could not release cached %s memory", self._device, exc_info=True)
            return 0


@dataclass
class QwenAsrCliBackend(ASRBackend):
    config: ModelConfig

    def __post_init__(self) -> None:
        self._binary_path: Path | None = None
        self._model_dir: Path | None = None

    def load_model(self) -> None:
        binary_path = Path(self.config.binary_path).expanduser()
        model_dir = Path(self.config.path_or_id).expanduser()
        if not binary_path.exists():
            raise RuntimeError(
                f"Lightweight backend binary not found: {binary_path}. "
                "Build antirez/qwen-asr first or update model.binary_path."
            )
        if not model_dir.exists():
            raise RuntimeError(
                f"Lightweight backend model directory not found: {model_dir}. "
                "Download the qwen-asr model files first or update model.path_or_id."
            )
        self._binary_path = binary_path
        self._model_dir = model_dir
        log.info(
            "Using lightweight ASR backend %s (variant=%s) via %s",
            self._model_dir,
            self.config.variant or "custom",
            self._binary_path,
        )

    def transcribe(self, audio_16k: np.ndarray, language: str | None) -> str:
        if self._binary_path is None or self._model_dir is None:
            raise RuntimeError("Lightweight backend has not been prepared")

        temp_root = _ensure_runtime_temp_dir()
        audio_path = temp_root / f"s2t-qwen-asr-{uuid.uuid4().hex}.wav"
        try:
            _write_pcm16_wav(audio_path, audio_16k)
            command = [
                str(self._binary_path),
                "-d",
                str(self._model_dir),
                "-i",
                str(audio_path),
                "--silent",
            ]
            if language:
                command.extend(["--language", language])

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                log.debug("Could not delete temporary audio file %s", audio_path, exc_info=True)

        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise RuntimeError(stderr or f"Lightweight backend exited with code {completed.returncode}")

        return completed.stdout.strip()


def build_backend(config: ModelConfig) -> ASRBackend:
    if config.provider == "qwen3_asr":
        return Qwen3ASRBackend(config=config)
    if config.provider == "qwen_asr_cli":
        return QwenAsrCliBackend(config=config)
    raise ValueError(f"Unsupported model provider: {config.provider}")


def _resolve_device(device_preference: str) -> str:
    import torch

    if device_preference == "cpu":
        return "cpu"
    if device_preference == "gpu":
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda:0"
        raise RuntimeError("GPU device requested but neither MPS nor CUDA is available")
    # auto
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def _resolve_dtype(device: str):
    """Pick the load dtype for `device`, preferring the checkpoint's own.

    The Qwen3-ASR checkpoints are stored in bfloat16. Requesting float16 makes
    transformers convert the whole model, so the original and the cast copy are
    both resident during load — measured at ~2.1GB of extra peak RSS for the
    0.6B model, versus ~0.2GB when bfloat16 is loaded as-is, with identical warm
    transcribe latency. MPS only has bfloat16 kernels on macOS 14+, so older
    systems keep the float16 path; CPU has no fast half support either way.
    """
    import torch

    if device == "cpu":
        return torch.float32
    if device == "mps" and not torch.backends.mps.is_macos_or_newer(14, 0):
        log.info("macOS < 14 has no MPS bfloat16 support; loading in float16")
        return torch.float16
    return torch.bfloat16


def _pad_to_bucket(audio_16k: np.ndarray, step: int = SHAPE_BUCKET_SAMPLES) -> np.ndarray:
    """Zero-pad to the next multiple of `step` samples (see SHAPE_BUCKET_SAMPLES)."""
    audio = np.asarray(audio_16k, dtype=np.float32).reshape(-1)
    target = -(-audio.size // step) * step
    if target == audio.size:
        return audio
    return np.pad(audio, (0, target - audio.size))


def _write_pcm16_wav(path: Path, audio_16k: np.ndarray) -> None:
    audio = np.asarray(audio_16k, dtype=np.float32)
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm16.tobytes())


def _ensure_runtime_temp_dir() -> Path:
    candidates = [runtime_temp_dir(), Path.cwd() / "runtime-temp"]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except PermissionError:
            continue
    raise RuntimeError("Could not create a writable runtime temp directory")

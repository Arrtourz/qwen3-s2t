from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import subprocess
import uuid
import wave

import numpy as np
import torch

from qwen_asr import Qwen3ASRModel

from .config import ModelConfig, runtime_temp_dir


SAMPLE_RATE = 16000

log = logging.getLogger(__name__)


class ASRBackend:
    def load_model(self) -> None:
        raise NotImplementedError

    def transcribe(self, audio_16k: np.ndarray, language: str | None) -> str:
        raise NotImplementedError


@dataclass
class Qwen3ASRBackend(ASRBackend):
    config: ModelConfig

    def __post_init__(self) -> None:
        self._model: Qwen3ASRModel | None = None

    def load_model(self) -> None:
        if self._model is not None:
            return

        device = _resolve_device(self.config.device)
        dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
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
        if self._model is None:
            raise RuntimeError("ASR model has not been loaded")

        results = self._model.transcribe(audio=(audio_16k, SAMPLE_RATE), language=language)
        if not results:
            return ""
        return results[0].text.strip()


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
            "Using lightweight ASR backend %s (variant=%s) via %s on cpu",
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

            env = os.environ.copy()
            env["PATH"] = os.pathsep.join(_lightweight_backend_path_entries(self._binary_path, env.get("PATH", "")))
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                env=env,
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
    if device_preference == "cpu":
        return "cpu"
    if device_preference == "gpu":
        if not torch.cuda.is_available():
            raise RuntimeError("GPU device requested but CUDA is not available")
        return "cuda:0"
    return "cuda:0" if torch.cuda.is_available() else "cpu"


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


def _lightweight_backend_path_entries(binary_path: Path, existing_path: str) -> list[str]:
    entries: list[str] = []
    binary_dir = str(binary_path.parent)
    if binary_dir:
        entries.append(binary_dir)

    msys_ucrt_bin = Path("C:/msys64/ucrt64/bin")
    if msys_ucrt_bin.exists():
        entries.append(str(msys_ucrt_bin))

    if existing_path:
        entries.append(existing_path)
    return entries

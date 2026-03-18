from __future__ import annotations

from dataclasses import dataclass
import logging

import numpy as np
import torch

from qwen_asr import Qwen3ASRModel

from .config import ModelConfig


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


def build_backend(config: ModelConfig) -> ASRBackend:
    if config.provider != "qwen3_asr":
        raise ValueError(f"Unsupported model provider: {config.provider}")
    return Qwen3ASRBackend(config=config)


def _resolve_device(device_preference: str) -> str:
    if device_preference == "cpu":
        return "cpu"
    if device_preference == "gpu":
        if not torch.cuda.is_available():
            raise RuntimeError("GPU device requested but CUDA is not available")
        return "cuda:0"
    return "cuda:0" if torch.cuda.is_available() else "cpu"

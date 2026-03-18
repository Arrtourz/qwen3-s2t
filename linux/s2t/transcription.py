"""Qwen3-ASR transcription backend."""

import logging
import os

import numpy as np
import torch
from qwen_asr import Qwen3ASRModel

from .config import DEFAULT_MODEL_ID, ModelConfig, infer_model_variant

log = logging.getLogger("s2t")

HF_TOKEN = os.environ.get("HF_TOKEN", "")
SAMPLE_RATE = 16000

_model: Qwen3ASRModel = None
_model_config: ModelConfig = ModelConfig()


def load_model(config: ModelConfig | None = None):
    global _model, _model_config
    if _model is not None and config == _model_config:
        return

    resolved = config if config is not None else _default_model_config()
    _model_config = resolved
    if HF_TOKEN:
        from huggingface_hub import login

        login(token=HF_TOKEN, add_to_git_credential=False)
    device = _resolve_device(resolved.device)
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    log.info(
        "Loading Qwen3-ASR model: %s (variant=%s, device=%s)",
        resolved.path_or_id,
        resolved.variant or "custom",
        device,
    )
    _model = Qwen3ASRModel.from_pretrained(
        resolved.path_or_id,
        dtype=dtype,
        device_map=device,
        max_new_tokens=256,
    )
    log.info("Model loaded.")


def transcribe(audio_16k: np.ndarray, language: str = None) -> str:
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")
    results = _model.transcribe(
        audio=(audio_16k, SAMPLE_RATE),
        language=language,
    )
    if results:
        return results[0].text.strip()
    return ""


def _resolve_device(device_preference: str) -> str:
    if device_preference == "cpu":
        return "cpu"
    if device_preference == "gpu":
        if not torch.cuda.is_available():
            raise RuntimeError("GPU device requested but CUDA is not available")
        return "cuda:0"
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def _default_model_config() -> ModelConfig:
    model_id = os.environ.get("QWEN3_ASR_MODEL", "").strip() or DEFAULT_MODEL_ID
    device = os.environ.get("S2T_DEVICE", "").strip().lower() or "auto"
    if device not in {"auto", "cpu", "gpu"}:
        raise RuntimeError("S2T_DEVICE must be 'auto', 'cpu', or 'gpu'")
    return ModelConfig(
        variant=infer_model_variant(model_id),
        path_or_id=model_id,
        device=device,
    )

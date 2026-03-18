"""Qwen3-ASR-1.7B transcription backend."""

import os

import numpy as np
import torch
from qwen_asr import Qwen3ASRModel

MODEL_PATH = os.environ.get("QWEN3_ASR_MODEL", "Qwen/Qwen3-ASR-1.7B")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
SAMPLE_RATE = 16000

_model: Qwen3ASRModel = None


def load_model():
    global _model
    print(f"Loading Qwen3-ASR model: {MODEL_PATH}")
    if HF_TOKEN:
        from huggingface_hub import login

        login(token=HF_TOKEN, add_to_git_credential=False)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    _model = Qwen3ASRModel.from_pretrained(
        MODEL_PATH,
        dtype=dtype,
        device_map=device,
        max_new_tokens=256,
    )
    print("Model loaded.")


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

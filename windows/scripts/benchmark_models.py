from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from s2t.core.backend import Qwen3ASRBackend
from s2t.core.config import ModelConfig


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Qwen3-ASR models on local audio")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-1.7B"],
        help="One or more HuggingFace model ids to benchmark",
    )
    parser.add_argument(
        "--audio",
        required=True,
        help="Path to a local wav/flac audio file used for transcription timing",
    )
    parser.add_argument(
        "--language",
        default="Chinese",
        help="Language hint passed to the model",
    )
    return parser


def load_audio(audio_path: Path) -> np.ndarray:
    audio, sample_rate = sf.read(audio_path, dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    if sample_rate != 16000:
        import librosa

        audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
    return np.asarray(audio, dtype=np.float32)


def benchmark_model(model_id: str, audio_16k: np.ndarray, language: str) -> dict[str, object]:
    config = ModelConfig(provider="qwen3_asr", path_or_id=model_id)
    backend = Qwen3ASRBackend(config=config)

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    load_started = time.perf_counter()
    backend.load_model()
    load_seconds = time.perf_counter() - load_started

    transcribe_started = time.perf_counter()
    text = backend.transcribe(audio_16k, language=language)
    first_transcribe_seconds = time.perf_counter() - transcribe_started

    gpu_peak_mb = None
    if torch.cuda.is_available():
        gpu_peak_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

    return {
        "model": model_id,
        "load_seconds": round(load_seconds, 3),
        "first_transcribe_seconds": round(first_transcribe_seconds, 3),
        "gpu_peak_memory_mb": round(gpu_peak_mb, 1) if gpu_peak_mb is not None else None,
        "text_preview": text[:120],
    }


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    audio_path = Path(args.audio).expanduser().resolve()
    audio_16k = load_audio(audio_path)

    results = [
        benchmark_model(model_id=model_id, audio_16k=audio_16k, language=args.language)
        for model_id in args.models
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

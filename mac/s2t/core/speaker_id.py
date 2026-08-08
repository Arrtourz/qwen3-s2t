from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np


log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# Transformer-based speaker-verification model (Microsoft WavLM fine-tuned with
# an X-Vector head). Outputs a 512-d embedding; cosine similarity between two
# embeddings measures whether they are the same speaker. No HF token required.
DEFAULT_MODEL_ID = "microsoft/wavlm-base-plus-sv"


class SpeakerVerifier:
    """Verifies whether an audio segment matches an enrolled voice profile.

    Enrollment stores the mean embedding of a few reference clips. At runtime a
    segment's embedding is compared to the profile by cosine similarity; scores
    at/above ``threshold`` are accepted as the enrolled speaker.
    """

    def __init__(self, model_id: str = DEFAULT_MODEL_ID, device: str | None = None) -> None:
        self.model_id = model_id
        self._device = device
        self._model = None
        self._extractor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector

        device = self._device or _resolve_device()
        log.info("Loading speaker-verification model %s on %s", self.model_id, device)
        self._extractor = Wav2Vec2FeatureExtractor.from_pretrained(self.model_id)
        self._model = WavLMForXVector.from_pretrained(self.model_id).to(device)
        self._model.eval()
        self._torch_device = device

    def embed(self, audio_16k: np.ndarray) -> np.ndarray:
        """Return a unit-normalized speaker embedding for a mono 16k segment."""
        import torch

        self._ensure_loaded()
        audio = np.asarray(audio_16k, dtype=np.float32).reshape(-1)
        inputs = self._extractor(
            audio, sampling_rate=SAMPLE_RATE, return_tensors="pt", padding=True
        )
        inputs = {k: v.to(self._torch_device) for k, v in inputs.items()}
        with torch.no_grad():
            emb = self._model(**inputs).embeddings
        emb = torch.nn.functional.normalize(emb, dim=-1)
        return emb.squeeze(0).cpu().numpy().astype(np.float32)

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a, dtype=np.float32).reshape(-1)
        b = np.asarray(b, dtype=np.float32).reshape(-1)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            return 0.0
        return float(np.dot(a, b) / denom)


class VoiceProfile:
    """Persisted enrolled voiceprint: a single mean embedding on disk (JSON)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._embedding: np.ndarray | None = None

    @property
    def enrolled(self) -> bool:
        return self.load() is not None

    def load(self) -> np.ndarray | None:
        if self._embedding is not None:
            return self._embedding
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._embedding = np.asarray(data["embedding"], dtype=np.float32)
            return self._embedding
        except Exception:
            log.exception("Failed to load voice profile from %s", self.path)
            return None

    def save(self, embedding: np.ndarray) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"embedding": np.asarray(embedding, dtype=np.float32).tolist()}
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        self._embedding = np.asarray(embedding, dtype=np.float32)
        log.info("Saved voice profile to %s", self.path)

    def clear(self) -> None:
        self._embedding = None
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            log.debug("Could not delete voice profile", exc_info=True)


def _resolve_device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"

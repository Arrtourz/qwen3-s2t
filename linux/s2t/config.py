from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


APP_DIR_NAME = "s2t"
DEFAULT_HOTKEY = "double_ctrl"
DEFAULT_RECORDING_MODE = "continuous"
MODEL_VARIANTS = {
    "0.6b": "Qwen/Qwen3-ASR-0.6B",
    "1.7b": "Qwen/Qwen3-ASR-1.7B",
}
DEFAULT_MODEL_VARIANT = "0.6b"
DEFAULT_MODEL_ID = MODEL_VARIANTS[DEFAULT_MODEL_VARIANT]


class ConfigError(ValueError):
    """Raised when the config file is invalid."""


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "qwen3_asr"
    variant: str = DEFAULT_MODEL_VARIANT
    path_or_id: str = DEFAULT_MODEL_ID
    device: str = "auto"


@dataclass(frozen=True)
class RecordingConfig:
    mode: str = DEFAULT_RECORDING_MODE
    sample_rate: int = 16000
    channels: int = 1
    continuous_window_seconds: int = 60


@dataclass(frozen=True)
class AppConfig:
    hotkey: str = DEFAULT_HOTKEY
    language: str = "Chinese"
    model: ModelConfig = ModelConfig()
    recording: RecordingConfig = RecordingConfig()


def app_config_dir() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg_config_home:
        return Path(xdg_config_home) / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME


def default_config_path() -> Path:
    return app_config_dir() / "config.toml"


def ensure_config(path: Path | None = None) -> Path:
    config_path = path if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(_default_config_text(), encoding="utf-8")
    return config_path


def load_config(path: Path | None = None) -> AppConfig:
    config_path = ensure_config(path)
    raw = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    return _parse_config(raw)


def resolve_model_variant(variant: str) -> str:
    normalized = variant.strip().lower()
    if normalized not in MODEL_VARIANTS:
        raise ConfigError("model.variant must be '0.6b' or '1.7b'")
    return MODEL_VARIANTS[normalized]


def infer_model_variant(path_or_id: str) -> str:
    reverse_map = {value: key for key, value in MODEL_VARIANTS.items()}
    return reverse_map.get(path_or_id.strip(), "")


def _default_config_text() -> str:
    return f"""hotkey = "{DEFAULT_HOTKEY}"
language = "Chinese"

[model]
provider = "qwen3_asr"
variant = "{DEFAULT_MODEL_VARIANT}"
path_or_id = "{DEFAULT_MODEL_ID}"
device = "auto"

[recording]
mode = "{DEFAULT_RECORDING_MODE}"
sample_rate = 16000
channels = 1
continuous_window_seconds = 60
"""


def _parse_config(raw: dict) -> AppConfig:
    hotkey = str(raw.get("hotkey", DEFAULT_HOTKEY)).strip() or DEFAULT_HOTKEY
    language = str(raw.get("language", "Chinese")).strip() or "Chinese"

    model_raw = raw.get("model", {})
    model = ModelConfig(
        provider=str(model_raw.get("provider", "qwen3_asr")).strip().lower(),
        variant=str(model_raw.get("variant", DEFAULT_MODEL_VARIANT)).strip().lower(),
        path_or_id=str(model_raw.get("path_or_id", DEFAULT_MODEL_ID)).strip(),
        device=str(model_raw.get("device", "auto")).strip().lower(),
    )
    model = _normalize_model_config(model)

    recording_raw = raw.get("recording", {})
    recording = RecordingConfig(
        mode=str(recording_raw.get("mode", DEFAULT_RECORDING_MODE)).strip().lower(),
        sample_rate=int(recording_raw.get("sample_rate", 16000)),
        channels=int(recording_raw.get("channels", 1)),
        continuous_window_seconds=int(recording_raw.get("continuous_window_seconds", 60)),
    )
    if recording.mode not in {"manual", "continuous"}:
        raise ConfigError("recording.mode must be 'manual' or 'continuous'")
    if recording.sample_rate <= 0:
        raise ConfigError("recording.sample_rate must be positive")
    if recording.channels != 1:
        raise ConfigError("recording.channels must be 1 for mono input")
    if recording.continuous_window_seconds <= 0:
        raise ConfigError("recording.continuous_window_seconds must be positive")

    return AppConfig(
        hotkey=hotkey,
        language=language,
        model=model,
        recording=recording,
    )


def _normalize_model_config(model: ModelConfig) -> ModelConfig:
    if model.provider != "qwen3_asr":
        raise ConfigError("model.provider must be 'qwen3_asr'")

    variant = model.variant.strip().lower()
    path_or_id = model.path_or_id.strip()

    if variant:
        resolved = resolve_model_variant(variant)
        if path_or_id and path_or_id != resolved:
            raise ConfigError("model.path_or_id does not match model.variant")
        path_or_id = resolved
    else:
        variant = infer_model_variant(path_or_id)

    if not path_or_id:
        raise ConfigError("model.path_or_id must be a non-empty string")
    if model.device not in {"auto", "cpu", "gpu"}:
        raise ConfigError("model.device must be 'auto', 'cpu', or 'gpu'")

    return ModelConfig(
        provider=model.provider,
        variant=variant,
        path_or_id=path_or_id,
        device=model.device,
    )

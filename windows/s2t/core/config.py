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
DEFAULT_MODEL_ID = "Qwen/Qwen3-ASR-0.6B"
LEGACY_MODEL_ID = "Qwen/Qwen3-ASR-1.7B"
LEGACY_DEFAULT_HOTKEY = "ctrl+alt+h"


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
    block_duration_ms: int = 100


@dataclass(frozen=True)
class PasteConfig:
    multiline_strategy: str = "line_by_line"
    settle_delay_ms: int = 50
    line_delay_ms: int = 30


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(frozen=True)
class AppConfig:
    hotkey: str
    language: str
    model: ModelConfig
    recording: RecordingConfig
    paste: PasteConfig
    logging: LoggingConfig


def app_data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME
    return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME


def default_config_path() -> Path:
    return app_data_dir() / "config.toml"


def default_log_file() -> Path:
    return app_data_dir() / "logs" / "s2t.log"


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
block_duration_ms = 100

[paste]
multiline_strategy = "line_by_line"
settle_delay_ms = 50
line_delay_ms = 30

[logging]
level = "INFO"
"""


def _legacy_default_config_text(*, hotkey: str, mode: str, model_id: str) -> str:
    return f"""hotkey = "{hotkey}"
language = "Chinese"

[model]
provider = "qwen3_asr"
path_or_id = "{model_id}"

[recording]
mode = "{mode}"
sample_rate = 16000
channels = 1
continuous_window_seconds = 60
block_duration_ms = 100

[paste]
multiline_strategy = "line_by_line"
settle_delay_ms = 50
line_delay_ms = 30

[logging]
level = "INFO"
"""


def ensure_config(path: Path | None = None) -> Path:
    config_path = path if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(_default_config_text(), encoding="utf-8")
    else:
        current_text = config_path.read_text(encoding="utf-8-sig")
        migratable_texts = {
            _default_config_text(),
            _default_config_text().replace(DEFAULT_HOTKEY, LEGACY_DEFAULT_HOTKEY, 1),
            _default_config_text().replace(DEFAULT_RECORDING_MODE, "manual", 1),
            _default_config_text()
            .replace(DEFAULT_RECORDING_MODE, "manual", 1)
            .replace(DEFAULT_HOTKEY, LEGACY_DEFAULT_HOTKEY, 1),
            _default_config_text().replace(DEFAULT_MODEL_ID, LEGACY_MODEL_ID, 1).replace(
                DEFAULT_MODEL_VARIANT, "1.7b", 1
            ),
            _default_config_text()
            .replace(DEFAULT_MODEL_ID, LEGACY_MODEL_ID, 1)
            .replace(DEFAULT_MODEL_VARIANT, "1.7b", 1)
            .replace(DEFAULT_HOTKEY, LEGACY_DEFAULT_HOTKEY, 1),
            _default_config_text()
            .replace(DEFAULT_MODEL_ID, LEGACY_MODEL_ID, 1)
            .replace(DEFAULT_MODEL_VARIANT, "1.7b", 1)
            .replace(DEFAULT_RECORDING_MODE, "manual", 1),
            _default_config_text()
            .replace(DEFAULT_MODEL_ID, LEGACY_MODEL_ID, 1)
            .replace(DEFAULT_MODEL_VARIANT, "1.7b", 1)
            .replace(DEFAULT_RECORDING_MODE, "manual", 1)
            .replace(DEFAULT_HOTKEY, LEGACY_DEFAULT_HOTKEY, 1),
            _legacy_default_config_text(
                hotkey=LEGACY_DEFAULT_HOTKEY,
                mode="manual",
                model_id=LEGACY_MODEL_ID,
            ),
            _legacy_default_config_text(
                hotkey=DEFAULT_HOTKEY,
                mode="manual",
                model_id=LEGACY_MODEL_ID,
            ),
            _legacy_default_config_text(
                hotkey=LEGACY_DEFAULT_HOTKEY,
                mode=DEFAULT_RECORDING_MODE,
                model_id=LEGACY_MODEL_ID,
            ),
            _legacy_default_config_text(
                hotkey=DEFAULT_HOTKEY,
                mode=DEFAULT_RECORDING_MODE,
                model_id=LEGACY_MODEL_ID,
            ),
        }
        if current_text in migratable_texts:
            config_path.write_text(_default_config_text(), encoding="utf-8")
    return config_path


def load_config(path: Path | None = None) -> AppConfig:
    config_path = ensure_config(path)
    raw = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    return _parse_config(raw)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    config_path = path if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _parse_config(
        {
            "hotkey": config.hotkey,
            "language": config.language,
            "model": {
                "provider": config.model.provider,
                "variant": config.model.variant,
                "path_or_id": config.model.path_or_id,
                "device": config.model.device,
            },
            "recording": {
                "mode": config.recording.mode,
                "sample_rate": config.recording.sample_rate,
                "channels": config.recording.channels,
                "continuous_window_seconds": config.recording.continuous_window_seconds,
                "block_duration_ms": config.recording.block_duration_ms,
            },
            "paste": {
                "multiline_strategy": config.paste.multiline_strategy,
                "settle_delay_ms": config.paste.settle_delay_ms,
                "line_delay_ms": config.paste.line_delay_ms,
            },
            "logging": {
                "level": config.logging.level,
            },
        }
    )
    config_path.write_text(_config_to_toml(normalized), encoding="utf-8")
    return config_path


def _parse_config(raw: dict) -> AppConfig:
    hotkey = str(raw.get("hotkey", "")).strip()
    language = str(raw.get("language", "Chinese")).strip() or "Chinese"
    if not hotkey:
        raise ConfigError("hotkey must be a non-empty string")

    model_raw = raw.get("model", {})
    recording_raw = raw.get("recording", {})
    paste_raw = raw.get("paste", {})
    logging_raw = raw.get("logging", {})

    model = ModelConfig(
        provider=str(model_raw.get("provider", "qwen3_asr")).strip().lower(),
        variant=str(model_raw.get("variant", "")).strip().lower(),
        path_or_id=str(model_raw.get("path_or_id", DEFAULT_MODEL_ID)).strip(),
        device=str(model_raw.get("device", "auto")).strip().lower(),
    )
    if model.provider != "qwen3_asr":
        raise ConfigError("model.provider must be 'qwen3_asr'")
    model = _normalize_model_config(model)

    recording = RecordingConfig(
        mode=str(recording_raw.get("mode", DEFAULT_RECORDING_MODE)).strip().lower(),
        sample_rate=int(recording_raw.get("sample_rate", 16000)),
        channels=int(recording_raw.get("channels", 1)),
        continuous_window_seconds=int(recording_raw.get("continuous_window_seconds", 60)),
        block_duration_ms=int(recording_raw.get("block_duration_ms", 100)),
    )
    if recording.mode not in {"manual", "continuous"}:
        raise ConfigError("recording.mode must be 'manual' or 'continuous'")
    if recording.sample_rate <= 0:
        raise ConfigError("recording.sample_rate must be positive")
    if recording.channels != 1:
        raise ConfigError("recording.channels must be 1 for mono input")
    if recording.continuous_window_seconds <= 0:
        raise ConfigError("recording.continuous_window_seconds must be positive")
    if recording.block_duration_ms <= 0:
        raise ConfigError("recording.block_duration_ms must be positive")

    paste = PasteConfig(
        multiline_strategy=str(paste_raw.get("multiline_strategy", "line_by_line")).strip().lower(),
        settle_delay_ms=int(paste_raw.get("settle_delay_ms", 50)),
        line_delay_ms=int(paste_raw.get("line_delay_ms", 30)),
    )
    if paste.multiline_strategy not in {"line_by_line", "block"}:
        raise ConfigError("paste.multiline_strategy must be 'line_by_line' or 'block'")
    if paste.settle_delay_ms < 0:
        raise ConfigError("paste.settle_delay_ms must be >= 0")
    if paste.line_delay_ms < 0:
        raise ConfigError("paste.line_delay_ms must be >= 0")

    logging_cfg = LoggingConfig(level=str(logging_raw.get("level", "INFO")).strip().upper() or "INFO")

    return AppConfig(
        hotkey=hotkey,
        language=language,
        model=model,
        recording=recording,
        paste=paste,
        logging=logging_cfg,
    )


def resolve_model_variant(variant: str) -> str:
    normalized = variant.strip().lower()
    if normalized not in MODEL_VARIANTS:
        raise ConfigError("model.variant must be '0.6b' or '1.7b'")
    return MODEL_VARIANTS[normalized]


def _normalize_model_config(model: ModelConfig) -> ModelConfig:
    variant = model.variant.strip().lower()
    path_or_id = model.path_or_id.strip()
    if variant:
        resolved = resolve_model_variant(variant)
        if path_or_id and path_or_id != resolved:
            raise ConfigError("model.path_or_id does not match model.variant")
        path_or_id = resolved
    else:
        reverse_map = {value: key for key, value in MODEL_VARIANTS.items()}
        variant = reverse_map.get(path_or_id, "")

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


def _config_to_toml(config: AppConfig) -> str:
    return f"""hotkey = "{config.hotkey}"
language = "{config.language}"

[model]
provider = "{config.model.provider}"
variant = "{config.model.variant}"
path_or_id = "{config.model.path_or_id}"
device = "{config.model.device}"

[recording]
mode = "{config.recording.mode}"
sample_rate = {config.recording.sample_rate}
channels = {config.recording.channels}
continuous_window_seconds = {config.recording.continuous_window_seconds}
block_duration_ms = {config.recording.block_duration_ms}

[paste]
multiline_strategy = "{config.paste.multiline_strategy}"
settle_delay_ms = {config.paste.settle_delay_ms}
line_delay_ms = {config.paste.line_delay_ms}

[logging]
level = "{config.logging.level}"
"""

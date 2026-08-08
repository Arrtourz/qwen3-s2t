from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


APP_DIR_NAME = "s2t"
DEFAULT_HOTKEY = "ctrl+alt+h"
DEFAULT_RECORDING_MODE = "continuous"
MODEL_PROVIDERS = {
    "qwen3_asr",
    "qwen_asr_cli",
}
MODEL_VARIANTS = {
    "0.6b": "Qwen/Qwen3-ASR-0.6B",
    "1.7b": "Qwen/Qwen3-ASR-1.7B",
}
DEFAULT_MODEL_VARIANT = "0.6b"
DEFAULT_MODEL_ID = "Qwen/Qwen3-ASR-0.6B"
LEGACY_MODEL_ID = "Qwen/Qwen3-ASR-1.7B"


class ConfigError(ValueError):
    """Raised when the config file is invalid."""


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "qwen3_asr"
    variant: str = DEFAULT_MODEL_VARIANT
    path_or_id: str = DEFAULT_MODEL_ID
    device: str = "auto"
    binary_path: str = ""


@dataclass(frozen=True)
class RecordingConfig:
    mode: str = DEFAULT_RECORDING_MODE
    sample_rate: int = 16000
    channels: int = 1
    continuous_window_seconds: int = 60
    block_duration_ms: int = 100
    # Name of the sounddevice input device, empty string = default mic
    input_device: str = ""


@dataclass(frozen=True)
class PasteConfig:
    multiline_strategy: str = "block"
    settle_delay_ms: int = 60
    line_delay_ms: int = 30


@dataclass(frozen=True)
class MeetingConfig:
    # mic_device: empty = system default input (auto-follows AirPods/built-in).
    mic_device: str = ""
    # How to capture the other party's audio:
    #   "tap"    = Core Audio system tap (default; no output-device change, auto-follows)
    #   "device" = read from system_device by name (e.g. a BlackHole loopback)
    #   "off"    = mic only
    system_source: str = "tap"
    system_device: str = ""
    mic_label: str = "\U0001f3a4 Me"
    system_label: str = "\U0001f50a Them"
    # Silence-based segmentation tuning (latency is not a concern here).
    silence_rms: float = 0.008
    silence_hold_ms: int = 800
    min_segment_ms: int = 400
    max_segment_seconds: float = 20.0
    # Frame-based voice-activity gate before transcription (standard VAD). The
    # segment is split into 20ms frames; a frame is "voiced" if its RMS >=
    # voice_frame_rms AND its zero-crossing rate < voice_max_zcr. The segment is
    # transcribed only if at least voice_min_voiced_ratio of frames are voiced.
    #   voice_frame_rms: per-frame loudness floor — raise to reject faint/distant
    #     voices, lower if your own speech is dropped (direct-to-mic ~0.06-0.13).
    #   voice_min_voiced_ratio: fraction of voiced frames required (0.30 = 30%).
    #   voice_max_zcr: upper zero-crossing rate for "voiced" (hiss ~0.5).
    voice_frame_rms: float = 0.045
    voice_max_zcr: float = 0.32
    voice_min_voiced_ratio: float = 0.30
    # Speaker verification (WavLM voiceprint). When enabled AND a voice profile
    # has been enrolled, the mic ("Me") stream keeps a segment only if its
    # speaker embedding matches the enrolled profile with cosine similarity >=
    # speaker_threshold. This filters out colleagues/others captured by the mic.
    # Only applies to the mic stream — the system-tap ("Them") stream is never
    # speaker-filtered. Disabled by default (needs enrollment first).
    speaker_filter: bool = False
    speaker_threshold: float = 0.55


@dataclass(frozen=True)
class TranscriptConfig:
    enabled: bool = True
    output_dir: str = ""
    filename_prefix: str = "meeting"


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
    transcript: TranscriptConfig
    meeting: MeetingConfig
    logging: LoggingConfig


def app_data_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    override = os.environ.get("S2T_CONFIG_PATH", "").strip()
    if override:
        return Path(override).parent
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME


def default_config_path() -> Path:
    override = os.environ.get("S2T_CONFIG_PATH", "").strip()
    if override:
        return Path(override)
    return app_data_dir() / "config.toml"


def default_log_file() -> Path:
    return app_data_dir() / "logs" / "s2t.log"


def default_transcript_dir() -> Path:
    return Path.home() / "Documents" / "s2t-transcripts"


def runtime_temp_dir() -> Path:
    return app_data_dir() / "tmp"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_lightweight_binary_path() -> Path:
    return repo_root() / "third_party" / "qwen-asr" / "qwen_asr"


def default_lightweight_model_dir(variant: str = DEFAULT_MODEL_VARIANT) -> Path:
    return repo_root() / "third_party" / "qwen-asr" / f"qwen3-asr-{variant.strip().lower()}"


def _default_config_text() -> str:
    return f"""# s2t config — edit this file, then choose "Reload Config" from the menu.
# language: transcription language, e.g. "Chinese" or "English"
# [meeting] mic_device: "" = default mic; or a device name from your system
# [meeting] system_source: "tap" = capture system audio (Zoom/other party),
#   "off" = my mic only, "device" = read from system_device by name
# [transcript] output_dir: "" = ~/Documents/s2t-transcripts

hotkey = "none"
language = "Chinese"

[model]
provider = "qwen3_asr"
variant = "{DEFAULT_MODEL_VARIANT}"
path_or_id = "{DEFAULT_MODEL_ID}"
device = "auto"
binary_path = ""

[recording]
mode = "{DEFAULT_RECORDING_MODE}"
sample_rate = 16000
channels = 1
continuous_window_seconds = 60
block_duration_ms = 100
input_device = ""

[paste]
multiline_strategy = "block"
settle_delay_ms = 60
line_delay_ms = 30

[transcript]
enabled = true
output_dir = ""
filename_prefix = "meeting"

[meeting]
mic_device = ""
system_source = "tap"
system_device = ""
mic_label = "\U0001f3a4 Me"
system_label = "\U0001f50a Them"
silence_rms = 0.008
silence_hold_ms = 800
min_segment_ms = 400
max_segment_seconds = 20.0
voice_frame_rms = 0.045
voice_max_zcr = 0.32
voice_min_voiced_ratio = 0.30
speaker_filter = false
speaker_threshold = 0.55

[logging]
level = "INFO"
"""


def ensure_config(path: Path | None = None) -> Path:
    config_path = path if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(_default_config_text(), encoding="utf-8")
    return config_path


def load_config(path: Path | None = None) -> AppConfig:
    config_path = ensure_config(path)
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return _parse_config(raw)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    config_path = path if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_config_to_toml(config), encoding="utf-8")
    return config_path


def _parse_config(raw: dict) -> AppConfig:
    # Empty/"none" hotkey = menu-only control (the hotkey is optional).
    hotkey = str(raw.get("hotkey", DEFAULT_HOTKEY)).strip() or "none"
    language = str(raw.get("language", "Chinese")).strip() or "Chinese"

    model_raw = raw.get("model", {})
    recording_raw = raw.get("recording", {})
    paste_raw = raw.get("paste", {})
    transcript_raw = raw.get("transcript", {})
    meeting_raw = raw.get("meeting", {})
    logging_raw = raw.get("logging", {})

    model = ModelConfig(
        provider=str(model_raw.get("provider", "qwen3_asr")).strip().lower(),
        variant=str(model_raw.get("variant", "")).strip().lower(),
        path_or_id=str(model_raw.get("path_or_id", DEFAULT_MODEL_ID)).strip(),
        device=str(model_raw.get("device", "auto")).strip().lower(),
        binary_path=str(model_raw.get("binary_path", "")).strip(),
    )
    model = normalize_model_config(model)

    recording = RecordingConfig(
        mode=str(recording_raw.get("mode", DEFAULT_RECORDING_MODE)).strip().lower(),
        sample_rate=int(recording_raw.get("sample_rate", 16000)),
        channels=int(recording_raw.get("channels", 1)),
        continuous_window_seconds=int(recording_raw.get("continuous_window_seconds", 60)),
        block_duration_ms=int(recording_raw.get("block_duration_ms", 100)),
        input_device=str(recording_raw.get("input_device", "")).strip(),
    )
    if recording.mode not in {"manual", "continuous"}:
        raise ConfigError("recording.mode must be 'manual' or 'continuous'")

    paste = PasteConfig(
        multiline_strategy=str(paste_raw.get("multiline_strategy", "block")).strip().lower(),
        settle_delay_ms=int(paste_raw.get("settle_delay_ms", 60)),
        line_delay_ms=int(paste_raw.get("line_delay_ms", 30)),
    )
    if paste.multiline_strategy not in {"line_by_line", "block"}:
        raise ConfigError("paste.multiline_strategy must be 'line_by_line' or 'block'")

    transcript = TranscriptConfig(
        enabled=bool(transcript_raw.get("enabled", True)),
        output_dir=str(transcript_raw.get("output_dir", "")).strip(),
        filename_prefix=str(transcript_raw.get("filename_prefix", "meeting")).strip(),
    )

    meeting = MeetingConfig(
        mic_device=str(meeting_raw.get("mic_device", "")).strip(),
        system_source=str(meeting_raw.get("system_source", "tap")).strip().lower() or "tap",
        system_device=str(meeting_raw.get("system_device", "")).strip(),
        mic_label=str(meeting_raw.get("mic_label", "\U0001f3a4 Me")).strip() or "\U0001f3a4 Me",
        system_label=str(meeting_raw.get("system_label", "\U0001f50a Them")).strip() or "\U0001f50a Them",
        silence_rms=float(meeting_raw.get("silence_rms", 0.008)),
        silence_hold_ms=int(meeting_raw.get("silence_hold_ms", 800)),
        min_segment_ms=int(meeting_raw.get("min_segment_ms", 400)),
        max_segment_seconds=float(meeting_raw.get("max_segment_seconds", 20.0)),
        voice_frame_rms=float(meeting_raw.get("voice_frame_rms", 0.045)),
        voice_max_zcr=float(meeting_raw.get("voice_max_zcr", 0.32)),
        voice_min_voiced_ratio=float(meeting_raw.get("voice_min_voiced_ratio", 0.30)),
        speaker_filter=bool(meeting_raw.get("speaker_filter", False)),
        speaker_threshold=float(meeting_raw.get("speaker_threshold", 0.55)),
    )
    if meeting.system_source not in {"tap", "device", "off"}:
        raise ConfigError("meeting.system_source must be 'tap', 'device', or 'off'")
    if meeting.silence_rms < 0:
        raise ConfigError("meeting.silence_rms must be >= 0")
    if meeting.silence_hold_ms <= 0:
        raise ConfigError("meeting.silence_hold_ms must be positive")
    if meeting.max_segment_seconds <= 0:
        raise ConfigError("meeting.max_segment_seconds must be positive")

    logging_cfg = LoggingConfig(
        level=str(logging_raw.get("level", "INFO")).strip().upper() or "INFO"
    )

    return AppConfig(
        hotkey=hotkey,
        language=language,
        model=model,
        recording=recording,
        paste=paste,
        transcript=transcript,
        meeting=meeting,
        logging=logging_cfg,
    )


def resolve_model_variant(variant: str) -> str:
    normalized = variant.strip().lower()
    if normalized not in MODEL_VARIANTS:
        raise ConfigError("model.variant must be '0.6b' or '1.7b'")
    return MODEL_VARIANTS[normalized]


def normalize_model_config(model: ModelConfig) -> ModelConfig:
    if model.provider not in MODEL_PROVIDERS:
        raise ConfigError("model.provider must be 'qwen3_asr' or 'qwen_asr_cli'")

    variant = model.variant.strip().lower()
    path_or_id = model.path_or_id.strip()
    binary_path = model.binary_path.strip()

    if model.provider == "qwen3_asr":
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
    else:
        if variant:
            resolve_model_variant(variant)
        else:
            variant = DEFAULT_MODEL_VARIANT
        if not path_or_id:
            path_or_id = str(default_lightweight_model_dir(variant))
        if not binary_path:
            binary_path = str(default_lightweight_binary_path())
        if model.device not in {"auto", "cpu"}:
            raise ConfigError("lightweight backend only supports model.device 'auto' or 'cpu'")

    return ModelConfig(
        provider=model.provider,
        variant=variant,
        path_or_id=path_or_id,
        device=model.device,
        binary_path=binary_path,
    )


def _config_to_toml(config: AppConfig) -> str:
    def _s(v: str) -> str:
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return f"""hotkey = {_s(config.hotkey)}
language = {_s(config.language)}

[model]
provider = {_s(config.model.provider)}
variant = {_s(config.model.variant)}
path_or_id = {_s(config.model.path_or_id)}
device = {_s(config.model.device)}
binary_path = {_s(config.model.binary_path)}

[recording]
mode = {_s(config.recording.mode)}
sample_rate = {config.recording.sample_rate}
channels = {config.recording.channels}
continuous_window_seconds = {config.recording.continuous_window_seconds}
block_duration_ms = {config.recording.block_duration_ms}
input_device = {_s(config.recording.input_device)}

[paste]
multiline_strategy = {_s(config.paste.multiline_strategy)}
settle_delay_ms = {config.paste.settle_delay_ms}
line_delay_ms = {config.paste.line_delay_ms}

[transcript]
enabled = {"true" if config.transcript.enabled else "false"}
output_dir = {_s(config.transcript.output_dir)}
filename_prefix = {_s(config.transcript.filename_prefix)}

[meeting]
mic_device = {_s(config.meeting.mic_device)}
system_source = {_s(config.meeting.system_source)}
system_device = {_s(config.meeting.system_device)}
mic_label = {_s(config.meeting.mic_label)}
system_label = {_s(config.meeting.system_label)}
silence_rms = {config.meeting.silence_rms}
silence_hold_ms = {config.meeting.silence_hold_ms}
min_segment_ms = {config.meeting.min_segment_ms}
max_segment_seconds = {config.meeting.max_segment_seconds}
voice_frame_rms = {config.meeting.voice_frame_rms}
voice_max_zcr = {config.meeting.voice_max_zcr}
voice_min_voiced_ratio = {config.meeting.voice_min_voiced_ratio}
speaker_filter = {"true" if config.meeting.speaker_filter else "false"}
speaker_threshold = {config.meeting.speaker_threshold}

[logging]
level = {_s(config.logging.level)}
"""

from __future__ import annotations

from pathlib import Path

import pytest

from s2t.core.config import (
    ConfigError,
    DEFAULT_HOTKEY,
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_VARIANT,
    DEFAULT_RECORDING_MODE,
    default_lightweight_binary_path,
    default_lightweight_model_dir,
    ensure_config,
    load_config,
)


def test_ensure_config_creates_default_file(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    created = ensure_config(config_path)
    assert created == config_path
    assert config_path.exists()

    config = load_config(config_path)
    assert config.hotkey == DEFAULT_HOTKEY
    assert config.recording.mode == DEFAULT_RECORDING_MODE
    assert config.model.variant == DEFAULT_MODEL_VARIANT
    assert config.model.path_or_id == DEFAULT_MODEL_ID
    assert config.model.device == "auto"
    assert config.paste.multiline_strategy == "line_by_line"


def test_ensure_config_migrates_legacy_default_hotkey(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "ctrl+alt+h"
language = "Chinese"

[model]
provider = "qwen3_asr"
path_or_id = "Qwen/Qwen3-ASR-1.7B"

[recording]
mode = "manual"
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
""",
        encoding="utf-8",
    )

    ensure_config(config_path)
    config = load_config(config_path)
    assert config.hotkey == DEFAULT_HOTKEY
    assert config.recording.mode == DEFAULT_RECORDING_MODE
    assert config.model.variant == DEFAULT_MODEL_VARIANT
    assert config.model.path_or_id == DEFAULT_MODEL_ID


def test_invalid_mode_raises_config_error(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "ctrl+alt+h"
language = "Chinese"

[model]
provider = "qwen3_asr"
variant = "1.7b"
path_or_id = "Qwen/Qwen3-ASR-1.7B"
device = "auto"

[recording]
mode = "broken"
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
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_load_config_accepts_utf8_bom(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "ctrl+alt+h"
language = "Chinese"

[model]
provider = "qwen3_asr"
variant = "1.7b"
path_or_id = "Qwen/Qwen3-ASR-1.7B"
device = "gpu"

[recording]
mode = "continuous"
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
""",
        encoding="utf-8-sig",
    )

    config = load_config(config_path)
    assert config.hotkey == "ctrl+alt+h"


def test_invalid_model_device_raises_config_error(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "ctrl+alt+h"
language = "Chinese"

[model]
provider = "qwen3_asr"
variant = "0.6b"
path_or_id = "Qwen/Qwen3-ASR-0.6B"
device = "tpu"

[recording]
mode = "continuous"
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
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_path)


def test_ensure_config_migrates_previous_generated_default_hotkey(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "double_ctrl"
language = "Chinese"

[model]
provider = "qwen3_asr"
variant = "0.6b"
path_or_id = "Qwen/Qwen3-ASR-0.6B"
device = "auto"

[recording]
mode = "continuous"
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
""",
        encoding="utf-8",
    )

    ensure_config(config_path)
    config = load_config(config_path)
    assert config.hotkey == DEFAULT_HOTKEY


def test_load_config_supports_lightweight_backend_defaults(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "ctrl+alt+h"
language = "Chinese"

[model]
provider = "qwen_asr_cli"
variant = "0.6b"
path_or_id = ""
device = "auto"
binary_path = ""

[recording]
mode = "continuous"
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
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    assert config.model.provider == "qwen_asr_cli"
    assert config.model.device == "auto"
    assert config.model.binary_path == str(default_lightweight_binary_path())
    assert config.model.path_or_id == str(default_lightweight_model_dir("0.6b"))


def test_lightweight_backend_rejects_gpu_device(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "ctrl+alt+h"
language = "Chinese"

[model]
provider = "qwen_asr_cli"
variant = "0.6b"
path_or_id = "C:/models/qwen3-asr-0.6b"
device = "gpu"
binary_path = "C:/bin/qwen_asr.exe"

[recording]
mode = "continuous"
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
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_path)

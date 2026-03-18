from __future__ import annotations

from pathlib import Path

import pytest

from s2t.core.config import (
    ConfigError,
    DEFAULT_HOTKEY,
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_VARIANT,
    DEFAULT_RECORDING_MODE,
    ensure_config,
    load_config,
)


def test_ensure_config_creates_default_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
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


def test_ensure_config_migrates_legacy_default_hotkey(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
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


def test_invalid_mode_raises_config_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
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


def test_load_config_accepts_utf8_bom(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "double_ctrl"
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
    assert config.hotkey == "double_ctrl"


def test_invalid_model_device_raises_config_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """hotkey = "double_ctrl"
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

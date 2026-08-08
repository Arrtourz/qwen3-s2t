from __future__ import annotations

from pathlib import Path

import pytest

from s2t.core.config import (
    ConfigError,
    TranscriptConfig,
    _parse_config,
    default_transcript_dir,
    load_config,
    save_config,
)


def _minimal_raw(**overrides):
    base = {
        "hotkey": "ctrl+alt+h",
        "language": "Chinese",
        "model": {"provider": "qwen3_asr", "variant": "0.6b", "path_or_id": "Qwen/Qwen3-ASR-0.6B", "device": "auto"},
    }
    base.update(overrides)
    return base


def test_parse_minimal_config():
    cfg = _parse_config(_minimal_raw())
    assert cfg.hotkey == "ctrl+alt+h"
    assert cfg.language == "Chinese"
    assert cfg.model.variant == "0.6b"
    assert cfg.recording.mode == "continuous"
    assert cfg.transcript.enabled is True


def test_parse_transcript_config():
    raw = _minimal_raw()
    raw["transcript"] = {"enabled": False, "output_dir": "/tmp/meetings", "filename_prefix": "standup"}
    cfg = _parse_config(raw)
    assert cfg.transcript.enabled is False
    assert cfg.transcript.output_dir == "/tmp/meetings"
    assert cfg.transcript.filename_prefix == "standup"


def test_empty_hotkey_becomes_none():
    # Empty hotkey is allowed → menu-only control (normalized to "none").
    cfg = _parse_config({"hotkey": "", "language": "Chinese", "model": {}})
    assert cfg.hotkey == "none"


def test_invalid_recording_mode_raises():
    raw = _minimal_raw()
    raw["recording"] = {"mode": "turbo"}
    with pytest.raises(ConfigError):
        _parse_config(raw)


def test_save_and_reload_roundtrip(workspace_tmp_path: Path):
    config_path = workspace_tmp_path / "config.toml"
    cfg = _parse_config(_minimal_raw())
    save_config(cfg, config_path)
    reloaded = load_config(config_path)
    assert reloaded.hotkey == cfg.hotkey
    assert reloaded.model.variant == cfg.model.variant
    assert reloaded.transcript.enabled == cfg.transcript.enabled


def test_default_transcript_dir():
    d = default_transcript_dir()
    assert "s2t-transcripts" in str(d)

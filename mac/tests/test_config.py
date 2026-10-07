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


def test_omitted_hotkey_defaults_to_off():
    # A config.toml without a hotkey line must not silently turn on pynput's
    # event tap; the generated default config already says "none".
    cfg = _parse_config({"language": "Chinese", "model": {}})
    assert cfg.hotkey == "none"


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


def test_legacy_speaker_filter_keys_are_ignored():
    # Speaker verification was removed; configs written before that still carry
    # speaker_filter / speaker_threshold and must keep loading.
    raw = _minimal_raw()
    raw["meeting"] = {"speaker_filter": True, "speaker_threshold": 0.55}
    cfg = _parse_config(raw)
    assert not hasattr(cfg.meeting, "speaker_filter")


def test_memory_idle_unload_default_and_validation():
    assert _parse_config(_minimal_raw()).memory.idle_unload_minutes == 10.0
    raw = _minimal_raw(); raw["memory"] = {"idle_unload_minutes": 0}
    assert _parse_config(raw).memory.idle_unload_minutes == 0
    raw["memory"] = {"idle_unload_minutes": -1}
    with pytest.raises(ConfigError):
        _parse_config(raw)


def test_legacy_paste_and_recording_mode_keys_are_ignored():
    # [paste] and recording.mode / input_device / continuous_window_seconds
    # belonged to the Windows dictation flow and were never read here.
    raw = _minimal_raw()
    raw["paste"] = {"multiline_strategy": "block"}
    raw["recording"] = {"mode": "manual", "input_device": "x", "continuous_window_seconds": 60}
    cfg = _parse_config(raw)
    assert not hasattr(cfg, "paste") and not hasattr(cfg.recording, "mode")

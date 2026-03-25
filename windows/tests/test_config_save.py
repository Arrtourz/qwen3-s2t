from __future__ import annotations

from pathlib import Path

from s2t.core.config import load_config, save_config


def test_save_config_persists_model_device_and_hotkey(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config = load_config(config_path)
    updated = config.__class__(
        hotkey="ctrl+alt+h",
        language=config.language,
        model=config.model.__class__(
            provider=config.model.provider,
            variant="1.7b",
            path_or_id="Qwen/Qwen3-ASR-1.7B",
            device="cpu",
        ),
        recording=config.recording.__class__(
            mode="manual",
            sample_rate=config.recording.sample_rate,
            channels=config.recording.channels,
            continuous_window_seconds=config.recording.continuous_window_seconds,
            block_duration_ms=config.recording.block_duration_ms,
        ),
        paste=config.paste,
        logging=config.logging,
    )

    save_config(updated, config_path)
    reloaded = load_config(config_path)

    assert reloaded.hotkey == "ctrl+alt+h"
    assert reloaded.model.variant == "1.7b"
    assert reloaded.model.device == "cpu"
    assert reloaded.recording.mode == "manual"


def test_save_config_preserves_custom_hotkey_with_default_mode_and_model(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config = load_config(config_path)
    updated = config.__class__(
        hotkey="ctrl+alt+h",
        language=config.language,
        model=config.model,
        recording=config.recording,
        paste=config.paste,
        logging=config.logging,
    )

    save_config(updated, config_path)
    reloaded = load_config(config_path)

    assert reloaded.hotkey == "ctrl+alt+h"
    assert reloaded.model.variant == config.model.variant
    assert reloaded.recording.mode == config.recording.mode


def test_save_config_persists_lightweight_backend_fields(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "config.toml"
    config = load_config(config_path)
    updated = config.__class__(
        hotkey=config.hotkey,
        language=config.language,
        model=config.model.__class__(
            provider="qwen_asr_cli",
            variant="0.6b",
            path_or_id="C:/models/qwen3-asr-0.6b",
            device="cpu",
            binary_path="C:/bin/qwen_asr.exe",
        ),
        recording=config.recording,
        paste=config.paste,
        logging=config.logging,
    )

    save_config(updated, config_path)
    reloaded = load_config(config_path)

    assert reloaded.model.provider == "qwen_asr_cli"
    assert reloaded.model.device == "cpu"
    assert reloaded.model.path_or_id == "C:/models/qwen3-asr-0.6b"
    assert reloaded.model.binary_path == "C:/bin/qwen_asr.exe"

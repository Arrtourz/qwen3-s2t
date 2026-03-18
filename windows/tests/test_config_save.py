from __future__ import annotations

from pathlib import Path

from s2t.core.config import load_config, save_config


def test_save_config_persists_model_device_and_hotkey(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
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

# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Repository Layout

- `windows/` contains the active Windows 11 tray app.
- `linux/` contains the archived original Ubuntu / PulseAudio implementation.
- Repository root only coordinates the subprojects and shared documentation.

Prefer working in `windows/` unless the task explicitly targets the legacy Linux version.

## Windows Setup

```powershell
cd windows
conda create -n s2t-win python=3.11
conda activate s2t-win
pip install -r requirements.txt
```

`windows/requirements.txt` is pinned to the official Windows CUDA PyTorch wheel.

## Windows Running

```powershell
cd windows
python -m s2t
python -m s2t --manual
python -m s2t --model 1.7b
python -m s2t --device gpu
```

Important runtime behavior:

- Default hotkey: `double_ctrl`
- Long-press `Ctrl` for about 2 seconds exits
- Default mode: `continuous`
- Supported model variants: `0.6b`, `1.7b`
- Supported devices: `auto`, `cpu`, `gpu`
- Config file: `%APPDATA%\\s2t\\config.toml`

Optional env override:

- `S2T_CONFIG_PATH`

## Windows Tests

```powershell
cd windows
pytest -q
```

## Linux Legacy Notes

The original Linux app now lives under `linux/`.

Run it from that folder if needed:

```bash
cd linux
python -m s2t
```

Its end-to-end test is `linux/tests/test_pipeline.py` and is intentionally excluded from default root test collection unless `S2T_RUN_LINUX_E2E=1`.

## Windows Architecture

- `windows/s2t/core/` contains config, controller, backend abstraction, and service interfaces.
- `windows/s2t/platform/windows/` contains hotkey, audio capture, paste, tray, notifications, settings UI, and single-instance lock.
- `windows/tests/` contains tests for config, hotkey, paste, controller, startup, and saving.
- `windows/scripts/` contains local utility scripts such as model benchmarking.

# qwen3-s2t

This folder contains the Windows 11 speech-to-text tray app built around `Qwen3-ASR`.

## MVP Features

- Tray-resident app with a minimal menu
- Configurable global hotkey
- Continuous recording mode by default
- Manual recording mode via CLI flag or config
- Automatic transcription through `Qwen/Qwen3-ASR-0.6B` by default
- Automatic paste into the active app with terminal-aware paste behavior
- Config-file based setup with reload support

## Requirements

- Windows 11
- Python 3.11
- A working microphone
- Optional CUDA-capable GPU for faster transcription

## Install

```powershell
cd windows
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` is pinned to the official Windows CUDA wheel for PyTorch so a compatible NVIDIA GPU will be used by default.

## Run

```powershell
cd windows
python -m s2t
python -m s2t --manual
python -m s2t --continuous
python -m s2t --model 1.7b
python -m s2t --device cpu
python -m s2t --model 0.6b --device gpu
```

On first launch the app creates a config file under `%APPDATA%\s2t\config.toml`.
Without flags, the default mode is `continuous`.
The config file and CLI both support choosing model `0.6b / 1.7b` and device `auto / cpu / gpu`.

## Benchmark Models

Use the helper script below to compare local model load time and first transcription latency:

```powershell
python scripts/benchmark_models.py --audio C:\path\to\sample.wav
```

Current local benchmark on Win11 + RTX 3080 favored `Qwen/Qwen3-ASR-0.6B` as the default because it used much less VRAM with similar first-pass latency.

## Default Hotkey

The generated default config uses:

```toml
hotkey = "double_ctrl"
```

You can change it and use the tray menu action `Reload Config`.
With the default hotkey mode, holding `Ctrl` for about 2 seconds exits the app.

## Model Selection

The config file supports both model size and runtime device:

```toml
[model]
variant = "0.6b"
device = "auto"
path_or_id = "Qwen/Qwen3-ASR-0.6B"
```

Examples:

```toml
[model]
variant = "1.7b"
device = "gpu"
path_or_id = "Qwen/Qwen3-ASR-1.7B"
```

```toml
[model]
variant = "0.6b"
device = "cpu"
path_or_id = "Qwen/Qwen3-ASR-0.6B"
```

## Tray Menu

- `Start / Snapshot`
- `Stop`
- `Settings`
- `Reload Config`
- `Open Logs`
- `Exit`

## Settings UI

Use the tray menu item `Settings` to change:

- Hotkey
- Recording mode
- Model variant
- Device preference

Saving writes back to `config.toml` and immediately reloads the running app.

## Notes

- The current implementation targets Windows only.
- The first start may take time because the ASR model is loaded during startup.
- Logs are written to `%APPDATA%\s2t\logs\s2t.log`.
- If you do not want CUDA, replace the `torch` requirement with a CPU build before installing.

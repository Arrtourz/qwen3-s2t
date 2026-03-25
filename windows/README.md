# qwen3-s2t

This folder contains the Windows 11 speech-to-text tray app built around `Qwen3-ASR`.

## MVP Features

- Tray-resident app with a minimal menu
- Configurable global hotkey
- Continuous recording mode by default
- Manual recording mode via CLI flag or config
- Automatic transcription through `Qwen/Qwen3-ASR-0.6B` by default
- Optional lightweight external CLI backend via `antirez/qwen-asr`
- Automatic paste into the active app using `Ctrl+Shift+V`
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
python -m s2t --backend python
python -m s2t --backend lightweight
python -m s2t --device cpu
python -m s2t --model 0.6b --device gpu
```

On first launch the app creates a config file under `%APPDATA%\s2t\config.toml`.
Without flags, the default mode is `continuous`.
The config file and CLI both support choosing model `0.6b / 1.7b` and device `auto / cpu / gpu`.

## Backend Selection

The app now supports two ASR backends:

- `python`: the current PyTorch + `qwen_asr` backend, with `auto / cpu / gpu`
- `lightweight`: an external `qwen-asr` CLI backend, intended for CPU-only local execution

CLI examples:

```powershell
python -m s2t --backend python --model 1.7b --device gpu
python -m s2t --backend lightweight --model 0.6b --device cpu
```

For the lightweight backend, `gpu` is not supported. Use `cpu` or `auto`.

## Benchmark Models

Use the helper script below to compare local model load time and first transcription latency:

```powershell
python scripts/benchmark_models.py --audio C:\path\to\sample.wav
```

Current local benchmark on Win11 + RTX 3080 favored `Qwen/Qwen3-ASR-0.6B` as the default because it used much less VRAM with similar first-pass latency.

## Default Hotkey

The generated default config uses:

```toml
hotkey = "ctrl+alt+h"
```

You can change it and use the tray menu action `Reload Config`.
Standard hotkeys like `ctrl+alt+h` are now registered through the native Windows `RegisterHotKey` API instead of the generic `keyboard.add_hotkey()` path, which is more reliable for normal modifier combinations.

## Model Selection

The config file supports both model size and runtime device:

```toml
[model]
variant = "0.6b"
device = "auto"
path_or_id = "Qwen/Qwen3-ASR-0.6B"
provider = "qwen3_asr"
binary_path = ""
```

Examples:

```toml
[model]
variant = "1.7b"
device = "gpu"
path_or_id = "Qwen/Qwen3-ASR-1.7B"
provider = "qwen3_asr"
binary_path = ""
```

```toml
[model]
variant = "0.6b"
device = "cpu"
path_or_id = "Qwen/Qwen3-ASR-0.6B"
provider = "qwen3_asr"
binary_path = ""
```

Lightweight backend example:

```toml
[model]
provider = "qwen_asr_cli"
variant = "0.6b"
device = "cpu"
path_or_id = "C:\\path\\to\\qwen3-asr-0.6b"
binary_path = "C:\\path\\to\\qwen_asr.exe"
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

- Backend
- Hotkey
- Recording mode
- Model variant
- Device preference
- Lightweight backend binary path
- Lightweight backend model directory

Saving writes back to `config.toml` and immediately reloads the running app.

## Audio Feedback

- The first hotkey press in `continuous` mode plays the start tone and opens the rolling microphone session.
- Later hotkey presses in `continuous` mode play a distinct snapshot tone and send the current buffered audio for transcription.
- The completion tone still plays only after transcription and paste finish.

## Lightweight Backend Setup

The lightweight backend is designed around [`antirez/qwen-asr`](../third_party/qwen-asr).

This repository has already been validated on Windows with:

- `MSYS2 UCRT64`
- `third_party/qwen-asr/qwen_asr.exe`
- `third_party/qwen-asr/qwen3-asr-0.6b`

Build path used locally:

```powershell
winget install --id MSYS2.MSYS2
```

```bash
pacman -S --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-make mingw-w64-ucrt-x86_64-openblas curl
cd /c/Users/thorn/Downloads/Tentacleslab/qwen3-s2t/third_party/qwen-asr
mingw32-make clean
mingw32-make qwen_asr \
  CFLAGS="-Wall -Wextra -O3 -march=native -ffast-math -DUSE_BLAS -DUSE_OPENBLAS -IC:/msys64/ucrt64/include/openblas" \
  LDFLAGS="-LC:/msys64/ucrt64/lib -lopenblas -lm -lpthread"
./download_model.sh --model small
```

Then point:

1. `binary_path` at `qwen_asr.exe`
2. `path_or_id` at the local model directory

The Windows app invokes the CLI like this:

```text
qwen_asr -d <model_dir> -i <temp.wav> --silent [--language <language>]
```

## Notes

- The current implementation targets Windows only.
- The first start may take time because the ASR model is loaded during startup.
- Logs are written to `%APPDATA%\s2t\logs\s2t.log`.
- If you do not want CUDA, replace the `torch` requirement with a CPU build before installing.
- If `%APPDATA%\s2t\tmp` is not writable, the lightweight backend falls back to a local `runtime-temp` directory under the current working directory.
- When launching `qwen_asr.exe` from normal PowerShell, the app automatically prepends `C:\msys64\ucrt64\bin` to `PATH` so that the MSYS2 OpenBLAS runtime DLLs can be found.

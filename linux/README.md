# s2t for Linux

This folder preserves the original Ubuntu-oriented implementation, but its runtime configuration is now aligned with the current Windows project for the shared core options.

It targets:

- Ubuntu
- PulseAudio / PipeWire
- X11 / Wayland helpers such as `xclip`, `xdotool`, `wtype`

## Features

- Double-click `Ctrl` to trigger speech capture
- Hold `Ctrl` for about 2 seconds to exit
- `continuous` and `manual` recording modes
- Qwen3-ASR model selection: `0.6b` or `1.7b`
- Runtime device selection: `auto`, `cpu`, or `gpu`
- Smart paste for terminals and GUI apps
- PulseAudio direct microphone capture

## Install

```bash
cd linux
conda create -n s2t python=3.11
conda activate s2t
pip install -r requirements.txt
conda install -c conda-forge xclip
```

## Run

```bash
cd linux
python -m s2t
python -m s2t --manual
python -m s2t --continuous
python -m s2t --model 1.7b
python -m s2t --device gpu
python -m s2t --model 0.6b --device cpu
python -m s2t --debug
```

## Config

On first launch the Linux app creates:

```bash
~/.config/s2t/config.toml
```

If `XDG_CONFIG_HOME` is set, the config file is created under `$XDG_CONFIG_HOME/s2t/config.toml` instead.

Default config:

```toml
hotkey = "double_ctrl"
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
```

Supported overrides:

- CLI: `--manual`, `--continuous`, `--model`, `--device`
- Env: `S2T_CONFIG_PATH`, `S2T_LANGUAGE`, `S2T_DEVICE`, `QWEN3_ASR_MODEL`

`QWEN3_ASR_MODEL` still works for custom local paths or custom Hugging Face IDs. When it matches one of the built-in Qwen3-ASR models, the variant is inferred automatically.

## Tests

Linux end-to-end validation remains in:

```bash
cd linux
export HF_TOKEN=<your_token>
python tests/test_pipeline.py
```

That pipeline test is intentionally excluded from default root test collection unless `S2T_RUN_LINUX_E2E=1`.

## Notes

- The Linux folder is preserved for compatibility and reference.
- Active product work is still centered on the Windows app under `windows/`.
- Debug output goes to `linux/tmp/s2t.log` and `linux/tmp/recordings/` when `--debug` is enabled.

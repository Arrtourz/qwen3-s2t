# qwen3-s2t — macOS

Menu-bar meeting transcriber for macOS, built around `Qwen3-ASR`.  
Records both **your mic** and **the other party's audio** simultaneously, auto-segments
speech on natural pauses, and saves timestamped, speaker-labeled entries to a local Markdown file.

## Features

- Menu-bar icon: ⏳ loading → 🎙 ready → 🔴 in a meeting — no window, no Dock icon
- **Start Meeting / End Meeting** from the menu — no hotkey, no setup
- **Dual-stream capture**: your mic (`🎤 Me`) + the other party's audio (`🔊 Them`) at once
- **Zero-config system audio**: captures Zoom/other-party sound via a Core Audio *system tap* — **does not change your output device** and **auto-follows AirPods ↔ built-in speakers**
- **Automatic sentence segmentation** via silence detection (latency-agnostic, tuned for readable transcripts)
- Transcription via `Qwen/Qwen3-ASR-0.6B` (MPS/Metal on Apple Silicon by default)
- **Speaker-labeled transcript**: entries appended with `[HH:MM:SS] 🎤 Me:` / `🔊 Them:` to a per-meeting Markdown file
- Configurable transcript folder + filename prefix (folder picker in Settings)

## Requirements

- macOS 12+, Apple Silicon or Intel
- Python 3.11
- Microphone access (grant in System Settings → Privacy → Microphone)
- Accessibility access for global hotkey (System Settings → Privacy → Accessibility → add Terminal / your Python binary)

## Install

```bash
cd mac
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> PyTorch is installed from the default PyPI index (CPU + MPS). MPS is used automatically on Apple Silicon.

## Run

```bash
cd mac
python -m s2t
python -m s2t --model 1.7b
python -m s2t --device cpu
python -m s2t --backend lightweight --device cpu
```

Config is created on first launch at `~/.config/s2t/config.toml`.

## Build the Desktop App

Package a double-clickable `.app` (alias mode — links to this venv, builds in seconds):

```bash
cd mac
.venv/bin/python setup.py py2app -A
open dist/
```

Drag `dist/s2t.app` to `/Applications`. It launches as a menu-bar-only app (no Dock icon).
Alias mode is for personal use on this machine; the `.app` uses the venv's Python + model cache.

## Using It in a Meeting

1. Click the 🎙 menu-bar icon → **Start Meeting** (icon turns 🔴)
2. First run: macOS asks for **Microphone** and **System Audio Recording** permission → Allow both
3. Talk / let the meeting play — both sides are transcribed and appended live
4. Menu → **End Meeting** → **Open Transcript** to read it

No audio-device setup needed. **Their Audio** defaults to *System audio — auto*, which
captures whatever is playing (Zoom, browser, …) without touching your output device;
switch freely between AirPods and speakers mid-meeting.

Optional tweaks in **Settings**:
- **My Mic**: `Auto` (default) or a specific input
- **Their Audio**: `System audio — auto` (default) · `Off` (mic only) · or a named device (e.g. BlackHole)
- **Transcript folder** / **filename prefix** (with a Browse… picker)

## Capturing Zoom / System Audio — Alternative: BlackHole

Not needed by default: the system tap (`system_source = "tap"`) already captures
the other party with no setup. Use BlackHole only if the tap is unavailable on
your macOS version.

1. Install BlackHole 2ch:
   ```bash
   brew install blackhole-2ch
   ```
2. Open **Audio MIDI Setup** → click `+` → **Create Multi-Output Device**
   - Check both your speakers and **BlackHole 2ch**
   - Set this as your system output (Sound → Output)
3. In `config.toml` set:
   ```toml
   [meeting]
   system_source = "device"
   system_device = "BlackHole 2ch"
   ```
4. Menu → **Reload Config**

To go back, set `system_source = "tap"` (or `"off"` for mic only) and reload.

## Hotkey (optional)

The app is driven from the menu bar; the hotkey is an optional extra that
toggles Start Meeting / End Meeting. It is **off by default** (`hotkey = "none"`).

To turn it on, set e.g. `hotkey = "ctrl+alt+h"` in `~/.config/s2t/config.toml`
and choose Reload Config. Registration needs Accessibility permission and is
skipped with a log warning if that is missing, so a hotkey problem never blocks
the menu.

There are no `continuous` / `manual` recording modes here — those belong to the
Windows app. A meeting records continuously from Start to End.

## Transcript Files

Files are saved to `~/Documents/s2t-transcripts/` by default.

Format example (`meeting_2025-08-06_14-30-00.md`):

```markdown
# Meeting — 2025-08-06 14:30

**[14:30:12]** The sprint retrospective will start in five minutes.

**[14:31:04]** We shipped the new onboarding flow last week.

---
*Session ended 15:02:47*
```

Configure path and filename prefix in Settings or via `[transcript]` in config.toml:

```toml
[transcript]
enabled = true
output_dir = ""           # empty = ~/Documents/s2t-transcripts
filename_prefix = "meeting"
```

## Tray Menu

| Item | Action |
|------|--------|
| Start Meeting | Begin recording both streams (icon turns 🔴) |
| End Meeting | Stop, flush the last utterance, close the transcript |
| Settings | Open `config.toml` in your editor (then use Reload Config) |
| Reload Config | Reload `config.toml` without restarting |
| Open Logs | Open the log directory in Finder |
| Open Transcript Folder | Open the transcript folder in Finder |
| Memory Report | Log a memory snapshot now (see Debugging) |
| Exit | Quit the app |

Start Meeting and End Meeting are enabled one at a time, matching the current state.

## Tests

```bash
cd mac
pytest -q
```

## Debugging Memory

`ps` and Activity Monitor disagree for this app: Metal/MPS buffers never show up
in RSS, so only Activity Monitor's figure (phys_footprint) is meaningful.

Turn on periodic memory logging either way:

```bash
S2T_MEMORY_DEBUG=1 python -m s2t
```

```toml
[debug]
memory_monitor = true
memory_monitor_interval_seconds = 60.0
```

Menu -> **Memory Report** logs one snapshot on demand, with or without the monitor.

Each line looks like:

```
MEM footprint=3780MB  mps_in_use=1975MB  mps_cache=72MB  queue=0  buffered=0.4s  objects=346836
```

| Field | Rising means |
|-------|--------------|
| `mps_in_use` | a real tensor leak — the only field that proves one |
| `mps_cache` | just allocator slack; released when the queue goes idle |
| `buffered` | audio piling up in a stream's segmenter |
| `queue` | transcription falling behind; oldest segments get dropped |
| `objects` | a Python-side leak |

`footprint` alone swings by ~1GB with utterance length and kernel reclaim timing,
so judge leaks by `mps_in_use` and `objects`, not by `footprint`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Hotkey not working | Add Terminal / Python binary to Accessibility in System Settings |
| No audio captured | Grant Microphone access; check input device name matches `sounddevice` device list |
| MPS out of memory | Switch to `--device cpu`, or set `model.variant = "0.6b"` |
| Memory looks high in Activity Monitor | Expected to sit around 2.5-3.8GB mid-meeting; see Debugging below |
| `rumps` import error | macOS only; ensure you're not running on Linux/Windows |

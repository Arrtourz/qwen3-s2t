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
python -m s2t --manual
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

## Capturing Zoom / System Audio (Meeting Transcription)

macOS does not expose system audio to apps directly. Use **BlackHole** as a virtual loopback device:

1. Install BlackHole 2ch:
   ```bash
   brew install blackhole-2ch
   ```
2. Open **Audio MIDI Setup** → click `+` → **Create Multi-Output Device**
   - Check both your speakers and **BlackHole 2ch**
   - Set this as your system output (Sound → Output)
3. In **s2t Settings** (tray icon → Settings), set **Input Device** to `BlackHole 2ch`
4. Reload Config — s2t now captures what Zoom plays

To revert to mic-only, clear the Input Device field and reload.

## Hotkey

Default: `ctrl+alt+h`

- First press in `continuous` mode: starts recording
- Subsequent presses: snapshot (transcribe buffered audio, keep recording)
- In `manual` mode: first press starts, second press stops and transcribes

Change in Settings or edit `~/.config/s2t/config.toml`.

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
| Start / Snapshot | Hotkey equivalent |
| Stop | Stop and transcribe current buffer |
| Settings | Open settings window |
| Reload Config | Reload config.toml without restart |
| Open Logs | Open log directory in Finder |
| Open Transcript | Open current session transcript in Finder |
| Exit | Quit app |

## Tests

```bash
cd mac
pytest -q
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Hotkey not working | Add Terminal / Python binary to Accessibility in System Settings |
| No audio captured | Grant Microphone access; check input device name matches `sounddevice` device list |
| MPS out of memory | Switch to `--model 0.6b --device mps` or `--device cpu` |
| `rumps` import error | macOS only; ensure you're not running on Linux/Windows |

# qwen3-s2t

This repository is now organized into platform-specific subprojects:

- `mac/`: macOS menu-bar meeting transcriber (mic + system audio, Apple Silicon)
- `windows/`: the active Windows 11 tray app
- `linux/`: the Ubuntu / PulseAudio implementation, now aligned with shared model/device runtime options

## macOS

Start with `mac/README.md`.

```bash
cd mac
```

## Windows

Start with `windows/README.md`.

Project root:

```powershell
cd windows
```

## Linux

Start with `linux/README.md`.

Project root:

```bash
cd linux
```

## Notes

- The Windows version is the active development target.
- The Linux version is retained and now supports the same model choices `0.6b / 1.7b` and device choices `auto / cpu / gpu`.

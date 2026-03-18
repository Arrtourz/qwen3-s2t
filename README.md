# qwen3-s2t

This repository is now organized into platform-specific subprojects:

- `windows/`: the active Windows 11 tray app
- `linux/`: the Ubuntu / PulseAudio implementation, now aligned with shared model/device runtime options

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

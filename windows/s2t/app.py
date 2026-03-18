from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .core.controller import SpeechToTextController
from .core.config import ConfigError
from .platform.windows.instance_lock import SingleInstanceLock


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows speech-to-text tray app")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--manual",
        action="store_true",
        help="Use manual start/stop recording instead of continuous mode",
    )
    mode_group.add_argument(
        "--continuous",
        action="store_true",
        help="Force continuous recording mode",
    )
    parser.add_argument(
        "--model",
        choices=["0.6b", "1.7b"],
        help="Temporarily choose the ASR model variant for this run",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "gpu"],
        help="Temporarily choose whether the ASR model runs on auto/cpu/gpu",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    mode_override = "manual" if args.manual else "continuous" if args.continuous else None

    config_override = os.environ.get("S2T_CONFIG_PATH", "").strip()
    config_path = Path(config_override) if config_override else None
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        _show_startup_message("s2t", "s2t is already running.")
        raise SystemExit(1)
    controller = SpeechToTextController(
        config_path=config_path,
        recording_mode_override=mode_override,
        model_variant_override=args.model,
        device_override=args.device,
    )
    try:
        try:
            controller.run()
        except ConfigError as exc:
            _show_startup_message("s2t config error", str(exc))
            raise SystemExit(2) from exc
        except ModuleNotFoundError as exc:
            _show_startup_message("s2t dependency error", f"Missing Python module: {exc.name}")
            raise SystemExit(3) from exc
        except Exception as exc:
            _show_startup_message("s2t startup failed", str(exc))
            raise
    finally:
        instance_lock.release()


def _show_startup_message(title: str, message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x00000010)
    except Exception:
        print(f"{title}: {message}", file=sys.stderr)

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .core.config import ConfigError
from .core.controller import SpeechToTextController
from .platform.macos.instance_lock import SingleInstanceLock


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="macOS speech-to-text menu bar app")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--manual", action="store_true", help="Manual start/stop recording mode")
    mode_group.add_argument("--continuous", action="store_true", help="Force continuous recording mode")
    parser.add_argument("--model", choices=["0.6b", "1.7b"], help="ASR model variant")
    parser.add_argument("--backend", choices=["python", "lightweight"], help="ASR backend")
    parser.add_argument("--device", choices=["auto", "cpu", "gpu"], help="Compute device")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    mode_override = "manual" if args.manual else "continuous" if args.continuous else None
    provider_override = {"python": "qwen3_asr", "lightweight": "qwen_asr_cli"}.get(args.backend)

    config_override = os.environ.get("S2T_CONFIG_PATH", "").strip()
    config_path = Path(config_override) if config_override else None

    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        print("s2t is already running.", file=sys.stderr)
        raise SystemExit(1)

    controller = SpeechToTextController(
        config_path=config_path,
        recording_mode_override=mode_override,
        provider_override=provider_override,
        model_variant_override=args.model,
        device_override=args.device,
    )
    try:
        controller.run()
    except ConfigError as exc:
        print(f"s2t config error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except ModuleNotFoundError as exc:
        print(f"s2t dependency error: Missing module {exc.name}", file=sys.stderr)
        raise SystemExit(3) from exc
    except Exception as exc:
        print(f"s2t startup failed: {exc}", file=sys.stderr)
        raise
    finally:
        instance_lock.release()

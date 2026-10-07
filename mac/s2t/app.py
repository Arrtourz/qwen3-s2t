from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .core.config import ConfigError
from .core.controller import SpeechToTextController
from .platform.macos.instance_lock import SingleInstanceLock


def build_arg_parser() -> argparse.ArgumentParser:
    # No --manual/--continuous here: those are Windows recording modes. This app
    # records a whole meeting between Start Meeting and End Meeting, so nothing
    # ever read recording.mode and the flags silently did nothing.
    parser = argparse.ArgumentParser(description="macOS speech-to-text menu bar app")
    parser.add_argument("--model", choices=["0.6b", "1.7b"], help="ASR model variant")
    parser.add_argument("--backend", choices=["python", "lightweight"], help="ASR backend")
    parser.add_argument("--device", choices=["auto", "cpu", "gpu"], help="Compute device")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    provider_override = {"python": "qwen3_asr", "lightweight": "qwen_asr_cli"}.get(args.backend)

    config_override = os.environ.get("S2T_CONFIG_PATH", "").strip()
    config_path = Path(config_override) if config_override else None

    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        print("s2t is already running.", file=sys.stderr)
        raise SystemExit(1)

    controller = SpeechToTextController(
        config_path=config_path,
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

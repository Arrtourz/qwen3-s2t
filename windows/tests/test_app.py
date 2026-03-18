from __future__ import annotations

from pathlib import Path
import os

import pytest

from s2t.app import build_arg_parser


def test_s2t_config_path_env_override_is_read(monkeypatch) -> None:
    config_path = Path("C:/tmp/custom-config.toml")
    monkeypatch.setenv("S2T_CONFIG_PATH", str(config_path))

    import s2t.app as app

    controller = app.SpeechToTextController(config_path=Path(os.environ["S2T_CONFIG_PATH"]))
    assert controller.config_path == config_path


def test_cli_parser_supports_manual_and_continuous() -> None:
    parser = build_arg_parser()

    manual_args = parser.parse_args(["--manual"])
    assert manual_args.manual is True
    assert manual_args.continuous is False

    continuous_args = parser.parse_args(["--continuous"])
    assert continuous_args.manual is False
    assert continuous_args.continuous is True

    model_args = parser.parse_args(["--model", "1.7b", "--device", "gpu"])
    assert model_args.model == "1.7b"
    assert model_args.device == "gpu"


def test_cli_parser_rejects_conflicting_mode_flags() -> None:
    parser = build_arg_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--manual", "--continuous"])

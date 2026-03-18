from __future__ import annotations

from pathlib import Path

from s2t.core.config import default_config_path
from s2t.core.controller import SpeechToTextController


def test_controller_defaults_to_user_config_when_no_path_is_provided() -> None:
    controller = SpeechToTextController()
    assert controller.config_path == default_config_path()


def test_controller_treats_directory_like_default_config() -> None:
    controller = SpeechToTextController(Path("."))
    assert controller.config_path == default_config_path()

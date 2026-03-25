from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from s2t.core.config import AppConfig, LoggingConfig, ModelConfig, PasteConfig, RecordingConfig, default_config_path
from s2t.core.controller import SpeechToTextController


def test_controller_defaults_to_user_config_when_no_path_is_provided() -> None:
    controller = SpeechToTextController()
    assert controller.config_path == default_config_path()


def test_controller_treats_directory_like_default_config() -> None:
    controller = SpeechToTextController(Path("."))
    assert controller.config_path == default_config_path()


def test_controller_console_ctrl_handler_triggers_shutdown(monkeypatch) -> None:
    controller = SpeechToTextController()
    calls: list[str] = []

    monkeypatch.setattr("s2t.core.controller.os.name", "nt")

    class FakeKernel32:
        def __init__(self) -> None:
            self.handler = None

        def SetConsoleCtrlHandler(self, handler, add):
            self.handler = handler
            return 1

    fake_kernel32 = FakeKernel32()
    fake_ctypes = SimpleNamespace(
        c_bool=bool,
        c_uint=int,
        WINFUNCTYPE=lambda *_args: (lambda fn: fn),
        windll=SimpleNamespace(kernel32=fake_kernel32),
    )

    monkeypatch.setattr("ctypes.WINFUNCTYPE", fake_ctypes.WINFUNCTYPE, raising=False)
    monkeypatch.setattr("ctypes.windll", fake_ctypes.windll, raising=False)
    monkeypatch.setattr(controller, "shutdown", lambda: calls.append("shutdown"))

    controller._install_console_ctrl_handler()
    assert fake_kernel32.handler is not None
    assert fake_kernel32.handler(0) is True
    assert calls == ["shutdown"]


def test_controller_lightweight_override_resets_model_paths(monkeypatch) -> None:
    config = AppConfig(
        hotkey="ctrl+alt+h",
        language="Chinese",
        model=ModelConfig(
            provider="qwen3_asr",
            variant="0.6b",
            path_or_id="Qwen/Qwen3-ASR-0.6B",
            device="auto",
            binary_path="",
        ),
        recording=RecordingConfig(),
        paste=PasteConfig(),
        logging=LoggingConfig(),
    )
    captured: dict[str, ModelConfig] = {}

    class FakeBackend:
        def load_model(self) -> None:
            return None

    class FakeAudio:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def close(self) -> None:
            return None

    class FakeHotkey:
        def register(self, *_args, **_kwargs) -> None:
            return None

        def unregister(self) -> None:
            return None

    class FakeTray:
        def notify(self, *_args, **_kwargs) -> None:
            return None

    monkeypatch.setattr("s2t.core.controller.load_config", lambda _path: config)
    monkeypatch.setattr("s2t.core.controller.configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("s2t.core.controller.SoundDeviceAudioCapture", FakeAudio)
    monkeypatch.setattr("s2t.core.controller.WindowsPasteService", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("s2t.core.controller.KeyboardHotkeyService", FakeHotkey)
    monkeypatch.setattr("s2t.core.controller.SettingsWindow", lambda *args, **kwargs: object())
    monkeypatch.setattr("s2t.core.controller.WindowsTrayService", lambda *args, **kwargs: FakeTray())

    def fake_build_backend(model: ModelConfig):
        captured["model"] = model
        return FakeBackend()

    monkeypatch.setattr("s2t.core.controller.build_backend", fake_build_backend)

    controller = SpeechToTextController(
        provider_override="qwen_asr_cli",
        model_variant_override="0.6b",
        device_override="cpu",
    )
    controller._load_runtime(initial=False)

    assert captured["model"].provider == "qwen_asr_cli"
    assert captured["model"].device == "cpu"
    assert captured["model"].path_or_id.endswith("third_party\\qwen-asr\\qwen3-asr-0.6b")
    assert captured["model"].binary_path.endswith("third_party\\qwen-asr\\qwen_asr.exe")


def test_continuous_hotkey_snapshots_without_restarting(monkeypatch) -> None:
    controller = SpeechToTextController()
    controller.config = AppConfig(
        hotkey="ctrl+alt+h",
        language="Chinese",
        model=ModelConfig(),
        recording=RecordingConfig(mode="continuous"),
        paste=PasteConfig(),
        logging=LoggingConfig(),
    )

    class FakeAudio:
        def __init__(self) -> None:
            self.started = False
            self.snapshots = 0

        def is_recording(self) -> bool:
            return True

        def start_recording(self, windowed: bool) -> bool:
            self.started = True
            return True

        def snapshot_recording(self):
            self.snapshots += 1
            return np.ones(3200, dtype=np.float32)

    fake_audio = FakeAudio()
    controller.audio = fake_audio

    beeps: list[tuple[int, int]] = []
    queued: list[np.ndarray] = []
    monkeypatch.setattr(controller, "_beep", lambda freq, duration_ms: beeps.append((freq, duration_ms)))
    monkeypatch.setattr(controller, "_queue_audio", lambda data: queued.append(data))

    controller.handle_hotkey()

    assert fake_audio.started is False
    assert fake_audio.snapshots == 1
    assert beeps == [(760, 90)]
    assert len(queued) == 1

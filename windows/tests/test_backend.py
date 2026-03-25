from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from s2t.core.backend import QwenAsrCliBackend, Qwen3ASRBackend, build_backend
from s2t.core.config import ModelConfig


def test_build_backend_supports_lightweight_provider() -> None:
    python_backend = build_backend(ModelConfig())
    lightweight_backend = build_backend(
        ModelConfig(
            provider="qwen_asr_cli",
            variant="0.6b",
            path_or_id="C:/models/qwen3-asr-0.6b",
            device="cpu",
            binary_path="C:/bin/qwen_asr.exe",
        )
    )

    assert isinstance(python_backend, Qwen3ASRBackend)
    assert isinstance(lightweight_backend, QwenAsrCliBackend)


def test_lightweight_backend_invokes_cli_and_returns_stdout(workspace_tmp_path: Path, monkeypatch) -> None:
    model_dir = workspace_tmp_path / "qwen3-asr-0.6b"
    model_dir.mkdir()
    binary_path = workspace_tmp_path / "fake_qwen_asr.cmd"
    monkeypatch.setenv("S2T_RUNTIME_TEMP_DIR", str(workspace_tmp_path / "runtime-temp"))
    binary_path.write_text(
        """@echo off
setlocal
set "lang="
:loop
if "%~1"=="" goto done
if /I "%~1"=="--language" (
  set "lang=%~2"
  shift
)
if /I "%~1"=="-i" (
  if not exist "%~2" exit /b 9
  shift
)
shift
goto loop
:done
echo lightweight transcript %lang%
""",
        encoding="utf-8",
    )

    backend = QwenAsrCliBackend(
        ModelConfig(
            provider="qwen_asr_cli",
            variant="0.6b",
            path_or_id=str(model_dir),
            device="cpu",
            binary_path=str(binary_path),
        )
    )
    backend.load_model()

    text = backend.transcribe(np.array([0.0, 0.1, -0.1, 0.0], dtype=np.float32), language="Chinese")

    assert text == "lightweight transcript Chinese"


def test_lightweight_backend_raises_for_cli_failure(workspace_tmp_path: Path, monkeypatch) -> None:
    model_dir = workspace_tmp_path / "qwen3-asr-0.6b"
    model_dir.mkdir()
    binary_path = workspace_tmp_path / "fail_qwen_asr.cmd"
    monkeypatch.setenv("S2T_RUNTIME_TEMP_DIR", str(workspace_tmp_path / "runtime-temp"))
    binary_path.write_text(
        """@echo off
echo lightweight failure 1>&2
exit /b 7
""",
        encoding="utf-8",
    )

    backend = QwenAsrCliBackend(
        ModelConfig(
            provider="qwen_asr_cli",
            variant="0.6b",
            path_or_id=str(model_dir),
            device="cpu",
            binary_path=str(binary_path),
        )
    )
    backend.load_model()

    with pytest.raises(RuntimeError, match="lightweight failure"):
        backend.transcribe(np.array([0.0, 0.1, -0.1, 0.0], dtype=np.float32), language=None)

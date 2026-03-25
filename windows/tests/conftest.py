from __future__ import annotations

import shutil
import sys
from pathlib import Path
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def workspace_tmp_path() -> Path:
    base_dir = ROOT / "test-output"
    base_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = base_dir / f"pytest-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

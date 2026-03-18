from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_file: Path, level_name: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, level_name.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

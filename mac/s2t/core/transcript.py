from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

from .config import TranscriptConfig, default_transcript_dir


log = logging.getLogger(__name__)


class TranscriptWriter:
    """Appends timestamped transcription entries to a per-session Markdown file."""

    def __init__(self, config: TranscriptConfig) -> None:
        self._config = config
        self._path: Path | None = None
        self._lock = threading.Lock()
        self._session_start: datetime | None = None

    def open_session(self) -> Path | None:
        if not self._config.enabled:
            return None

        with self._lock:
            if self._path is not None:
                return self._path

            now = datetime.now()
            self._session_start = now
            output_dir = Path(self._config.output_dir) if self._config.output_dir else default_transcript_dir()
            output_dir.mkdir(parents=True, exist_ok=True)

            date_str = now.strftime("%Y-%m-%d_%H-%M-%S")
            prefix = self._config.filename_prefix or "meeting"
            filename = f"{prefix}_{date_str}.md"
            self._path = output_dir / filename

            header = f"# {prefix.replace('-', ' ').replace('_', ' ').title()} — {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            self._path.write_text(header, encoding="utf-8")
            log.info("Transcript session opened: %s", self._path)
            return self._path

    def append(self, text: str, speaker: str | None = None) -> None:
        if not self._config.enabled or not text.strip():
            return

        with self._lock:
            if self._path is None:
                return

            timestamp = datetime.now().strftime("%H:%M:%S")
            if speaker:
                entry = f"**[{timestamp}] {speaker}:** {text.strip()}\n\n"
            else:
                entry = f"**[{timestamp}]** {text.strip()}\n\n"
            try:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(entry)
            except Exception:
                log.exception("Failed to write transcript entry")

    def close_session(self) -> None:
        with self._lock:
            if self._path is None:
                return
            try:
                now = datetime.now()
                footer = f"\n---\n*Session ended {now.strftime('%H:%M:%S')}*\n"
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(footer)
            except Exception:
                log.exception("Failed to write transcript footer")
            log.info("Transcript session closed: %s", self._path)
            self._path = None
            self._session_start = None

    @property
    def current_path(self) -> Path | None:
        with self._lock:
            return self._path

from __future__ import annotations

from pathlib import Path

from s2t.core.config import TranscriptConfig
from s2t.core.transcript import TranscriptWriter


def test_transcript_creates_file(workspace_tmp_path: Path):
    cfg = TranscriptConfig(enabled=True, output_dir=str(workspace_tmp_path), filename_prefix="test")
    writer = TranscriptWriter(cfg)
    path = writer.open_session()
    assert path is not None
    assert path.exists()
    assert path.name.startswith("test_")
    assert path.suffix == ".md"


def test_transcript_appends_entries(workspace_tmp_path: Path):
    cfg = TranscriptConfig(enabled=True, output_dir=str(workspace_tmp_path), filename_prefix="mtg")
    writer = TranscriptWriter(cfg)
    writer.open_session()
    writer.append("Hello world")
    writer.append("Second line")
    content = writer.current_path.read_text(encoding="utf-8")
    assert "Hello world" in content
    assert "Second line" in content
    assert "**[" in content


def test_transcript_disabled_writes_nothing(workspace_tmp_path: Path):
    cfg = TranscriptConfig(enabled=False, output_dir=str(workspace_tmp_path))
    writer = TranscriptWriter(cfg)
    path = writer.open_session()
    assert path is None
    assert list(workspace_tmp_path.iterdir()) == []


def test_transcript_close_appends_footer(workspace_tmp_path: Path):
    cfg = TranscriptConfig(enabled=True, output_dir=str(workspace_tmp_path), filename_prefix="mtg")
    writer = TranscriptWriter(cfg)
    path = writer.open_session()
    writer.append("Some text")
    writer.close_session()
    content = path.read_text(encoding="utf-8")
    assert "Session ended" in content
    assert writer.current_path is None


def test_transcript_speaker_label(workspace_tmp_path: Path):
    cfg = TranscriptConfig(enabled=True, output_dir=str(workspace_tmp_path), filename_prefix="mtg")
    writer = TranscriptWriter(cfg)
    writer.open_session()
    writer.append("我们开始吧", speaker="🎤 Me")
    writer.append("好的", speaker="🔊 Them")
    content = writer.current_path.read_text(encoding="utf-8")
    assert "🎤 Me:" in content
    assert "🔊 Them:" in content
    assert "我们开始吧" in content


def test_transcript_ignore_blank_append(workspace_tmp_path: Path):
    cfg = TranscriptConfig(enabled=True, output_dir=str(workspace_tmp_path), filename_prefix="blank")
    writer = TranscriptWriter(cfg)
    writer.open_session()
    writer.append("  ")
    content = writer.current_path.read_text(encoding="utf-8")
    # Only the header line should exist — no entry appended
    assert "**[" not in content


def test_restart_within_same_second_does_not_overwrite(tmp_path):
    from s2t.core.config import TranscriptConfig
    from s2t.core.transcript import TranscriptWriter

    w = TranscriptWriter(TranscriptConfig(enabled=True, output_dir=str(tmp_path), filename_prefix="meeting"))
    first = w.open_session()
    w.append("first meeting content", speaker="Me")
    w.close_session()
    second = w.open_session()
    w.close_session()
    assert first != second
    assert "first meeting content" in first.read_text(encoding="utf-8")
    assert second.name.endswith("_2.md")

"""Unit tests for BatchTranscriptionService file discovery.

Pure filesystem — no Deepgram call. Guards the case-insensitive audio-file
scan (uppercase extensions from phone recorders must be found, #478).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from core.services.transcription.batch_transcription_service import BatchTranscriptionService


async def test_preview_finds_mixed_case_audio_extensions(tmp_path: Any) -> None:
    (tmp_path / "VOICE.MP3").write_bytes(b"x")
    (tmp_path / "Interview.WAV").write_bytes(b"y")
    (tmp_path / "clip.mp3").write_bytes(b"z")
    (tmp_path / "notes.txt").write_bytes(b"ignored")  # not audio
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    service = BatchTranscriptionService(deepgram_adapter=MagicMock())
    result = service.preview(tmp_path, out_dir)

    assert result.is_ok
    names = {f.name for f in result.value.files}
    assert names == {"VOICE.MP3", "Interview.WAV", "clip.mp3"}

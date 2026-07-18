"""
Batch Transcription Service (Tier 1)
======================================

Audio folder → .txt transcripts. Pure filesystem, no Neo4j.

Processes multiple audio files through Deepgram concurrently with
semaphore-bounded parallelism. Supports preview (dry-run) and
skip-existing logic for idempotent reruns.

Usage:
    service = BatchTranscriptionService(deepgram_adapter)
    preview = service.preview(Path("data/je_inputs"), Path("data/je_outputs"))
    result = await service.transcribe_batch(Path("data/je_inputs"), Path("data/je_outputs"))
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.utils.exception_types import FILE_IO_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from pathlib import Path

    from core.ports.transcription_protocols import TranscriptionPort

logger = get_logger("skuel.services.transcription.batch")

# Audio extensions supported by DeepgramAdapter._get_mimetype()
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"}


def _path_name(p: Path) -> str:
    """Sort key for paths by name (SKUEL012: named function, not lambda)."""
    return p.name


@dataclass(frozen=True)
class BatchFileInfo:
    """Info about a single audio file for preview."""

    name: str
    size_mb: float
    path: Path


@dataclass(frozen=True)
class BatchTranscriptionPreview:
    """Preview of batch transcription — what would happen."""

    files: list[BatchFileInfo]
    total_files: int
    total_size_mb: float
    already_transcribed: list[str]  # filenames with existing .txt in output_dir


@dataclass(frozen=True)
class BatchTranscriptionResult:
    """Result of batch transcription run."""

    total_files: int
    succeeded: int
    failed: int
    skipped: int
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


class BatchTranscriptionService:
    """
    Batch audio → text transcription via Deepgram.

    Tier 1 of the journals pipeline: produces .txt files from audio.
    No Neo4j involvement — pure filesystem I/O + Deepgram API.

    Concurrency pattern from core/services/ingestion/batch.py.
    """

    def __init__(
        self,
        deepgram_adapter: TranscriptionPort,
        max_concurrent: int = 5,
    ) -> None:
        """
        Initialize batch transcription service.

        Args:
            deepgram_adapter: Transcription port (required; DeepgramAdapter at runtime)
            max_concurrent: Max parallel transcription requests
        """
        if not deepgram_adapter:
            raise ValueError("A transcription port is required (fail-fast)")

        self.deepgram = deepgram_adapter
        self.max_concurrent = max_concurrent
        self.logger = logger

    async def transcribe_one(self, audio_path: str) -> Result[str]:
        """Transcribe a single audio file and return the transcript text.

        Stateless: calls the Deepgram port directly and returns the transcript
        in memory — no ``.txt`` write, no Neo4j. Used by the FOUNDER interactive
        upload path, which needs the transcript string to render the review
        card before the DNWF stages. The batch/file-write variant lives in
        :meth:`transcribe_batch`.
        """
        try:
            result = await self.deepgram.transcribe(audio_path=audio_path)
        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(f"Audio file read failed: {e}", operation="transcribe_one")
            )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.transcript_text)

    def _find_audio_files(self, input_dir: Path) -> list[Path]:
        """Find all audio files in directory (non-recursive, case-insensitive).

        Matches on the lowercased suffix so uppercase extensions (``VOICE.MP3``,
        ``Interview.WAV`` — common from phone recorders) are picked up, not just
        the lowercase ``*.mp3`` glob.
        """
        files = [
            f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
        ]
        return sorted(files, key=_path_name)

    def preview(
        self,
        input_dir: Path,
        output_dir: Path,
    ) -> Result[BatchTranscriptionPreview]:
        """
        Preview what a batch transcription would do.

        Lists audio files, sizes, and which already have .txt output.

        Args:
            input_dir: Directory containing audio files
            output_dir: Directory where .txt files would be written

        Returns:
            Result[BatchTranscriptionPreview]
        """
        if not input_dir.is_dir():
            return Result.fail(
                Errors.validation(f"Input directory does not exist: {input_dir}", field="input_dir")
            )

        audio_files = self._find_audio_files(input_dir)
        if not audio_files:
            return Result.ok(
                BatchTranscriptionPreview(
                    files=[], total_files=0, total_size_mb=0.0, already_transcribed=[]
                )
            )

        files_info = []
        already_transcribed = []
        total_size = 0.0

        for audio_path in audio_files:
            size_mb = audio_path.stat().st_size / (1024 * 1024)
            total_size += size_mb
            files_info.append(
                BatchFileInfo(name=audio_path.name, size_mb=round(size_mb, 2), path=audio_path)
            )

            txt_path = output_dir / f"{audio_path.stem}.txt"
            if txt_path.exists():
                already_transcribed.append(audio_path.name)

        return Result.ok(
            BatchTranscriptionPreview(
                files=files_info,
                total_files=len(files_info),
                total_size_mb=round(total_size, 2),
                already_transcribed=already_transcribed,
            )
        )

    async def transcribe_batch(
        self,
        input_dir: Path,
        output_dir: Path,
        skip_existing: bool = True,
    ) -> Result[BatchTranscriptionResult]:
        """
        Transcribe all audio files in a directory to .txt files.

        Args:
            input_dir: Directory containing audio files
            output_dir: Directory for .txt output files
            skip_existing: Skip files that already have .txt output (default True)

        Returns:
            Result[BatchTranscriptionResult]
        """
        if not input_dir.is_dir():
            return Result.fail(
                Errors.validation(f"Input directory does not exist: {input_dir}", field="input_dir")
            )

        # Ensure output directory exists
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except FILE_IO_EXCEPTIONS as e:
            return Result.fail(
                Errors.system(f"Cannot create output directory: {e}", operation="transcribe_batch")
            )

        audio_files = self._find_audio_files(input_dir)
        if not audio_files:
            return Result.ok(
                BatchTranscriptionResult(total_files=0, succeeded=0, failed=0, skipped=0)
            )

        self.logger.info(f"Starting batch transcription: {len(audio_files)} files from {input_dir}")

        # Concurrent transcription with semaphore
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [
            self._transcribe_single(f, output_dir, semaphore, skip_existing) for f in audio_files
        ]
        results = await asyncio.gather(*tasks)

        # Aggregate results
        succeeded = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        errors = [
            {"name": r["name"], "error": r.get("error", "")}
            for r in results
            if r["status"] == "failed"
        ]

        self.logger.info(
            f"Batch transcription complete: {succeeded} succeeded, {failed} failed, {skipped} skipped"
        )

        return Result.ok(
            BatchTranscriptionResult(
                total_files=len(audio_files),
                succeeded=succeeded,
                failed=failed,
                skipped=skipped,
                results=list(results),
                errors=errors,
            )
        )

    async def _transcribe_single(
        self,
        audio_path: Path,
        output_dir: Path,
        semaphore: asyncio.Semaphore,
        skip_existing: bool,
    ) -> dict[str, Any]:
        """
        Transcribe a single audio file to .txt.

        Args:
            audio_path: Path to audio file
            output_dir: Directory for output .txt file
            semaphore: Concurrency limiter
            skip_existing: Whether to skip if .txt already exists

        Returns:
            Dict with {name, status, word_count, confidence, error}
        """
        txt_path = output_dir / f"{audio_path.stem}.txt"
        file_name = audio_path.name

        # Skip if already transcribed
        if skip_existing and txt_path.exists():
            self.logger.debug(f"Skipping {file_name} (already transcribed)")
            return {"name": file_name, "status": "skipped"}

        async with semaphore:
            self.logger.info(f"Transcribing: {file_name}")

            try:
                result = await self.deepgram.transcribe(audio_path=str(audio_path))

                if result.is_error:
                    error_msg = str(result.error)
                    self.logger.error(f"Transcription failed for {file_name}: {error_msg}")
                    return {"name": file_name, "status": "failed", "error": error_msg}

                deepgram_result = result.value

                # Write transcript to .txt
                txt_path.write_text(deepgram_result.transcript_text, encoding="utf-8")

                self.logger.info(
                    f"Transcribed {file_name}: {deepgram_result.word_count} words, "
                    f"confidence={deepgram_result.confidence_score:.2f}"
                )

                return {
                    "name": file_name,
                    "status": "success",
                    "word_count": deepgram_result.word_count,
                    "confidence": deepgram_result.confidence_score,
                    "duration_seconds": deepgram_result.duration_seconds,
                    "output_path": str(txt_path),
                }

            except Exception as e:  # safety-net: single file failure must not stop batch
                self.logger.error(f"Error transcribing {file_name}: {e}")
                return {"name": file_name, "status": "failed", "error": str(e)}


__all__ = [
    "BatchFileInfo",
    "BatchTranscriptionPreview",
    "BatchTranscriptionResult",
    "BatchTranscriptionService",
]

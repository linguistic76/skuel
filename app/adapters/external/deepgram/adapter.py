"""
Deepgram Adapter - Thin Wrapper for Audio Transcription API
============================================================

Single responsibility: Send audio to Deepgram, return transcript.

ARCHITECTURE DECISION (December 2025):
This is a thin adapter, NOT a service. It has no business logic,
no state management, no persistence. Just API calls.

Usage:
    adapter = DeepgramAdapter(api_key="...")
    result = await adapter.transcribe(audio_path, options)
    if result.is_ok:
        print(result.value.transcript_text)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiofiles  # type: ignore[import-untyped]
from deepgram import DeepgramClient, PrerecordedOptions
from deepgram.options import DeepgramClientOptions

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.type_converters import _HasToDict

logger = get_logger(__name__)


@dataclass
class TranscriptionResult:
    """Result from Deepgram transcription."""

    transcript_text: str
    confidence_score: float
    duration_seconds: float
    word_count: int
    raw_response: dict[str, Any] | None = None


class DeepgramAdapter:
    """
    Thin adapter for Deepgram audio transcription API.

    Does ONE thing: audio file → API call → transcript.
    No persistence, no state, no business logic.
    """

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        """
        Initialize with Deepgram API key.

        Args:
            api_key: Deepgram API key (required)
            timeout: API request timeout in seconds (default: 120s for large files)

        Raises:
            ValueError: If api_key is not provided
        """
        if not api_key:
            raise ValueError("Deepgram API key is required")

        # Initialize client with timeout configuration
        config = DeepgramClientOptions(
            api_key=api_key,
            options={"timeout": timeout}
        )
        self.client = DeepgramClient(api_key=api_key, config=config)
        self.timeout = timeout
        self.logger = logger

    async def transcribe(
        self,
        audio_path: str | Path,
        language: str = "en",
        model: str = "nova-2",
        punctuate: bool = True,
        paragraphs: bool = True,
        diarize: bool = False,
    ) -> Result[TranscriptionResult]:
        """
        Transcribe audio file using Deepgram API.

        Args:
            audio_path: Path to audio file
            language: Language code (default: "en")
            model: Deepgram model (default: "nova-2")
            punctuate: Enable punctuation
            paragraphs: Enable paragraph detection
            diarize: Enable speaker diarization

        Returns:
            Result containing TranscriptionResult or error
        """
        # Validate file exists
        path = Path(audio_path)
        if not path.exists():
            return Result.fail(
                Errors.validation(
                    f"Audio file not found: {audio_path}",
                    field="audio_path",
                )
            )

        try:
            # Read audio file asynchronously
            async with aiofiles.open(path, "rb") as audio_file:
                audio_data = await audio_file.read()

            # Configure options
            options = PrerecordedOptions(
                model=model,
                language=language,
                smart_format=True,
                punctuate=punctuate,
                paragraphs=paragraphs,
                diarize=diarize,
                utterances=True,
            )

            # Call Deepgram API
            file_size_mb = len(audio_data) / (1024 * 1024)
            self.logger.info(
                f"Sending audio to Deepgram: {path.name} ({file_size_mb:.2f}MB, timeout={self.timeout}s)"
            )
            response = self.client.listen.rest.v("1").transcribe_file(
                {"buffer": audio_data, "mimetype": self._get_mimetype(path.suffix)},
                options,
                timeout=self.timeout,
            )

            # Extract results
            transcript_text = self._extract_transcript(response)
            confidence_score = self._extract_confidence(response)
            duration_seconds = self._extract_duration(response)
            word_count = len(transcript_text.split()) if transcript_text else 0

            self.logger.info(
                f"Transcription complete: {word_count} words, "
                f"{duration_seconds:.1f}s, confidence: {confidence_score:.2f}"
            )

            return Result.ok(
                TranscriptionResult(
                    transcript_text=transcript_text,
                    confidence_score=confidence_score,
                    duration_seconds=duration_seconds,
                    word_count=word_count,
                    raw_response=response.to_dict() if isinstance(response, _HasToDict) else None,
                )
            )

        except FileNotFoundError:
            return Result.fail(
                Errors.validation(f"Audio file not found: {audio_path}", field="audio_path")
            )
        except Exception as e:
            self.logger.error(f"Deepgram API error: {e}")
            return Result.fail(
                Errors.integration(
                    service="deepgram",
                    message=str(e),
                    user_message="Audio transcription failed",
                )
            )

    def _get_mimetype(self, suffix: str) -> str:
        """Get MIME type from file suffix."""
        mimetypes = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/m4a",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
            ".webm": "audio/webm",
        }
        return mimetypes.get(suffix.lower(), "audio/mpeg")

    def _extract_transcript(self, response: Any) -> str:
        """Extract transcript text from Deepgram response."""
        try:
            channels = response.results.channels
            if channels and len(channels) > 0:
                alternatives = channels[0].alternatives
                if alternatives and len(alternatives) > 0:
                    return alternatives[0].transcript or ""
        except (AttributeError, IndexError):
            pass
        return ""

    def _extract_confidence(self, response: Any) -> float:
        """Extract confidence score from Deepgram response."""
        try:
            channels = response.results.channels
            if channels and len(channels) > 0:
                alternatives = channels[0].alternatives
                if alternatives and len(alternatives) > 0:
                    return float(alternatives[0].confidence or 0.0)
        except (AttributeError, IndexError, TypeError):
            pass
        return 0.0

    def _extract_duration(self, response: Any) -> float:
        """Extract audio duration from Deepgram response."""
        try:
            return float(response.metadata.duration or 0.0)
        except (AttributeError, TypeError):
            pass
        return 0.0


__all__ = ["DeepgramAdapter", "TranscriptionResult"]

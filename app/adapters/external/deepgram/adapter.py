"""
Deepgram Adapter - Thin Wrapper for Audio Transcription API
============================================================

Single responsibility: Send audio to Deepgram, return transcript.

All transcription options are controlled via config/deepgram.toml.
The adapter reads a DeepgramConfig at init time and uses it as defaults.
Per-call overrides are still possible via keyword arguments.

See: docs/configuration/DEEPGRAM_CONFIG.md
See: config/deepgram.toml

ARCHITECTURE DECISION (December 2025):
This is a thin adapter, NOT a service. It has no business logic,
no state management, no persistence. Just API calls.

Usage:
    from core.config.deepgram_config import load_deepgram_config

    config = load_deepgram_config()
    adapter = DeepgramAdapter(api_key="...", config=config)
    result = await adapter.transcribe(audio_path)
    if result.is_ok:
        print(result.value.transcript_text)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles  # type: ignore[import-untyped]
from deepgram import DeepgramClient, PrerecordedOptions
from deepgram.options import DeepgramClientOptions

from core.ports.transcription_protocols import TranscriptionResult
from core.utils.exception_types import DEEPGRAM_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.retry import async_retry
from core.utils.type_converters import _HasToDict

if TYPE_CHECKING:
    from core.config.deepgram_config import DeepgramConfig
    from core.models.transcription.transcription import TranscriptionProcessOptions

logger = get_logger(__name__)


class DeepgramAdapter:
    """
    Thin adapter for Deepgram audio transcription API — implements
    ``core.ports.transcription_protocols.TranscriptionPort``.

    Does ONE thing: audio file → API call → transcript. No persistence, no
    state, no business logic. The ``deepgram`` SDK and response parsing stay
    here, below the boundary; core depends only on ``TranscriptionPort`` +
    the ``TranscriptionResult`` DTO.

    All options are driven by DeepgramConfig (loaded from config/deepgram.toml).
    """

    def __init__(
        self,
        api_key: str,
        config: DeepgramConfig | None = None,
        timeout: float | None = None,
    ) -> None:
        """
        Initialize with Deepgram API key and optional config.

        Args:
            api_key: Deepgram API key (required)
            config: DeepgramConfig from config/deepgram.toml (optional, uses defaults if None)
            timeout: API request timeout override. If None, uses config.timeout (default: 120s).

        Raises:
            ValueError: If api_key is not provided
        """
        if not api_key:
            raise ValueError("Deepgram API key is required")

        # Load config — import here to avoid circular imports at module level
        if config is None:
            from core.config.deepgram_config import DeepgramConfig

            config = DeepgramConfig()

        self.config = config
        self.timeout = timeout if timeout is not None else config.timeout

        # Initialize client with timeout configuration
        client_config = DeepgramClientOptions(api_key=api_key, options={"timeout": self.timeout})
        self.client = DeepgramClient(api_key=api_key, config=client_config)
        self.logger = logger

    def _build_options(self, **overrides: Any) -> PrerecordedOptions:
        """Build PrerecordedOptions from config with optional per-call overrides.

        Merges config/deepgram.toml defaults with any keyword overrides.
        Only non-default values are passed to Deepgram to avoid unnecessary API charges.
        """
        # Start with config values
        params = self.config.to_transcribe_kwargs()

        # Apply per-call overrides
        params.update({k: v for k, v in overrides.items() if v is not None})

        # Build PrerecordedOptions — only include truthy intelligence features
        # and non-empty list fields to keep the API call clean
        opts: dict[str, Any] = {
            "model": params["model"],
            "language": params["language"],
            "smart_format": params["smart_format"],
            "punctuate": params["punctuate"],
            "paragraphs": params["paragraphs"],
            "utterances": params["utterances"],
            "utt_split": params["utt_split"],
            "diarize": params["diarize"],
        }

        # Conditional options — only add when enabled to avoid extra API costs
        if params.get("detect_language"):
            opts["detect_language"] = True
        if params.get("numerals"):
            opts["numerals"] = True
        if params.get("measurements"):
            opts["measurements"] = True
        if params.get("filler_words"):
            opts["filler_words"] = True
        if params.get("profanity_filter"):
            opts["profanity_filter"] = True
        if params.get("dictation"):
            opts["dictation"] = True
        if params.get("summarize"):
            opts["summarize"] = params["summarize"]
        if params.get("topics"):
            opts["topics"] = True
        if params.get("intents"):
            opts["intents"] = True
        if params.get("sentiment"):
            opts["sentiment"] = True
        if params.get("detect_entities"):
            opts["detect_entities"] = True
        if params.get("keywords"):
            opts["keywords"] = params["keywords"]
        if params.get("replace"):
            opts["replace"] = params["replace"]
        if params.get("redact"):
            opts["redact"] = params["redact"]
        if params.get("alternatives", 1) > 1:
            opts["alternatives"] = params["alternatives"]
        if params.get("tags"):
            opts["tag"] = params["tags"]

        return PrerecordedOptions(**opts)

    @async_retry(exceptions=DEEPGRAM_EXCEPTIONS, max_attempts=3, base_delay=2.0)
    async def _transcribe_raw(  # skuel-lint: disable=SKUEL029 -- @async_retry wrapper awaits this unconditionally (core/utils/retry.py)
        self,
        audio_data: bytes,
        path: Path,
        options: PrerecordedOptions,
    ) -> Any:  # boundary: deepgram-sdk-response
        return self.client.listen.rest.v("1").transcribe_file(  # pyright: ignore[reportAttributeAccessIssue]
            {"buffer": audio_data, "mimetype": self._get_mimetype(path.suffix)},
            options,
            timeout=self.timeout,
        )

    async def transcribe(
        self,
        audio_path: str | Path,
        options: TranscriptionProcessOptions | None = None,
    ) -> Result[TranscriptionResult]:
        """
        Transcribe audio file using Deepgram API.

        Options come from config/deepgram.toml by default; *options* overrides
        the fields it carries for this single call.

        Args:
            audio_path: Path to audio file
            options: Per-call overrides (language/model/punctuate/paragraphs/
                diarize). Every other Deepgram knob stays on the config.

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

            # Build options from config + per-call overrides.
            # exclude_unset, not a plain model_dump: every field on
            # TranscriptionProcessOptions has a default, so a bare dump would
            # reassert those defaults over config and a caller passing only
            # diarize=True would silently reset the configured model/language.
            # Overriding means overriding what the caller actually set.
            dg_options = self._build_options(
                **(options.model_dump(exclude_unset=True) if options else {})
            )

            # Call Deepgram API (retried via _transcribe_raw)
            file_size_mb = len(audio_data) / (1024 * 1024)
            self.logger.info(
                f"Sending audio to Deepgram: {path.name} ({file_size_mb:.2f}MB, timeout={self.timeout}s)"
            )
            response = await self._transcribe_raw(audio_data, path, dg_options)

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
        except Exception as e:  # safety-net: Deepgram SDK may raise various exception types
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
        """Extract transcript text from Deepgram response.

        Uses utterances (split by silence gaps) to create paragraph breaks.
        Falls back to flat channel transcript if utterances are unavailable.
        """
        # Prefer utterances — each becomes a paragraph separated by blank lines
        try:
            utterances = response.results.utterances
            if utterances and len(utterances) > 0:
                paragraphs = [u.transcript.strip() for u in utterances if u.transcript.strip()]
                if paragraphs:
                    return "\n\n".join(paragraphs)
        except (AttributeError, IndexError):  # fmt: skip
            pass

        # Fallback: flat transcript from channel alternatives
        try:
            channels = response.results.channels
            if channels and len(channels) > 0:
                alternatives = channels[0].alternatives
                if alternatives and len(alternatives) > 0:
                    return alternatives[0].transcript or ""
        except (AttributeError, IndexError):  # fmt: skip
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
        except (AttributeError, IndexError, TypeError):  # fmt: skip
            pass
        return 0.0

    def _extract_duration(self, response: Any) -> float:
        """Extract audio duration from Deepgram response."""
        try:
            return float(response.metadata.duration or 0.0)
        except (AttributeError, TypeError):  # fmt: skip
            pass
        return 0.0


__all__ = ["DeepgramAdapter"]

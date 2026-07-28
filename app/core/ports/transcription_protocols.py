"""
Transcription Protocols
=======================

The audio-transcription boundary (W1 / ADR-044, ADR-063). Keeps the vendor SDK
(``deepgram``) out of ``core/`` — core depends only on ``TranscriptionPort`` and
the core-owned ``TranscriptionResult`` DTO; the SDK client, response parsing, and
error mapping are the adapter's concern.

This closes the last ADR-063 asymmetry: the LLM (``ChatCompletionPort``) and
embeddings (``EmbeddingClientOperations``) inference clients already sat behind
core ports, but transcription typed against the concrete ``DeepgramAdapter``.
Now it has a port too, so all three external model-call boundaries are uniform.

Implementation: adapters/external/deepgram/adapter.py (DeepgramAdapter)
Consumers: TranscriptionService, BatchTranscriptionService, UserEntryProcessingService
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from pathlib import Path

    from core.models.transcription.transcription import TranscriptionProcessOptions


@dataclass(frozen=True)
class TranscriptionResult:
    """A transcript returned by a transcription provider.

    The normalized fields (``transcript_text`` … ``word_count``) are what core
    consumers read; ``raw_response`` carries the provider's full response dict
    when available, for debugging / downstream extraction.
    """

    transcript_text: str
    confidence_score: float
    duration_seconds: float
    word_count: int
    # boundary: provider's raw JSON response — heterogeneous, debugging/extraction only
    raw_response: dict[str, Any] | None = None


@runtime_checkable
class TranscriptionPort(Protocol):
    """Provider-agnostic audio-transcription boundary.

    The vendor SDK lives in the adapter; the core-owned
    ``TranscriptionProcessOptions`` tunes a single transcription without the
    caller naming a provider. It replaced a ``**overrides: Any`` bag whose
    documented keys were ``DeepgramConfig`` field names — a provider leak in a
    port whose whole point is that the caller need not know the provider.
    Everything not in the options model comes from ``config/deepgram.toml``
    inside the adapter, which is where the remaining knobs already lived.
    """

    async def transcribe(
        self,
        audio_path: str | Path,
        options: TranscriptionProcessOptions | None = None,
    ) -> Result[TranscriptionResult]:
        """Transcribe an audio file.

        ``options`` overrides the provider's configured defaults for this call
        only; ``None`` uses the configuration as-is.

        Returns ``Result.ok(TranscriptionResult)`` or
        ``Result.fail(integration_error)``. File-read and transport errors are
        the adapter's concern.
        """
        ...


__all__ = ["TranscriptionPort", "TranscriptionResult"]

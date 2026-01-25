"""
Deepgram API Integration
========================

Thin adapter and protocols for Deepgram audio transcription API.

Components:
- DeepgramAdapter: Thin wrapper for API calls (audio → transcript)
- Protocols: Type-safe duck typing for response objects

Usage:
    from adapters.external.deepgram import DeepgramAdapter

    adapter = DeepgramAdapter(api_key="...")
    result = await adapter.transcribe("/path/to/audio.mp3")
    if result.is_ok:
        print(result.value.transcript_text)

ARCHITECTURE (December 2025):
DeepgramAdapter is a thin adapter, NOT a service. It has no business logic,
no state management, no persistence. Just API calls.
"""

from typing import Any, Protocol, runtime_checkable

from adapters.external.deepgram.adapter import DeepgramAdapter, TranscriptionResult


@runtime_checkable
class DeepgramResults(Protocol):
    """Protocol for Deepgram API results container."""

    results: Any


@runtime_checkable
class DeepgramChannels(Protocol):
    """Protocol for Deepgram API channels container."""

    channels: Any


@runtime_checkable
class DeepgramAlternatives(Protocol):
    """Protocol for Deepgram API alternatives container."""

    alternatives: Any


@runtime_checkable
class DeepgramTranscript(Protocol):
    """Protocol for Deepgram API transcript text."""

    transcript: str


@runtime_checkable
class DeepgramMetadata(Protocol):
    """Protocol for Deepgram API metadata container."""

    metadata: Any


@runtime_checkable
class DeepgramDuration(Protocol):
    """Protocol for Deepgram API duration value."""

    duration: float


@runtime_checkable
class DeepgramConfidence(Protocol):
    """Protocol for Deepgram API confidence score."""

    confidence: float


__all__ = [
    # Adapter (primary export)
    "DeepgramAdapter",
    # Protocols (for type checking)
    "DeepgramAlternatives",
    "DeepgramChannels",
    "DeepgramConfidence",
    "DeepgramDuration",
    "DeepgramMetadata",
    "DeepgramResults",
    "DeepgramTranscript",
    "TranscriptionResult",
]

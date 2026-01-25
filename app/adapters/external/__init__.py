"""
External Service Adapters
=========================

Adapters for external third-party APIs and services.

Structure:
- deepgram/: Audio transcription service protocols and adapters
"""

from .deepgram import (
    DeepgramAlternatives,
    DeepgramChannels,
    DeepgramConfidence,
    DeepgramDuration,
    DeepgramMetadata,
    DeepgramResults,
    DeepgramTranscript,
)

__all__ = [
    "DeepgramAlternatives",
    "DeepgramChannels",
    "DeepgramConfidence",
    "DeepgramDuration",
    "DeepgramMetadata",
    "DeepgramResults",
    "DeepgramTranscript",
]

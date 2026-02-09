"""
Transcription Domain Models
===========================

Simplified model for audio transcription: audio file -> Deepgram -> text.
"""

from .transcription import (
    Transcription,
    TranscriptionCreateRequest,
    TranscriptionProcessOptions,
    TranscriptionStatus,
)

__all__ = [
    "Transcription",
    "TranscriptionCreateRequest",
    "TranscriptionProcessOptions",
    "TranscriptionStatus",
]

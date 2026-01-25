"""
Transcription Service Module - Simplified
==========================================

Single, focused service for audio transcription.
Core Purpose: Audio file → Deepgram → Text

ARCHITECTURE (December 2025):
- TranscriptionService: 8 core methods (~300 lines)
- DeepgramAdapter: Thin wrapper for API calls (~150 lines)
- Event-driven: Publishes TranscriptionCompleted for downstream services

Total: ~450 lines (was 1843 lines)
"""

from core.services.transcription.transcription_service import TranscriptionService

__all__ = ["TranscriptionService"]

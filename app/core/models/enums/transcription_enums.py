"""
Transcription Enums - Single Source of Truth
=============================================

Consolidated enums for the Transcription domain (January 2026).
Previously duplicated in transcription_dto.py and transcription_pure.py.

Per One Path Forward: One definition, imported everywhere.
"""

from enum import Enum


class ProcessingStatus(Enum):
    """Status of content processing pipeline."""

    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


class AudioFormat(Enum):
    """Supported audio formats."""

    MP3 = "mp3"
    WAV = "wav"
    M4A = "m4a"
    WEBM = "webm"
    OGG = "ogg"
    FLAC = "flac"


class TranscriptionService(Enum):
    """Available transcription services."""

    DEEPGRAM = "deepgram"
    WHISPER = "whisper"
    GOOGLE = "google"
    AZURE = "azure"
    AWS = "aws"


class LanguageCode(Enum):
    """Supported language codes."""

    EN = "en"
    ES = "es"
    FR = "fr"
    DE = "de"
    IT = "it"
    PT = "pt"
    RU = "ru"
    ZH = "zh"
    JA = "ja"
    KO = "ko"
    AR = "ar"
    HI = "hi"

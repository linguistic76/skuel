"""
Journal Domain Events
======================

Events published when journal operations occur.

Journal is a standalone domain — these events are separate from submission events.

Pipeline: JE_INPUT(audio) → Deepgram → JE_INPUT(text) → LLM → JE_OUTPUT
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class JeInputCreated(BaseEvent):
    """
    Published when a new journal entry input is created.

    Triggers:
    - Processing pipeline (Deepgram for audio, LLM for text)
    - User activity tracking
    """

    je_input_uid: str
    user_uid: str
    occurred_at: datetime
    file_type: str | None = None  # MIME type
    file_size: int | None = None
    original_filename: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "journal.input_created"


@dataclass(frozen=True)
class JeInputProcessingStarted(BaseEvent):
    """Published when processing begins for a journal entry input."""

    je_input_uid: str
    user_uid: str
    processor_type: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "journal.input_processing_started"


@dataclass(frozen=True)
class JeInputProcessingCompleted(BaseEvent):
    """Published when journal input processing completes (transcription or text cleanup)."""

    je_input_uid: str
    user_uid: str
    has_processed_content: bool
    processing_duration_seconds: float | None
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "journal.input_processing_completed"


@dataclass(frozen=True)
class JeOutputGenerated(BaseEvent):
    """
    Published when an LLM-processed journal output is created.

    The je_output is a transformation of a je_input — not a report or analysis.
    """

    je_output_uid: str
    je_input_uid: str
    user_uid: str
    enrichment_mode: str
    occurred_at: datetime
    output_file_path: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "journal.output_generated"


@dataclass(frozen=True)
class JeInputDeleted(BaseEvent):
    """Published when a journal entry input is deleted."""

    je_input_uid: str
    user_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "journal.input_deleted"

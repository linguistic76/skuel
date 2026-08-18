"""
UserEntry Domain Events (ADR-054)
=================================

Events published across the unified ``UserEntry`` lifecycle — the single
entry point that replaced the legacy Submission + Journal event streams.
"""

from dataclasses import dataclass
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


@dataclass(frozen=True)
class UserEntryCreated(BaseEvent):
    """Published when a new UserEntry is persisted."""

    entity_uid: str
    user_uid: UserUID
    pipeline: str  # Pipeline enum value
    modality: str | None = None  # SubmissionModality enum value
    fulfills_exercise_uid: str | None = None
    transforms_of_uid: str | None = None
    file_type: str | None = None

    event_type: ClassVar[str] = "user_entry.created"


@dataclass(frozen=True)
class UserEntryProcessingStarted(BaseEvent):
    """Published when the pipeline begins processing a UserEntry."""

    entity_uid: str
    user_uid: UserUID
    pipeline: str

    event_type: ClassVar[str] = "user_entry.processing_started"


@dataclass(frozen=True)
class UserEntryProcessingCompleted(BaseEvent):
    """Published when pipeline processing finishes successfully.

    ``produced_entry_uid`` is populated for TRANSCRIBE_AND_STRUCTURE, which
    writes an LLM-structured child entry alongside the raw transcript.
    """

    entity_uid: str
    user_uid: UserUID
    pipeline: str
    produced_entry_uid: str | None = None

    event_type: ClassVar[str] = "user_entry.processing_completed"


@dataclass(frozen=True)
class UserEntryProcessingFailed(BaseEvent):
    """Published when pipeline processing fails.

    ``failed_phase`` identifies which stage of a multi-phase pipeline broke.
    For ``TRANSCRIBE_AND_STRUCTURE`` the phases are ``transcribe`` (Deepgram),
    ``update_source`` (persist transcript on source entry), ``structure``
    (LLM structuring), and ``persist_child`` (create child entry). Single-
    phase pipelines emit the phase name of their only step. Left ``None``
    only when failure occurs before any phase dispatch (e.g. missing adapter).
    """

    entity_uid: str
    user_uid: UserUID
    pipeline: str
    error: str
    failed_phase: str | None = None

    event_type: ClassVar[str] = "user_entry.processing_failed"

"""
Embedding Request Events
=========================

Events for async embedding generation requests.

Published when entities are created via UX, consumed by background worker
for batch embedding generation.

Architecture:
- Zero latency impact on user creation
- Batch processing for efficiency
- Graceful degradation if worker unavailable
"""

from dataclasses import dataclass
from datetime import datetime

from core.events.base import BaseEvent
from core.models.type_hints import EntityUID


@dataclass(frozen=True)
class EmbeddingRequested(BaseEvent):
    """
    Base event for embedding generation requests.

    Published after entity creation, consumed by background worker.
    Carries no ownership attribution: embeddings are stored as properties on
    nodes that already carry ``user_uid``, so the worker needs only the UID,
    type, and text.
    """

    entity_uid: EntityUID
    entity_type: str  # "task", "goal", etc.
    embedding_text: str
    requested_at: datetime

    @property
    def event_type(self) -> str:
        return "embedding.requested"


@dataclass(frozen=True)
class TaskEmbeddingRequested(EmbeddingRequested):
    """Task-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "task.embedding_requested"


@dataclass(frozen=True)
class GoalEmbeddingRequested(EmbeddingRequested):
    """Goal-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "goal.embedding_requested"


@dataclass(frozen=True)
class HabitEmbeddingRequested(EmbeddingRequested):
    """Habit-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "habit.embedding_requested"


@dataclass(frozen=True)
class EventEmbeddingRequested(EmbeddingRequested):
    """Event-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "event.embedding_requested"


@dataclass(frozen=True)
class ChoiceEmbeddingRequested(EmbeddingRequested):
    """Choice-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "choice.embedding_requested"


@dataclass(frozen=True)
class PrincipleEmbeddingRequested(EmbeddingRequested):
    """Principle-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "principle.embedding_requested"


@dataclass(frozen=True)
class KuEmbeddingRequested(EmbeddingRequested):
    """Ku-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "ku.embedding_requested"


@dataclass(frozen=True)
class ResourceEmbeddingRequested(EmbeddingRequested):
    """Resource-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "resource.embedding_requested"


@dataclass(frozen=True)
class ExerciseEmbeddingRequested(EmbeddingRequested):
    """Exercise-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "exercise.embedding_requested"


@dataclass(frozen=True)
class PathStepEmbeddingRequested(EmbeddingRequested):
    """PathStep-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "path_step.embedding_requested"


@dataclass(frozen=True)
class LearningPathEmbeddingRequested(EmbeddingRequested):
    """LearningPath-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "learning_path.embedding_requested"


@dataclass(frozen=True)
class RevisedExerciseEmbeddingRequested(EmbeddingRequested):
    """RevisedExercise-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "revised_exercise.embedding_requested"


@dataclass(frozen=True)
class UserEntryEmbeddingRequested(EmbeddingRequested):
    """UserEntry-specific embedding request.

    Pipeline-scoped at the publisher: only ``pipeline=knowledge`` entries
    (knowledge/ + consented je_pro/ notes) publish — UserEntryService gates
    before calling the chokepoint, so exercise turn-ins, teacher-review
    submissions, and LLM outputs never embed.
    """

    @property
    def event_type(self) -> str:
        return "user_entry.embedding_requested"

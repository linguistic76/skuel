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


@dataclass(frozen=True)
class EmbeddingRequested(BaseEvent):
    """
    Base event for embedding generation requests.

    Published after entity creation, consumed by background worker.
    """

    entity_uid: str
    entity_type: str  # "task", "goal", etc.
    embedding_text: str
    user_uid: str
    requested_at: datetime
    occurred_at: datetime

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
class ArticleEmbeddingRequested(EmbeddingRequested):
    """Article-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "article.embedding_requested"


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
class LearningStepEmbeddingRequested(EmbeddingRequested):
    """LearningStep-specific embedding request."""

    @property
    def event_type(self) -> str:
        return "learning_step.embedding_requested"


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

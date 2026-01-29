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

from core.events.base import DomainEvent


@dataclass(frozen=True)
class EmbeddingRequested(DomainEvent):
    """
    Base event for embedding generation requests.

    Published after entity creation, consumed by background worker.
    """

    entity_uid: str
    entity_type: str  # "task", "goal", etc.
    embedding_text: str
    user_uid: str
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

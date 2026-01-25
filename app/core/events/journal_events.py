"""
Journal Domain Events
=====================

Events published when journal operations occur.

These events enable:
- User context invalidation when journals change
- Mood/sentiment tracking over time
- Learning insights from journal content
- Cross-domain reflection tracking

Version: 1.0.0
Date: 2025-10-16
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class JournalCreated(BaseEvent):
    """
    Published when a new journal entry is created.

    Triggers:
    - User context invalidation (new reflection data)
    - Mood/sentiment tracking updates
    - Learning insights generation
    - Theme extraction and analysis
    """

    journal_uid: str
    user_uid: str
    title: str
    content_length: int
    has_summary: bool
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "journal.created"


@dataclass(frozen=True)
class JournalUpdated(BaseEvent):
    """
    Published when a journal entry is updated.

    Triggers:
    - User context invalidation (journal content changed)
    - Re-extraction of themes/insights
    - Sentiment re-analysis
    """

    journal_uid: str
    user_uid: str
    updated_fields: dict[str, Any]
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "journal.updated"


@dataclass(frozen=True)
class JournalDeleted(BaseEvent):
    """
    Published when a journal entry is deleted.

    Triggers:
    - User context invalidation (reflection history changes)
    - Mood tracking recalculation
    - Theme history updates
    """

    journal_uid: str
    user_uid: str
    title: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "journal.deleted"

"""
Report AI Processing Types
===========================

Frozen dataclasses for report AI processing returns.
Replaces dict[str, Any] with strongly-typed, immutable structures.

Migrated from journals_types.py (February 2026 — Journal→Report merge).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReportProcessingContext:
    """
    Context gathered from Neo4j for intelligent report/journal editing.

    Used by TranscriptProcessorService to provide context-aware editing.
    """

    user_uid: str
    gathered_at: str
    recent_journals: list[dict[str, str]] = field(default_factory=list)
    active_goals: list[dict[str, str]] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    mood_trends: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReportAIInsights:
    """Parsed AI response for report/journal formatting."""

    title: str
    formatted_content: str
    summary: str
    themes: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    edits_summary: str = ""
    context_summary: str | None = None

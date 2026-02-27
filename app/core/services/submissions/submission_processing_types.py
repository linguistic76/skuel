"""
Ku AI Processing Types
========================

Frozen dataclasses for Ku AI processing returns.
Replaces dict[str, Any] with strongly-typed, immutable structures.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReportsProcessingContext:
    """
    Context gathered from Neo4j for intelligent Ku editing.

    Used by ContentEnrichmentService to provide context-aware editing.
    """

    user_uid: str
    gathered_at: str
    recent_journals: list[dict[str, str]] = field(default_factory=list)
    active_goals: list[dict[str, str]] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    mood_trends: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReportsAIInsights:
    """Parsed AI response for entity formatting."""

    title: str
    formatted_content: str
    summary: str
    themes: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    edits_summary: str = ""
    context_summary: str | None = None

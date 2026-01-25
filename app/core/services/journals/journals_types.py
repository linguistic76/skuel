"""
Journals AI Processing Types (Pattern 3C Migration)
=====================================================

Frozen dataclasses for journals AI processing returns.
Replaces dict[str, Any] with strongly-typed, immutable structures.

Pattern 3C Phase 1: High-Priority Public API Types
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class JournalContext:
    """
    Context gathered from Neo4j for intelligent journal editing.

    Enhanced in Step 1 Implementation (November 2025) with:
    - Active goals for goal progress tracking
    - Recent topics for thematic continuity
    - Mood trends for emotional pattern awareness
    """

    user_uid: str
    gathered_at: str
    recent_journals: list[dict[str, str]] = field(default_factory=list)
    active_goals: list[dict[str, str]] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    mood_trends: dict[str, Any] | None = None


@dataclass(frozen=True)
class JournalAIInsights:
    """Parsed AI response for journal formatting."""

    title: str
    formatted_content: str
    summary: str
    themes: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    edits_summary: str = ""
    context_summary: str | None = None

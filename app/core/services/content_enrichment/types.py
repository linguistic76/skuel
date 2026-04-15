"""
Content Enrichment Types
========================

Frozen dataclasses for the LLM-driven transcript enrichment pipeline.
Ported from ``submissions/submission_processing_types.py`` on ADR-054
Commit 6a (Step 10) and renamed so that the content_enrichment package is
no longer coupled to the legacy Submission naming.
"""

from dataclasses import dataclass, field
from typing import Any

from core.models.type_hints import UserUID


@dataclass(frozen=True)
class EnrichmentContext:
    """Neo4j-gathered context consumed by ContentEnrichmentService."""

    user_uid: UserUID
    gathered_at: str
    recent_journals: list[dict[str, str]] = field(default_factory=list)
    active_goals: list[dict[str, str]] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    mood_trends: dict[str, Any] | None = None


@dataclass(frozen=True)
class EnrichmentInsights:
    """Parsed LLM response produced by the enrichment pipeline."""

    title: str
    formatted_content: str
    summary: str
    themes: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    edits_summary: str = ""
    context_summary: str | None = None

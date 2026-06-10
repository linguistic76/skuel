"""
Content Enrichment Types
========================

Frozen dataclasses for the LLM-driven transcript enrichment pipeline.
Ported from the legacy ``submissions/submission_processing_types.py`` on
ADR-054 and renamed so that the content_enrichment package is no longer
coupled to the legacy Submission naming.
"""

from dataclasses import dataclass, field

from core.models.type_hints import UserUID


@dataclass(frozen=True)
class EnrichmentContext:
    """Neo4j-gathered context consumed by ContentEnrichmentService.

    Active goals are the only live enrichment signal: ADR-054 dismantled the
    rich-journal model (``mood``/``energy_level``/``key_topics``/``entry_date``
    were dropped from ``UserEntry``), so the former recent-journals, topic, and
    mood-trend fields read gone properties and have been removed.
    """

    user_uid: UserUID
    gathered_at: str
    active_goals: list[dict[str, str]] = field(default_factory=list)


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

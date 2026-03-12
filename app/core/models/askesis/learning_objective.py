"""
Structured Learning Objective — Curriculum-Aligned Assessment Target
=====================================================================

Extends string-based learning_objectives with structured assessment data.
Progressive enhancement: when populated, the Socratic engine uses structured
objectives for evaluation rubrics. When empty, falls back to string
learning_objectives from the Article.

See: /docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StructuredLearningObjective:
    """A single learning objective with assessment metadata.

    Used by the EvaluationEngine to assess learner responses against
    specific, measurable criteria rather than comparing free text.

    Fields:
        statement: The objective text (e.g., "Explain why breath is used as anchor")
        assessment_type: How to assess (conceptual | procedural | reflective)
        evidence_markers: Keywords/phrases a correct response should contain
        depth_levels: {surface: "...", functional: "...", deep: "..."} rubric
        ku_uid: KU this objective targets (for scoped evaluation)
    """

    statement: str
    assessment_type: str = "conceptual"  # conceptual | procedural | reflective
    evidence_markers: tuple[str, ...] = ()
    depth_levels: dict[str, str] = field(default_factory=dict)
    ku_uid: str | None = None

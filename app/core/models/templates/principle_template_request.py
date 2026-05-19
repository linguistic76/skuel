"""
PrincipleTemplate Request Models — API Validation (Tier 1, External)
=====================================================================

Pydantic models at the API boundary for PrincipleTemplate create/update.

``expressions`` (tuple[PrincipleExpression, ...] on the core model) require
FormGenerator nested-dataclass support; the schema accepts them as
``list[dict]`` for forward-compatibility, and the converter coerces shape.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from core.models.enums import EntityStatus
from core.models.enums.principle_enums import (
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.request_base import UpdateRequestBase
from core.models.templates._template_request_base import TemplateCreateRequest


class PrincipleTemplateCreateRequest(TemplateCreateRequest):
    """External API request for creating a PrincipleTemplate."""

    description: str | None = None
    tags: list[str] = Field(default_factory=list)

    statement: str | None = None

    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    tradition: str | None = None
    original_source: str | None = None
    personal_interpretation: str | None = None

    expressions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Authored expression structure (cloned to instance)",
    )
    key_behaviors: list[str] = Field(default_factory=list)

    potential_conflicts: list[str] = Field(default_factory=list)
    conflicting_principles: list[str] = Field(default_factory=list)
    resolution_strategies: list[str] = Field(default_factory=list)

    origin_story: str | None = None
    evolution_notes: str | None = None


class PrincipleTemplateUpdateRequest(UpdateRequestBase):
    """External API request for updating a PrincipleTemplate."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: EntityStatus | None = None
    tags: list[str] | None = None

    statement: str | None = None

    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    tradition: str | None = None
    original_source: str | None = None
    personal_interpretation: str | None = None

    expressions: list[dict[str, Any]] | None = None
    key_behaviors: list[str] | None = None

    potential_conflicts: list[str] | None = None
    conflicting_principles: list[str] | None = None
    resolution_strategies: list[str] | None = None

    origin_story: str | None = None
    evolution_notes: str | None = None

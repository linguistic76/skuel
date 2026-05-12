"""
ChoiceTemplate Request Models — API Validation (Tier 1, External)
==================================================================

Pydantic models at the API boundary for ChoiceTemplate create/update endpoints.

``options`` (tuple[ChoiceOption, ...] on the core model) require
FormGenerator nested-dataclass support. The schema accepts them as
``list[dict]``; the converter coerces values into ``ChoiceOption`` instances.
For Phase 5 V1 a default empty list works; UI authoring is the use case
that exercises the full nested shape.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from core.models.enums import EntityStatus
from core.models.enums.choice_enums import ChoiceType
from core.models.request_base import UpdateRequestBase
from core.models.templates._template_request_base import TemplateCreateRequest
from core.models.templates.relative_offset_dto import RelativeOffsetDTO


class ChoiceTemplateCreateRequest(TemplateCreateRequest):
    """External API request for creating a ChoiceTemplate."""

    description: str | None = None
    tags: list[str] = Field(default_factory=list)

    choice_type: ChoiceType | None = None
    options: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Authored option blueprints (cloned to instance)",
    )
    decision_rationale: str | None = None
    decision_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)

    decision_deadline_offset: RelativeOffsetDTO | None = None

    inspiration_type: str | None = None
    expands_possibilities: bool = False


class ChoiceTemplateUpdateRequest(UpdateRequestBase):
    """External API request for updating a ChoiceTemplate."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: EntityStatus | None = None
    tags: list[str] | None = None

    choice_type: ChoiceType | None = None
    options: list[dict[str, Any]] | None = None
    decision_rationale: str | None = None
    decision_criteria: list[str] | None = None
    constraints: list[str] | None = None
    stakeholders: list[str] | None = None

    decision_deadline_offset: RelativeOffsetDTO | None = None

    inspiration_type: str | None = None
    expands_possibilities: bool | None = None

"""
PrincipleTemplate — PS-Owned Principle Spawn Blueprint
=======================================================

Frozen dataclass for principle templates (EntityType.PRINCIPLE_TEMPLATE).
PS-owned via ``HAS_PRINCIPLE_TEMPLATE``. Spawns a Principle instance when the
owning PS is engaged.

PrincipleTemplate is Layer 0 in spawn order — no cross-template references.

Excludes per-user state (current_alignment, alignment_history, last_review_date,
adopted_date, is_active) since those track student adoption of the principle
and are populated on the spawned Principle, not authored on the template.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.principle_enums import (
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.principle.principle_types import PrincipleExpression

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.templates.principle_template_dto import PrincipleTemplateDTO


@dataclass(frozen=True, kw_only=True)
class PrincipleTemplate(Entity):
    """Immutable domain model for principle templates (EntityType.PRINCIPLE_TEMPLATE)."""

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.PRINCIPLE_TEMPLATE, kw_only=True)

    def __post_init__(self) -> None:
        if self.entity_type != EntityType.PRINCIPLE_TEMPLATE:
            raise ValueError(
                f"PrincipleTemplate constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # STATEMENT
    # =========================================================================
    statement: str | None = None

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    # =========================================================================
    # PHILOSOPHICAL CONTEXT
    # =========================================================================
    tradition: str | None = None
    original_source: str | None = None
    personal_interpretation: str | None = None

    # =========================================================================
    # EXPRESSIONS & APPLICATIONS
    # =========================================================================
    expressions: tuple[PrincipleExpression, ...] = ()
    key_behaviors: tuple[str, ...] = ()

    # =========================================================================
    # CONFLICTS & TENSIONS (authoring-time hints; cloned to instance)
    # =========================================================================
    potential_conflicts: tuple[str, ...] = ()
    conflicting_principles: tuple[str, ...] = ()
    resolution_strategies: tuple[str, ...] = ()

    # =========================================================================
    # AUTHORING REFLECTION (template-side narrative)
    # =========================================================================
    origin_story: str | None = None
    evolution_notes: str | None = None

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: EntityDTO | PrincipleTemplateDTO) -> PrincipleTemplate:
        return cls._from_dto(dto)

    def to_dto(self) -> PrincipleTemplateDTO:
        from core.models.dto_helpers import domain_to_dto
        from core.models.templates.principle_template_dto import PrincipleTemplateDTO

        return domain_to_dto(self, PrincipleTemplateDTO)

    def __str__(self) -> str:
        return (
            f"PrincipleTemplate(uid={self.uid}, title='{self.title}', "
            f"category={self.principle_category})"
        )

    def __repr__(self) -> str:
        return (
            f"PrincipleTemplate(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, principle_category={self.principle_category})"
        )

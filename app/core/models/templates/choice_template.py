"""
ChoiceTemplate — PS-Owned Choice Spawn Blueprint
================================================

Frozen dataclass for choice templates (EntityType.CHOICE_TEMPLATE). PS-owned
via ``HAS_CHOICE_TEMPLATE``. Spawns a Choice instance when the owning PS is
engaged.

ChoiceTemplate is Layer 0 in spawn order — no cross-template references.
GoalTemplates can reference a ChoiceTemplate (and one of its options) via
``inspired_by_choice_template_uid`` / ``selected_choice_option_template_uid``.

Excludes per-user state (selected_option_uid, decided_at, satisfaction_score,
actual_outcome, lessons_learned) since those are populated as the student
makes the decision on the spawned Choice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.models.choice.choice_option import ChoiceOption
from core.models.entity import Entity
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityType
from core.models.templates.relative_offset import RelativeOffset

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.templates.choice_template_dto import ChoiceTemplateDTO


@dataclass(frozen=True, kw_only=True)
class ChoiceTemplate(Entity):
    """Immutable domain model for choice templates (EntityType.CHOICE_TEMPLATE)."""

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.CHOICE_TEMPLATE, kw_only=True)

    def __post_init__(self) -> None:
        if self.entity_type != EntityType.CHOICE_TEMPLATE:
            raise ValueError(
                f"ChoiceTemplate constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # DECISION FRAME
    # =========================================================================
    choice_type: ChoiceType | None = None
    options: tuple[ChoiceOption, ...] = ()
    decision_rationale: str | None = None
    decision_criteria: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    stakeholders: tuple[str, ...] = ()

    # =========================================================================
    # TIMING (engagement-relative)
    # =========================================================================
    decision_deadline_offset: RelativeOffset | None = None

    # =========================================================================
    # CURRICULUM INTEGRATION
    # =========================================================================
    inspiration_type: str | None = None
    expands_possibilities: bool = False

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: EntityDTO | ChoiceTemplateDTO) -> ChoiceTemplate:
        return cls._from_dto(dto)

    def to_dto(self) -> ChoiceTemplateDTO:
        from core.models.dto_helpers import domain_to_dto
        from core.models.templates.choice_template_dto import ChoiceTemplateDTO

        return domain_to_dto(self, ChoiceTemplateDTO)

    def __str__(self) -> str:
        return f"ChoiceTemplate(uid={self.uid}, title='{self.title}', type={self.choice_type})"

    def __repr__(self) -> str:
        return (
            f"ChoiceTemplate(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, choice_type={self.choice_type})"
        )

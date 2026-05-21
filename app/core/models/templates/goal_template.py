"""
GoalTemplate — PS-Owned Goal Spawn Blueprint
============================================

Frozen dataclass for goal templates (EntityType.GOAL_TEMPLATE). PS-owned via
``HAS_GOAL_TEMPLATE``. Spawns a Goal instance when the owning PS is engaged.

Excludes per-user progress fields (current_value, progress_percentage,
progress_history, last_progress_update, achieved_date, milestones-as-instance-state)
since those are populated by the spawned Goal as the student tracks progress.
``milestones`` are kept as authored content (the template author defines milestone
structure; instance milestones are spawned alongside the goal).

See:
    project_engage_pathstep_contract.md (memory)
    project_template_relative_offset.md (memory)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.goal.milestone import Milestone
from core.models.templates.relative_offset import RelativeOffset

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.templates.goal_template_dto import GoalTemplateDTO


@dataclass(frozen=True, kw_only=True)
class GoalTemplate(Entity):
    """Immutable domain model for goal templates (EntityType.GOAL_TEMPLATE)."""

    def __post_init__(self) -> None:
        if self.entity_type != EntityType.GOAL_TEMPLATE:
            object.__setattr__(self, "entity_type", EntityType.GOAL_TEMPLATE)
        super().__post_init__()

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    # =========================================================================
    # MEASUREMENT (target only — current_value is instance state)
    # =========================================================================
    target_value: float | None = None
    unit_of_measurement: str | None = None

    # =========================================================================
    # TIMELINE (engagement-relative)
    # =========================================================================
    start_offset: RelativeOffset | None = None
    target_offset: RelativeOffset | None = None

    # =========================================================================
    # AUTHORED MILESTONES (structure — instance receives a clone)
    # =========================================================================
    milestones: tuple[Milestone, ...] = ()

    # =========================================================================
    # MOTIVATION
    # =========================================================================
    vision_statement: str | None = None
    why_important: str | None = None
    success_criteria: str | None = None
    potential_obstacles: tuple[str, ...] = ()
    strategies: tuple[str, ...] = ()

    # =========================================================================
    # CROSS-TEMPLATE REFERENCES
    # =========================================================================
    fulfills_goal_template_uid: str | None = None  # Sub-goal template → parent
    inspired_by_choice_template_uid: str | None = None
    selected_choice_option_template_uid: str | None = None

    # =========================================================================
    # IDENTITY
    # =========================================================================
    target_identity: str | None = None
    identity_evidence_required: int = 0

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: EntityDTO | GoalTemplateDTO) -> GoalTemplate:
        return cls._from_dto(dto)

    def to_dto(self) -> GoalTemplateDTO:
        from core.models.dto_helpers import domain_to_dto
        from core.models.templates.goal_template_dto import GoalTemplateDTO

        return domain_to_dto(self, GoalTemplateDTO)

    def __str__(self) -> str:
        return f"GoalTemplate(uid={self.uid}, title='{self.title}', target={self.target_offset})"

    def __repr__(self) -> str:
        return (
            f"GoalTemplate(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, goal_type={self.goal_type})"
        )

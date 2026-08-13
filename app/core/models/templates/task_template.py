"""
TaskTemplate — PS-Owned Task Spawn Blueprint
============================================

Frozen dataclass for task templates (EntityType.TASK_TEMPLATE).

A TaskTemplate is curriculum content authored by an admin/teacher and owned by
a PathStep via the ``HAS_TASK_TEMPLATE`` edge. When a student engages the
owning PathStep, the engagement service spawns a Task instance from this
template (see project_engage_pathstep_contract.md).

Hierarchy:
    Entity (~19 fields)
    └── TaskTemplate(Entity) +13 template-specific fields

Why Entity (not Curriculum)? Templates are authoring blueprints, not knowledge
content. Curriculum's substance tracking, learning_level, complexity, and
semantic_links live on the owning PathStep — TaskTemplate inherits that
context via the PS edge rather than duplicating it. Same precedent as
``FormTemplate`` (also Entity-direct, also PS-linked, also CURRICULUM origin).

Field shape vs Task (instance):
    - Absolute date fields → RelativeOffset (engagement-anchored)
    - Cross-domain ``*_uid`` refs → ``*_template_uid`` refs (resolved at spawn)
    - Per-user instance state (completion_date, actual_minutes, knowledge
      intelligence dicts) is not present — those are populated on the spawned
      Task by user actions, not authored on the template.

See:
    project_engage_pathstep_contract.md (memory)
    project_template_relative_offset.md (memory)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.templates.relative_offset import RelativeOffset

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.templates.task_template_dto import TaskTemplateDTO


@dataclass(frozen=True, kw_only=True)
class TaskTemplate(Entity):
    """Immutable domain model for task templates (EntityType.TASK_TEMPLATE)."""

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.TASK_TEMPLATE, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=TASK_TEMPLATE before delegating to Entity defaults."""
        if self.entity_type != EntityType.TASK_TEMPLATE:
            raise ValueError(
                f"TaskTemplate constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # SCHEDULING (engagement-relative)
    # =========================================================================
    due_offset: RelativeOffset | None = None
    scheduled_offset: RelativeOffset | None = None
    duration_minutes: int | None = None

    # Recurrence — end offset is engagement-relative.
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_offset: RelativeOffset | None = None

    # =========================================================================
    # HIERARCHY (template-side)
    # =========================================================================
    parent_template_uid: str | None = None  # Parent task template (same PS)
    project: str | None = None

    # =========================================================================
    # CROSS-TEMPLATE REFERENCES (resolved at spawn via instance map)
    # =========================================================================
    fulfills_goal_template_uid: str | None = None
    reinforces_habit_template_uid: str | None = None
    scheduled_event_template_uid: str | None = None

    # =========================================================================
    # PROGRESS IMPACT (copied as-is to spawned Task)
    # =========================================================================
    goal_progress_contribution: float = 0.0
    knowledge_mastery_check: bool = False
    habit_streak_maintainer: bool = False
    completion_updates_goal: bool = False

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: EntityDTO | TaskTemplateDTO) -> TaskTemplate:
        """Create TaskTemplate from an EntityDTO or TaskTemplateDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> TaskTemplateDTO:
        """Convert TaskTemplate to TaskTemplateDTO."""
        from core.models.dto_helpers import domain_to_dto
        from core.models.templates.task_template_dto import TaskTemplateDTO

        return domain_to_dto(self, TaskTemplateDTO)

    def __str__(self) -> str:
        return f"TaskTemplate(uid={self.uid}, title='{self.title}', due={self.due_offset})"

    def __repr__(self) -> str:
        return (
            f"TaskTemplate(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, due_offset={self.due_offset})"
        )

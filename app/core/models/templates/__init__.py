"""
Activity Templates — PS-Owned Authoring Models
==============================================

PathStep-owned templates that spawn user-owned Activity instances when a student
engages a PathStep. Templates are curriculum content (admin/teacher-authored,
shared); instances are user content. Lifecycle: Template -> Engaged -> Owned.

This package contains the shared value types used across the 6 *Template
entities (added in Phase 2). The 6 entities themselves live in their own
modules within this package.

Value types:
    RelativeOffset    — engagement-relative timing (days/hours/minutes from anchor)
    RelativeOffsetDTO — Pydantic companion for serialization at boundaries

See:
    /home/mike/.claude/plans/skip-when-do-idempotent-shell.md (build plan)
    project_template_relative_offset.md (memory)
    project_engage_pathstep_contract.md (memory)
    project_pathstep_lifecycle_contract.md (memory)
"""

from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.choice_template_dto import ChoiceTemplateDTO
from core.models.templates.event_template import EventTemplate
from core.models.templates.event_template_dto import EventTemplateDTO
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.goal_template_dto import GoalTemplateDTO
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.habit_template_dto import HabitTemplateDTO
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.principle_template_dto import PrincipleTemplateDTO
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.relative_offset_dto import RelativeOffsetDTO
from core.models.templates.task_template import TaskTemplate
from core.models.templates.task_template_dto import TaskTemplateDTO

__all__ = [
    "ChoiceTemplate",
    "ChoiceTemplateDTO",
    "EventTemplate",
    "EventTemplateDTO",
    "GoalTemplate",
    "GoalTemplateDTO",
    "HabitTemplate",
    "HabitTemplateDTO",
    "PrincipleTemplate",
    "PrincipleTemplateDTO",
    "RelativeOffset",
    "RelativeOffsetDTO",
    "TaskTemplate",
    "TaskTemplateDTO",
]

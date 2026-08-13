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
    project_template_relative_offset.md (memory)
    project_engage_pathstep_contract.md (memory)
    project_pathstep_lifecycle_contract.md (memory)
"""

from core.models.templates._template_request_base import TemplateCreateRequest
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.choice_template_dto import ChoiceTemplateDTO
from core.models.templates.choice_template_request import (
    ChoiceTemplateCreateRequest,
    ChoiceTemplateUpdateRequest,
)
from core.models.templates.event_template import EventTemplate
from core.models.templates.event_template_dto import EventTemplateDTO
from core.models.templates.event_template_request import (
    EventTemplateCreateRequest,
    EventTemplateUpdateRequest,
)
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.goal_template_dto import GoalTemplateDTO
from core.models.templates.goal_template_request import (
    GoalTemplateCreateRequest,
    GoalTemplateUpdateRequest,
)
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.habit_template_dto import HabitTemplateDTO
from core.models.templates.habit_template_request import (
    HabitTemplateCreateRequest,
    HabitTemplateUpdateRequest,
)
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.principle_template_dto import PrincipleTemplateDTO
from core.models.templates.principle_template_request import (
    PrincipleTemplateCreateRequest,
    PrincipleTemplateUpdateRequest,
)
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.relative_offset_dto import RelativeOffsetDTO
from core.models.templates.task_template import TaskTemplate
from core.models.templates.task_template_dto import TaskTemplateDTO
from core.models.templates.task_template_request import (
    TaskTemplateCreateRequest,
    TaskTemplateUpdateRequest,
)

__all__ = [
    "ChoiceTemplate",
    "ChoiceTemplateCreateRequest",
    "ChoiceTemplateDTO",
    "ChoiceTemplateUpdateRequest",
    "EventTemplate",
    "EventTemplateCreateRequest",
    "EventTemplateDTO",
    "EventTemplateUpdateRequest",
    "GoalTemplate",
    "GoalTemplateCreateRequest",
    "GoalTemplateDTO",
    "GoalTemplateUpdateRequest",
    "HabitTemplate",
    "HabitTemplateCreateRequest",
    "HabitTemplateDTO",
    "HabitTemplateUpdateRequest",
    "PrincipleTemplate",
    "PrincipleTemplateCreateRequest",
    "PrincipleTemplateDTO",
    "PrincipleTemplateUpdateRequest",
    "RelativeOffset",
    "RelativeOffsetDTO",
    "TaskTemplate",
    "TaskTemplateCreateRequest",
    "TaskTemplateDTO",
    "TaskTemplateUpdateRequest",
    "TemplateCreateRequest",
]

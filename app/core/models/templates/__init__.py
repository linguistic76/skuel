"""
Activity Templates — PS-Owned Curriculum Models
===============================================

PathStep-owned templates that spawn user-owned Activity instances when a student
engages a PathStep. Templates are curriculum content, authored as ``_tmpl.md``
files in the content vault; instances are user content. Lifecycle:
Template -> Engaged -> Owned.

This package contains the 6 *Template entities, their DTOs, and the shared
value type they use for timing.

Value type:
    RelativeOffset    — engagement-relative timing (days/hours/minutes from anchor)

See: /docs/guides/ACTIVITY_TEMPLATE_AUTHORING.md
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
    "TaskTemplate",
    "TaskTemplateDTO",
]

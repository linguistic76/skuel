"""TemplateBundle — typed aggregate of all templates attached to one PathStep.

Consumed by both ``_PsValidator`` and ``_SpawnOrchestrator`` — the facade loads
once via ``_TemplateLoader`` so neither consumer double-queries Neo4j.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from core.models.templates.choice_template import ChoiceTemplate
    from core.models.templates.event_template import EventTemplate
    from core.models.templates.goal_template import GoalTemplate
    from core.models.templates.habit_template import HabitTemplate
    from core.models.templates.principle_template import PrincipleTemplate
    from core.models.templates.task_template import TaskTemplate

# ---------------------------------------------------------------------------
# Template type name literals
# ---------------------------------------------------------------------------

_TaskTemplateType = Literal["TaskTemplate"]
_GoalTemplateType = Literal["GoalTemplate"]
_HabitTemplateType = Literal["HabitTemplate"]
_EventTemplateType = Literal["EventTemplate"]
_ChoiceTemplateType = Literal["ChoiceTemplate"]
_PrincipleTemplateType = Literal["PrincipleTemplate"]

TemplateTypeName = Literal[
    "TaskTemplate",
    "GoalTemplate",
    "HabitTemplate",
    "EventTemplate",
    "ChoiceTemplate",
    "PrincipleTemplate",
]


# ---------------------------------------------------------------------------
# TemplateBundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemplateBundle:
    """All templates attached to one PathStep, grouped by domain.

    The validator and the spawn orchestrator both consume this — loading is
    done once by the facade so we don't double-query Neo4j.
    """

    ps_uid: str
    tasks: tuple[TaskTemplate, ...]
    goals: tuple[GoalTemplate, ...]
    habits: tuple[HabitTemplate, ...]
    events: tuple[EventTemplate, ...]
    choices: tuple[ChoiceTemplate, ...]
    principles: tuple[PrincipleTemplate, ...]

    def all_uids(self) -> set[str]:
        """Every template UID attached to this PS, regardless of domain."""
        out: set[str] = set()
        for tt in self.tasks:
            out.add(str(tt.uid))
        for gt in self.goals:
            out.add(str(gt.uid))
        for ht in self.habits:
            out.add(str(ht.uid))
        for et in self.events:
            out.add(str(et.uid))
        for ct in self.choices:
            out.add(str(ct.uid))
        for pt in self.principles:
            out.add(str(pt.uid))
        return out

    def type_by_uid(self) -> dict[str, TemplateTypeName]:
        """Reverse index: template UID → declared type name."""
        out: dict[str, TemplateTypeName] = {}
        for tt in self.tasks:
            out[str(tt.uid)] = "TaskTemplate"
        for gt in self.goals:
            out[str(gt.uid)] = "GoalTemplate"
        for ht in self.habits:
            out[str(ht.uid)] = "HabitTemplate"
        for et in self.events:
            out[str(et.uid)] = "EventTemplate"
        for ct in self.choices:
            out[str(ct.uid)] = "ChoiceTemplate"
        for pt in self.principles:
            out[str(pt.uid)] = "PrincipleTemplate"
        return out

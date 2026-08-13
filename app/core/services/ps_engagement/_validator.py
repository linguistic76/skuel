"""_PsValidator — PS-save validation for Activity Templates.

Runs six checks:

1. ``target_missing`` — ``*_template_uid`` points to a template that doesn't
   exist (or isn't attached to this PS).
2. ``wrong_type`` — reference points to a template of the wrong domain
   (e.g. a TaskTemplate field pointing at a HabitTemplate UID).
3. ``self_reference`` — template references its own UID.
4. ``cross_ps`` — reference points to a template attached to a *different* PS.
5. ``cycle`` — within a single domain, ``parent_template_uid`` (Tasks only for
   V1) creates a cycle.
6. ``not_active`` — a template's status is not ``ACTIVE`` (still DRAFT or
   already ARCHIVED). Runs first; non-ACTIVE templates cannot be spawned.

Output is ``list[Violation]`` (TypedDict in core.ports.query_types). The facade
wraps a non-empty list with ``Errors.ps_validation_report()`` and returns it
as a ``BUSINESS`` error so the route layer can render ``details["violations"]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger

from ._template_bundle import TemplateBundle, TemplateTypeName

if TYPE_CHECKING:
    from core.ports.query_types import Violation

logger = get_logger(__name__)


# ============================================================================
# Cross-template reference field maps (per template type)
# ============================================================================
#
# Each entry is (field_name, expected_target_type). The validator iterates
# these per template, looks up the target by UID in the bundle, and emits a
# Violation if the target is missing or of the wrong type.

# (template_type, [(field_name, expected_target_type), ...])
TASK_REFS: list[tuple[str, TemplateTypeName]] = [
    ("fulfills_goal_template_uid", "GoalTemplate"),
    ("reinforces_habit_template_uid", "HabitTemplate"),
    ("scheduled_event_template_uid", "EventTemplate"),
    ("parent_template_uid", "TaskTemplate"),
]
GOAL_REFS: list[tuple[str, TemplateTypeName]] = [
    ("fulfills_goal_template_uid", "GoalTemplate"),
    ("inspired_by_choice_template_uid", "ChoiceTemplate"),
    ("selected_choice_option_template_uid", "ChoiceTemplate"),
]
EVENT_REFS: list[tuple[str, TemplateTypeName]] = [
    ("reinforces_habit_template_uid", "HabitTemplate"),
    ("milestone_celebration_for_goal_template_uid", "GoalTemplate"),
]
# Habit, Choice, Principle have no cross-template references in V1.

# Maps RelationshipName.HAS_*_TEMPLATE → template type name (for diagnostics).
HAS_TEMPLATE_RELS: dict[TemplateTypeName, RelationshipName] = {
    "TaskTemplate": RelationshipName.HAS_TASK_TEMPLATE,
    "GoalTemplate": RelationshipName.HAS_GOAL_TEMPLATE,
    "HabitTemplate": RelationshipName.HAS_HABIT_TEMPLATE,
    "EventTemplate": RelationshipName.HAS_EVENT_TEMPLATE,
    "ChoiceTemplate": RelationshipName.HAS_CHOICE_TEMPLATE,
    "PrincipleTemplate": RelationshipName.HAS_PRINCIPLE_TEMPLATE,
}


class _PsValidator:
    """PS-save validator — pure function, no I/O. Executor is unused for V1."""

    def __init__(self) -> None:
        self.logger = logger

    def validate(self, bundle: TemplateBundle) -> list[Violation]:
        """Run all six checks. Returns `[]` if the bundle is fully consistent."""
        from core.ports.query_types import Violation  # local — TypedDict, runtime ok

        violations: list[Violation] = []

        # 6. not_active — must run first; non-ACTIVE templates cannot be spawned.
        violations.extend(self._check_template_statuses(bundle))
        if violations:
            return violations

        uid_to_type = bundle.type_by_uid()
        valid_uids = bundle.all_uids()

        # Walk each template's cross-template references.
        for template_obj, refs in self._iter_refs(bundle):
            template: Any = template_obj  # heterogeneous tuple — relax typing
            for field_name, expected_type in refs:
                target_uid = getattr(template, field_name, None)
                if target_uid is None:
                    continue

                # 3. self-reference
                if target_uid == template.uid:
                    violations.append(
                        Violation(
                            template_uid=template.uid,
                            template_title=template.title,
                            template_type=uid_to_type[template.uid],
                            field=field_name,
                            violation="self_reference",
                            referenced_uid=target_uid,
                            hint=f"{field_name} cannot reference its own template",
                        )
                    )
                    continue

                # 1. target_missing OR 4. cross_ps (we collapse: anything not in
                # this PS's bundle is "target_missing" from the engagement
                # service's POV — cross-PS refs would also fail because the
                # bundle is PS-scoped).
                if target_uid not in valid_uids:
                    violations.append(
                        Violation(
                            template_uid=template.uid,
                            template_title=template.title,
                            template_type=uid_to_type[template.uid],
                            field=field_name,
                            violation="target_missing",
                            referenced_uid=target_uid,
                            hint=(
                                f"{expected_type} '{target_uid}' is not attached "
                                f"to PS {bundle.ps_uid} via "
                                f"{HAS_TEMPLATE_RELS[expected_type].value}"
                            ),
                        )
                    )
                    continue

                # 2. wrong_type
                actual_type = uid_to_type[target_uid]
                if actual_type != expected_type:
                    violations.append(
                        Violation(
                            template_uid=template.uid,
                            template_title=template.title,
                            template_type=uid_to_type[template.uid],
                            field=field_name,
                            violation="wrong_type",
                            referenced_uid=target_uid,
                            hint=f"expected {expected_type}, got {actual_type}",
                        )
                    )

        # 5. cycle — only meaningful for parent_template_uid (Tasks).
        violations.extend(self._detect_task_parent_cycles(bundle))

        return violations

    @staticmethod
    def _check_template_statuses(bundle: TemplateBundle) -> list[Violation]:
        """Flag every template whose status is not ACTIVE."""
        from core.ports.query_types import Violation

        uid_to_type = bundle.type_by_uid()
        all_templates: list[Any] = [
            *bundle.tasks,
            *bundle.goals,
            *bundle.habits,
            *bundle.events,
            *bundle.choices,
            *bundle.principles,
        ]
        return [
            Violation(
                template_uid=str(tmpl.uid),
                template_title=tmpl.title,
                template_type=uid_to_type[str(tmpl.uid)],
                field="status",
                violation="not_active",
                referenced_uid=None,
                hint=(
                    f"template status is {tmpl.status!r}; "
                    "must be ACTIVE before the PathStep can be published or engaged"
                ),
            )
            for tmpl in all_templates
            if tmpl.status != EntityStatus.ACTIVE
        ]

    @staticmethod
    def _iter_refs(
        bundle: TemplateBundle,
    ) -> list[tuple[Any, list[tuple[str, TemplateTypeName]]]]:
        """Yield (template, ref_field_table) pairs for every template with refs."""
        out: list[tuple[Any, list[tuple[str, TemplateTypeName]]]] = []
        out.extend((tt, TASK_REFS) for tt in bundle.tasks)
        out.extend((gt, GOAL_REFS) for gt in bundle.goals)
        out.extend((et, EVENT_REFS) for et in bundle.events)
        # Habit, Choice, Principle have no refs to walk.
        return out

    @staticmethod
    def _detect_task_parent_cycles(bundle: TemplateBundle) -> list[Violation]:
        """Find cycles in the TaskTemplate.parent_template_uid graph."""
        from core.ports.query_types import Violation

        parent_of: dict[str, str | None] = {
            str(tt.uid): tt.parent_template_uid for tt in bundle.tasks
        }
        cycle_members: set[str] = set()
        for start_uid in parent_of:
            if start_uid in cycle_members:
                continue
            seen: list[str] = []
            cur: str | None = start_uid
            while cur is not None and cur not in seen:
                seen.append(cur)
                cur = parent_of.get(cur)
            if cur is not None and cur in seen:
                # Cycle detected — flag every member reached after re-entering.
                cycle_start = seen.index(cur)
                cycle_members.update(seen[cycle_start:])

        if not cycle_members:
            return []

        title_by_uid: dict[str, str] = {str(tt.uid): tt.title for tt in bundle.tasks}
        return [
            Violation(
                template_uid=uid,
                template_title=title_by_uid[uid],
                template_type="TaskTemplate",
                field="parent_template_uid",
                violation="cycle",
                referenced_uid=parent_of[uid],
                hint="parent_template_uid chain forms a cycle",
            )
            for uid in sorted(cycle_members)
        ]

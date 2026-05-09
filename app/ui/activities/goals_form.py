"""
Goal create / edit form
=======================

Wires the searchable cross-domain :class:`~ui.patterns.entity_picker.EntityPicker`
into FormGenerator-rendered Goal forms so users pick a parent goal instead of
typing a UID by hand.

Used by ``adapters/inbound/goals_ui.py`` (``GET /goals/create`` and
``GET /goals/edit``).
"""

from __future__ import annotations

from typing import Any

from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest, GoalUpdateRequest
from ui.patterns.entity_picker import EntityPicker
from ui.patterns.form_generator import FormGenerator

_CREATE_SECTIONS: dict[str, list[str]] = {
    "Basics": ["title", "description", "vision_statement"],
    "Classification": ["goal_type", "domain", "timeframe", "priority"],
    "Measurement": ["measurement_type", "target_value", "unit_of_measurement"],
    "Timeline": ["start_date", "target_date"],
    "Motivation": ["why_important", "success_criteria"],
    "Hierarchy": ["parent_goal_uid", "progress_weight"],
}

_EDIT_SECTIONS: dict[str, list[str]] = {
    "Basics": ["title", "description", "vision_statement"],
    "Classification": ["goal_type", "domain", "timeframe", "priority", "status"],
    "Measurement": ["measurement_type", "target_value", "unit_of_measurement"],
    # parent_goal_uid intentionally absent: GoalUpdateRequest doesn't accept it.
    "Timeline": ["target_date"],
    "Motivation": ["why_important", "success_criteria"],
}


def GoalCreateForm() -> Any:
    """Render the Goal create form with EntityPicker for the parent-goal UID.

    POSTs ``application/x-www-form-urlencoded`` to ``/goals/create``. The picker
    emits a hidden input named ``parent_goal_uid`` so the form body validates
    directly against :class:`GoalCreateRequest`.

    List-typed fields (``required_knowledge_uids``, ``supporting_habit_uids``,
    ``guiding_principle_uids``, ``potential_obstacles``, ``strategies``, ``tags``)
    are intentionally omitted — UID-list relationships belong on the detail-page
    relationship picker, and free-text list fields hit the FormGenerator list
    bug. See: project_form_generator_list_bug.md.
    """
    return FormGenerator.from_model(
        GoalCreateRequest,
        action="/goals/create",
        method="POST",
        sections=_CREATE_SECTIONS,
        custom_widgets={
            "parent_goal_uid": EntityPicker("parent_goal_uid", target_type="goal"),
        },
        submit_label="Create Goal",
        form_attrs={"id": "goal-create-form"},
    )


def GoalEditForm(goal: Goal) -> Any:
    """Render the Goal edit form prefilled from an existing goal.

    Args:
        goal: The Goal being edited. Field values prefill via
            :meth:`FormGenerator.from_instance`.

    GoalUpdateRequest exposes no cross-domain single-UID fields, so no
    EntityPicker widgets are wired here.
    """
    return FormGenerator.from_instance(
        GoalUpdateRequest,
        goal,
        action=f"/goals/edit?uid={goal.uid}",
        method="POST",
        sections=_EDIT_SECTIONS,
        submit_label="Save Changes",
        form_attrs={"id": "goal-edit-form"},
    )


__all__ = ["GoalCreateForm", "GoalEditForm"]

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

_CREATE_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "vision_statement"],
    },
    "Classification": {
        "icon": "tag",
        "accent": "violet",
        "fields": ["goal_type", "domain", "timeframe", "priority"],
    },
    "Measurement": {
        "icon": "ruler",
        "accent": "cyan",
        "fields": ["measurement_type", "target_value", "unit_of_measurement"],
    },
    "Timeline": {
        "icon": "calendar",
        "accent": "amber",
        "fields": ["start_date", "target_date"],
    },
    "Motivation": {
        "icon": "flame",
        "accent": "rose",
        "fields": ["why_important", "success_criteria"],
    },
    "Hierarchy": {
        "icon": "git-branch",
        "accent": "emerald",
        "fields": ["parent_goal_uid", "progress_weight"],
    },
}

# parent_goal_uid intentionally absent: GoalUpdateRequest doesn't accept it.
_EDIT_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "vision_statement"],
    },
    "Classification": {
        "icon": "tag",
        "accent": "violet",
        "fields": ["goal_type", "domain", "timeframe", "priority", "status"],
    },
    "Measurement": {
        "icon": "ruler",
        "accent": "cyan",
        "fields": ["measurement_type", "target_value", "unit_of_measurement"],
    },
    "Timeline": {"icon": "calendar", "accent": "amber", "fields": ["target_date"]},
    "Motivation": {
        "icon": "flame",
        "accent": "rose",
        "fields": ["why_important", "success_criteria"],
    },
}

_FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "description": "Description",
    "vision_statement": "Long-term vision",
    "goal_type": "Type",
    "domain": "Knowledge domain",
    "timeframe": "Timeframe",
    "priority": "Priority",
    "status": "Status",
    "measurement_type": "Measurement type",
    "target_value": "Target value",
    "unit_of_measurement": "Unit",
    "start_date": "Start date",
    "target_date": "Target date",
    "why_important": "Why this matters",
    "success_criteria": "Success criteria",
    "parent_goal_uid": "Parent goal",
    "progress_weight": "Progress weight",
}

_FIELD_HELP: dict[str, str] = {
    "vision_statement": "What does success look like long-term?",
    "parent_goal_uid": "Make this a subgoal of a larger goal.",
    "progress_weight": "How much this subgoal contributes to its parent (1.0 = equal weight).",
    "why_important": "Why is achieving this goal meaningful to you?",
    "success_criteria": "How will you know you've succeeded?",
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
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
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
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        submit_label="Save Changes",
        form_attrs={"id": "goal-edit-form"},
    )


__all__ = ["GoalCreateForm", "GoalEditForm"]

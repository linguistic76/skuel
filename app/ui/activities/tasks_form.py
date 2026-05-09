"""
Task create / edit form
=======================

Wires the searchable cross-domain :class:`~ui.patterns.entity_picker.EntityPicker`
into FormGenerator-rendered Task forms so users pick a parent task, fulfilled
goal, or reinforced habit instead of typing UIDs by hand.

Used by ``adapters/inbound/tasks_ui.py`` (``GET /tasks/create`` and
``GET /tasks/edit``).
"""

from __future__ import annotations

from typing import Any

from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from ui.patterns.entity_picker import EntityPicker
from ui.patterns.form_generator import FormGenerator

_CREATE_SECTIONS: dict[str, list[str]] = {
    "Basics": ["title", "description"],
    "Scheduling": ["due_date", "scheduled_date", "duration_minutes", "priority"],
    "Organization": ["project", "assignee"],
    "Connections": ["parent_uid", "fulfills_goal_uid", "reinforces_habit_uid"],
}

_EDIT_SECTIONS: dict[str, list[str]] = {
    "Basics": ["title", "description"],
    "Scheduling": [
        "due_date",
        "scheduled_date",
        "duration_minutes",
        "priority",
        "status",
        "completion_date",
    ],
    "Organization": ["project", "assignee"],
    # parent_uid is intentionally absent: TaskUpdateRequest does not accept it.
    "Connections": ["fulfills_goal_uid", "reinforces_habit_uid"],
}


def TaskCreateForm() -> Any:
    """Render the Task create form with EntityPicker for cross-domain UIDs.

    POSTs ``application/x-www-form-urlencoded`` to ``/tasks/create``. Each
    picker emits a hidden input named ``{parent,fulfills_goal,reinforces_habit}_uid``
    so the form body validates directly against :class:`TaskCreateRequest`.
    """
    return FormGenerator.from_model(
        TaskCreateRequest,
        action="/tasks/create",
        method="POST",
        sections=_CREATE_SECTIONS,
        custom_widgets={
            "parent_uid": EntityPicker("parent_uid", target_type="task"),
            "fulfills_goal_uid": EntityPicker("fulfills_goal_uid", target_type="goal"),
            "reinforces_habit_uid": EntityPicker("reinforces_habit_uid", target_type="habit"),
        },
        submit_label="Create Task",
        form_attrs={"id": "task-create-form"},
    )


def TaskEditForm(
    task: Task,
    *,
    goal_display: str | None = None,
    habit_display: str | None = None,
) -> Any:
    """Render the Task edit form prefilled from an existing task.

    Args:
        task: The Task being edited. Provides UID context (so the parent picker
            could later exclude self+descendants), and field values to prefill.
        goal_display: Human-readable title for ``task.fulfills_goal_uid``,
            resolved by the route layer. ``None`` leaves the picker's visible
            input empty even when the hidden UID is set.
        habit_display: Same as ``goal_display`` but for
            ``task.reinforces_habit_uid``.
    """
    return FormGenerator.from_instance(
        TaskUpdateRequest,
        task,
        action=f"/tasks/edit?uid={task.uid}",
        method="POST",
        sections=_EDIT_SECTIONS,
        custom_widgets={
            "fulfills_goal_uid": EntityPicker(
                "fulfills_goal_uid",
                target_type="goal",
                value=task.fulfills_goal_uid,
                display=goal_display,
            ),
            "reinforces_habit_uid": EntityPicker(
                "reinforces_habit_uid",
                target_type="habit",
                value=task.reinforces_habit_uid,
                display=habit_display,
            ),
        },
        submit_label="Save Changes",
        form_attrs={"id": "task-edit-form"},
    )


__all__ = ["TaskCreateForm", "TaskEditForm"]

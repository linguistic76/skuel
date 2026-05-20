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
from ui.patterns.activity_form_helper import render_activity_form
from ui.patterns.entity_picker import EntityPicker

_CREATE_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description"]},
    "Scheduling": {
        "icon": "calendar",
        "accent": "amber",
        "fields": ["due_date", "scheduled_date", "duration_minutes", "priority"],
    },
    "Organization": {
        "icon": "folder",
        "accent": "emerald",
        "fields": ["project", "assignee"],
    },
    "Connections": {
        "icon": "link-2",
        "accent": "violet",
        "fields": ["parent_uid", "fulfills_goal_uid", "reinforces_habit_uid"],
    },
}

# parent_uid is intentionally absent from edit: TaskUpdateRequest does not accept it.
_EDIT_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description"]},
    "Scheduling": {
        "icon": "calendar",
        "accent": "amber",
        "fields": [
            "due_date",
            "scheduled_date",
            "duration_minutes",
            "priority",
            "status",
            "completion_date",
        ],
    },
    "Organization": {
        "icon": "folder",
        "accent": "emerald",
        "fields": ["project", "assignee"],
    },
    "Connections": {
        "icon": "link-2",
        "accent": "violet",
        "fields": ["fulfills_goal_uid", "reinforces_habit_uid"],
    },
}

# Friendlier labels override the Pydantic descriptions, which are written for
# API docs, not UI. Section titles already supply the domain context.
_FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "description": "Description",
    "due_date": "Due date",
    "scheduled_date": "Work date",
    "duration_minutes": "Duration (minutes)",
    "priority": "Priority",
    "status": "Status",
    "completion_date": "Completed on",
    "project": "Project",
    "assignee": "Assignee",
    "parent_uid": "Parent task",
    "fulfills_goal_uid": "Goal",
    "reinforces_habit_uid": "Habit",
}

_FIELD_HELP: dict[str, str] = {
    "parent_uid": "Make this a subtask of another task.",
    "fulfills_goal_uid": "Link this task to a goal it contributes to.",
    "reinforces_habit_uid": "Link this task to a habit it reinforces.",
    "duration_minutes": "How long you expect this to take, in minutes.",
}


def TaskCreateForm() -> Any:
    """Render the Task create form with EntityPicker for cross-domain UIDs.

    Each picker emits a hidden input named ``{parent,fulfills_goal,reinforces_habit}_uid``
    so the form body validates directly against :class:`TaskCreateRequest`.
    """
    return render_activity_form(
        domain_slug="tasks",
        entity_name="Task",
        request_model=TaskCreateRequest,
        operation="create",
        sections=_CREATE_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        custom_widgets={
            "parent_uid": EntityPicker("parent_uid", target_type="task"),
            "fulfills_goal_uid": EntityPicker("fulfills_goal_uid", target_type="goal"),
            "reinforces_habit_uid": EntityPicker("reinforces_habit_uid", target_type="habit"),
        },
    )


def TaskEditForm(
    task: Task,
    *,
    goal_display: str | None = None,
    habit_display: str | None = None,
    habit_uid: str | None = None,
) -> Any:
    """Render the Task edit form prefilled from an existing task.

    Args:
        task: The Task being edited. Provides UID context and field values to prefill.
        goal_display: Human-readable title for ``task.fulfills_goal_uid``, resolved by
            the route layer. ``None`` leaves the picker's visible input empty even
            when the hidden UID is set.
        habit_display: Human-readable title for the reinforced habit, resolved by
            the route layer.
        habit_uid: UID of the habit this task reinforces, resolved by the route layer
            from the (Task)-[:REINFORCES_HABIT]->(Habit) edge (graph-native; no longer
            a property on the task).
    """
    return render_activity_form(
        domain_slug="tasks",
        entity_name="Task",
        request_model=TaskUpdateRequest,
        operation="edit",
        sections=_EDIT_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        entity=task,
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
                value=habit_uid,
                display=habit_display,
            ),
        },
    )


__all__ = ["TaskCreateForm", "TaskEditForm"]

"""
Task create / edit form
=======================

Wires the searchable cross-domain :class:`~ui.patterns.entity_picker.EntityPicker`
into FormGenerator-rendered Task forms so users pick a parent task, a goal the
task contributes to, or a reinforced habit instead of typing UIDs by hand.

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
        "fields": ["parent_uid", "contributes_to_goal_uids", "reinforces_habit_uid"],
    },
}

# parent_uid is intentionally absent from edit: TaskUpdateRequest does not accept it.
# The goal picker is absent too: a task contributes to any number of goals, and a
# single picker posting one would replace the whole set (TaskUpdateRequest's
# ``contributes_to_goal_uids`` is a full replace). The task's goals show in its
# Connections section.
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
        "fields": ["reinforces_habit_uid"],
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
    "contributes_to_goal_uids": "Goal",
    "reinforces_habit_uid": "Habit",
}

_FIELD_HELP: dict[str, str] = {
    "parent_uid": "Make this a subtask of another task.",
    "contributes_to_goal_uids": "A goal this task contributes to.",
    "reinforces_habit_uid": "Link this task to a habit it reinforces.",
    "duration_minutes": "How long you expect this to take, in minutes.",
}


def TaskCreateForm() -> Any:
    """Render the Task create form with EntityPicker for cross-domain UIDs.

    Each picker emits a hidden input named for its request field (``parent_uid``,
    ``contributes_to_goal_uids``, ``reinforces_habit_uid``) so the form body validates
    directly against :class:`TaskCreateRequest`; the goal picker's one uid becomes a
    one-goal list.
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
            "contributes_to_goal_uids": EntityPicker(
                "contributes_to_goal_uids", target_type="goal"
            ),
            "reinforces_habit_uid": EntityPicker("reinforces_habit_uid", target_type="habit"),
        },
    )


def TaskEditForm(
    task: Task,
    *,
    habit_display: str | None = None,
    habit_uid: str | None = None,
) -> Any:
    """Render the Task edit form prefilled from an existing task.

    Args:
        task: The Task being edited. Provides UID context and field values to prefill.
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
            "reinforces_habit_uid": EntityPicker(
                "reinforces_habit_uid",
                target_type="habit",
                value=habit_uid,
                display=habit_display,
            ),
        },
    )


__all__ = ["TaskCreateForm", "TaskEditForm"]

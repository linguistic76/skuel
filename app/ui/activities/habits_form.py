"""
Habit create / edit form
========================

FormGenerator-rendered Habit forms used by ``adapters/inbound/habits_ui.py``
(``GET /habits/create`` and ``GET /habits/edit``).

Habit's cross-domain links (``linked_goal_uids``, ``linked_principle_uids``,
``linked_knowledge_uids``, ``prerequisite_habit_uids``) are all list-typed,
so they are intentionally omitted from the form — UID-list relationships
belong on the detail-page relationship picker.

Request-model field names match the Habit domain model 1:1, so the edit form
auto-prefills via ``entity=habit`` (no hand-maintained ``values`` dict).
"""

from __future__ import annotations

from typing import Any

from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitCreateRequest, HabitUpdateRequest
from ui.patterns.activity_form_helper import render_activity_form

_CREATE_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "polarity", "habit_category", "habit_difficulty"],
    },
    "Schedule": {
        "icon": "calendar",
        "accent": "amber",
        "fields": [
            "recurrence_pattern",
            "target_days_per_week",
            "preferred_time",
            "duration_minutes",
        ],
    },
    "Behavioral Science": {
        "icon": "lightbulb",
        "accent": "violet",
        "fields": ["cue", "routine", "reward"],
    },
    "Identity": {
        "icon": "user-check",
        "accent": "emerald",
        "fields": ["reinforces_identity", "is_identity_habit"],
    },
    "Organization": {"icon": "flag", "accent": "rose", "fields": ["priority"]},
}

_EDIT_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "polarity", "habit_category", "habit_difficulty"],
    },
    "Schedule": {
        "icon": "calendar",
        "accent": "amber",
        "fields": [
            "recurrence_pattern",
            "target_days_per_week",
            "preferred_time",
            "duration_minutes",
        ],
    },
    "Behavioral Science": {
        "icon": "lightbulb",
        "accent": "violet",
        "fields": ["cue", "routine", "reward"],
    },
    "Status & Priority": {
        "icon": "flag",
        "accent": "rose",
        "fields": ["status", "priority"],
    },
}

_FIELD_LABELS: dict[str, str] = {
    "title": "Name",
    "description": "Description",
    "polarity": "Polarity",
    "habit_category": "Category",
    "habit_difficulty": "Difficulty",
    "recurrence_pattern": "Recurrence",
    "target_days_per_week": "Target days per week",
    "preferred_time": "Preferred time of day",
    "duration_minutes": "Duration (minutes)",
    "cue": "Cue / trigger",
    "routine": "Routine",
    "reward": "Reward",
    "reinforces_identity": "Identity it reinforces",
    "is_identity_habit": "Identity habit",
    "status": "Status",
    "priority": "Priority",
}

_FIELD_HELP: dict[str, str] = {
    "polarity": "'Build' to establish a habit; 'Break' to eliminate one.",
    "preferred_time": "Which block of the day this habit belongs in — not a clock time.",
    "duration_minutes": "How long one occurrence takes.",
    "cue": "What triggers this habit? (e.g. 'After morning coffee')",
    "routine": "The specific behavior you carry out.",
    "reward": "What immediate benefit do you get from completing it?",
    "reinforces_identity": "An identity statement this habit supports (e.g. 'I am a writer').",
    "is_identity_habit": "Mark this as primarily about identity rather than outcomes.",
}


def HabitCreateForm() -> Any:
    """Render the Habit create form."""
    return render_activity_form(
        domain_slug="habits",
        entity_name="Habit",
        request_model=HabitCreateRequest,
        operation="create",
        sections=_CREATE_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
    )


def HabitEditForm(habit: Habit) -> Any:
    """Render the Habit edit form prefilled from an existing habit."""
    return render_activity_form(
        domain_slug="habits",
        entity_name="Habit",
        request_model=HabitUpdateRequest,
        operation="edit",
        sections=_EDIT_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        entity=habit,
    )


__all__ = ["HabitCreateForm", "HabitEditForm"]

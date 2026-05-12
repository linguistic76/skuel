"""
Activity Template create/edit forms.

One ``DomainSpec`` per Activity Domain bundles the four bits the route layer
needs to render or submit a template form:

- ``create_schema`` / ``update_schema`` — the Pydantic request models.
- ``offset_fields`` — schema fields typed ``RelativeOffsetDTO | None``; rendered
  with :func:`RelativeOffsetWidget` instead of the default datetime input.
- ``ref_fields`` — ``{field_name: target_domain}`` mapping for the cross-
  template UID fields, rendered with :func:`PsTemplatePicker`.
- ``sections`` / ``edit_sections`` — section layout passed to FormGenerator.
- ``excluded_create`` / ``excluded_edit`` — nested-authoring fields explicitly
  deferred from V1 (Goal milestones, Choice options, Principle expressions).

V1 nested-field policy: the ``milestones`` / ``options`` / ``expressions``
fields are excluded from both create and edit forms. The schemas accept
``list[dict]``; templates created/edited via this UI will get the empty-tuple
default. Authoring those nested shapes requires repeatable subforms — deferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from core.models.templates.choice_template_request import (
    ChoiceTemplateCreateRequest,
    ChoiceTemplateUpdateRequest,
)
from core.models.templates.event_template_request import (
    EventTemplateCreateRequest,
    EventTemplateUpdateRequest,
)
from core.models.templates.goal_template_request import (
    GoalTemplateCreateRequest,
    GoalTemplateUpdateRequest,
)
from core.models.templates.habit_template_request import (
    HabitTemplateCreateRequest,
    HabitTemplateUpdateRequest,
)
from core.models.templates.principle_template_request import (
    PrincipleTemplateCreateRequest,
    PrincipleTemplateUpdateRequest,
)
from core.models.templates.task_template_request import (
    TaskTemplateCreateRequest,
    TaskTemplateUpdateRequest,
)
from ui.patterns.form_generator import FormGenerator
from ui.teaching._template_widgets import PsTemplatePicker, RelativeOffsetWidget


@dataclass(frozen=True)
class DomainSpec:
    """Per-domain config bundling everything the form layer needs."""

    domain: str
    create_schema: type[BaseModel]
    update_schema: type[BaseModel]
    offset_fields: tuple[str, ...]
    ref_fields: dict[str, str]  # field_name -> target domain (e.g. "goal")
    sections: dict[str, dict[str, Any]]
    edit_sections: dict[str, dict[str, Any]]
    excluded_create: tuple[str, ...] = ()
    excluded_edit: tuple[str, ...] = ()


# ============================================================================
# Per-domain specs
# ============================================================================

_TASK_SECTIONS = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description", "tags"]},
    "Scheduling": {
        "icon": "calendar",
        "accent": "amber",
        "fields": [
            "due_offset",
            "scheduled_offset",
            "duration_minutes",
            "recurrence_pattern",
            "recurrence_end_offset",
        ],
    },
    "Organization": {
        "icon": "folder",
        "accent": "emerald",
        "fields": ["project", "parent_template_uid"],
    },
    "Cross-template links": {
        "icon": "link-2",
        "accent": "violet",
        "fields": [
            "fulfills_goal_template_uid",
            "reinforces_habit_template_uid",
            "scheduled_event_template_uid",
        ],
    },
    "Progress impact": {
        "icon": "trending-up",
        "accent": "rose",
        "fields": [
            "goal_progress_contribution",
            "knowledge_mastery_check",
            "habit_streak_maintainer",
            "completion_updates_goal",
        ],
    },
}
_TASK_EDIT_SECTIONS = {
    **_TASK_SECTIONS,
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "status", "tags"],
    },
}

TASK_SPEC = DomainSpec(
    domain="task",
    create_schema=TaskTemplateCreateRequest,
    update_schema=TaskTemplateUpdateRequest,
    offset_fields=("due_offset", "scheduled_offset", "recurrence_end_offset"),
    ref_fields={
        "parent_template_uid": "task",
        "fulfills_goal_template_uid": "goal",
        "reinforces_habit_template_uid": "habit",
        "scheduled_event_template_uid": "event",
    },
    sections=_TASK_SECTIONS,
    edit_sections=_TASK_EDIT_SECTIONS,
)

_GOAL_SECTIONS = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description", "tags"]},
    "Targeting": {
        "icon": "target",
        "accent": "amber",
        "fields": [
            "goal_type",
            "timeframe",
            "measurement_type",
            "target_value",
            "unit_of_measurement",
            "start_offset",
            "target_offset",
        ],
    },
    "Vision": {
        "icon": "eye",
        "accent": "emerald",
        "fields": [
            "vision_statement",
            "why_important",
            "success_criteria",
            "potential_obstacles",
            "strategies",
        ],
    },
    "Identity": {
        "icon": "user",
        "accent": "cyan",
        "fields": ["target_identity", "identity_evidence_required"],
    },
    "Cross-template links": {
        "icon": "link-2",
        "accent": "violet",
        "fields": [
            "fulfills_goal_template_uid",
            "inspired_by_choice_template_uid",
            "selected_choice_option_template_uid",
        ],
    },
}
_GOAL_EDIT_SECTIONS = {
    **_GOAL_SECTIONS,
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "status", "tags"],
    },
}

GOAL_SPEC = DomainSpec(
    domain="goal",
    create_schema=GoalTemplateCreateRequest,
    update_schema=GoalTemplateUpdateRequest,
    offset_fields=("start_offset", "target_offset"),
    ref_fields={
        "fulfills_goal_template_uid": "goal",
        "inspired_by_choice_template_uid": "choice",
        "selected_choice_option_template_uid": "choice",
    },
    sections=_GOAL_SECTIONS,
    edit_sections=_GOAL_EDIT_SECTIONS,
    excluded_create=("milestones",),
    excluded_edit=("milestones",),
)

_HABIT_SECTIONS = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description", "tags"]},
    "Shape": {
        "icon": "repeat",
        "accent": "amber",
        "fields": [
            "polarity",
            "habit_category",
            "habit_difficulty",
            "cue",
            "routine",
            "reward",
        ],
    },
    "Identity": {
        "icon": "user",
        "accent": "emerald",
        "fields": [
            "is_identity_habit",
            "target_identity",
            "reinforces_identity",
            "identity_evidence_required",
        ],
    },
    "Cadence": {
        "icon": "calendar",
        "accent": "violet",
        "fields": [
            "duration_minutes",
            "recurrence_pattern",
            "recurrence_end_offset",
            "target_days_per_week",
            "preferred_time",
        ],
    },
    "Reminders": {
        "icon": "bell",
        "accent": "rose",
        "fields": ["reminder_enabled", "reminder_time", "reminder_days"],
    },
}
_HABIT_EDIT_SECTIONS = {
    **_HABIT_SECTIONS,
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "status", "tags"],
    },
}

HABIT_SPEC = DomainSpec(
    domain="habit",
    create_schema=HabitTemplateCreateRequest,
    update_schema=HabitTemplateUpdateRequest,
    offset_fields=("recurrence_end_offset",),
    ref_fields={},
    sections=_HABIT_SECTIONS,
    edit_sections=_HABIT_EDIT_SECTIONS,
)

_EVENT_SECTIONS = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description", "tags"]},
    "When": {
        "icon": "calendar",
        "accent": "amber",
        "fields": [
            "event_offset",
            "start_time",
            "end_time",
            "duration_minutes",
            "recurrence_pattern",
            "recurrence_end_offset",
            "reminder_minutes",
        ],
    },
    "Where": {
        "icon": "map-pin",
        "accent": "emerald",
        "fields": ["event_type", "location", "is_online", "meeting_url", "max_attendees"],
    },
    "Cross-template links": {
        "icon": "link-2",
        "accent": "violet",
        "fields": [
            "reinforces_habit_template_uid",
            "milestone_celebration_for_goal_template_uid",
        ],
    },
    "Milestone signals": {
        "icon": "flag",
        "accent": "rose",
        "fields": [
            "is_milestone_event",
            "milestone_type",
            "curriculum_week",
            "knowledge_retention_check",
            "recurrence_maintains_habit",
            "skip_breaks_habit_streak",
        ],
    },
}
_EVENT_EDIT_SECTIONS = {
    **_EVENT_SECTIONS,
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "status", "tags"],
    },
}

EVENT_SPEC = DomainSpec(
    domain="event",
    create_schema=EventTemplateCreateRequest,
    update_schema=EventTemplateUpdateRequest,
    offset_fields=("event_offset", "recurrence_end_offset"),
    ref_fields={
        "reinforces_habit_template_uid": "habit",
        "milestone_celebration_for_goal_template_uid": "goal",
    },
    sections=_EVENT_SECTIONS,
    edit_sections=_EVENT_EDIT_SECTIONS,
)

_CHOICE_SECTIONS = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description", "tags"]},
    "Decision": {
        "icon": "git-branch",
        "accent": "amber",
        "fields": [
            "choice_type",
            "decision_rationale",
            "decision_criteria",
            "constraints",
            "stakeholders",
            "decision_deadline_offset",
        ],
    },
    "Inspiration": {
        "icon": "sparkles",
        "accent": "violet",
        "fields": ["inspiration_type", "expands_possibilities"],
    },
}
_CHOICE_EDIT_SECTIONS = {
    **_CHOICE_SECTIONS,
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "status", "tags"],
    },
}

CHOICE_SPEC = DomainSpec(
    domain="choice",
    create_schema=ChoiceTemplateCreateRequest,
    update_schema=ChoiceTemplateUpdateRequest,
    offset_fields=("decision_deadline_offset",),
    ref_fields={},
    sections=_CHOICE_SECTIONS,
    edit_sections=_CHOICE_EDIT_SECTIONS,
    excluded_create=("options",),
    excluded_edit=("options",),
)

_PRINCIPLE_SECTIONS = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description", "tags"]},
    "Statement": {
        "icon": "quote",
        "accent": "amber",
        "fields": [
            "statement",
            "principle_category",
            "principle_source",
            "strength",
        ],
    },
    "Provenance": {
        "icon": "book",
        "accent": "emerald",
        "fields": ["tradition", "original_source", "personal_interpretation"],
    },
    "Application": {
        "icon": "check",
        "accent": "violet",
        "fields": ["key_behaviors"],
    },
    "Conflicts": {
        "icon": "alert-triangle",
        "accent": "rose",
        "fields": ["potential_conflicts", "conflicting_principles", "resolution_strategies"],
    },
    "History": {
        "icon": "history",
        "accent": "cyan",
        "fields": ["origin_story", "evolution_notes"],
    },
}
_PRINCIPLE_EDIT_SECTIONS = {
    **_PRINCIPLE_SECTIONS,
    "Basics": {
        "icon": "info",
        "accent": "blue",
        "fields": ["title", "description", "status", "tags"],
    },
}

PRINCIPLE_SPEC = DomainSpec(
    domain="principle",
    create_schema=PrincipleTemplateCreateRequest,
    update_schema=PrincipleTemplateUpdateRequest,
    offset_fields=(),
    ref_fields={},
    sections=_PRINCIPLE_SECTIONS,
    edit_sections=_PRINCIPLE_EDIT_SECTIONS,
    excluded_create=("expressions",),
    excluded_edit=("expressions",),
)


DOMAIN_SPECS: dict[str, DomainSpec] = {
    "task": TASK_SPEC,
    "goal": GOAL_SPEC,
    "habit": HABIT_SPEC,
    "event": EVENT_SPEC,
    "choice": CHOICE_SPEC,
    "principle": PRINCIPLE_SPEC,
}


# ============================================================================
# Shared field labels / help
# ============================================================================

_FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "description": "Description",
    "tags": "Tags",
    "status": "Status",
    "due_offset": "Due offset",
    "scheduled_offset": "Scheduled offset",
    "recurrence_end_offset": "Recurrence ends after",
    "start_offset": "Start offset",
    "target_offset": "Target offset",
    "event_offset": "Event offset",
    "decision_deadline_offset": "Decision deadline offset",
    "parent_template_uid": "Parent task template",
    "fulfills_goal_template_uid": "Fulfills goal template",
    "reinforces_habit_template_uid": "Reinforces habit template",
    "scheduled_event_template_uid": "Scheduled within event template",
    "inspired_by_choice_template_uid": "Inspired by choice template",
    "selected_choice_option_template_uid": "Selected choice option template",
    "milestone_celebration_for_goal_template_uid": "Celebrates goal template",
}

_FIELD_HELP: dict[str, str] = {
    "due_offset": "Time from engagement until due (days / hours / minutes).",
    "scheduled_offset": "When the student should work on this, relative to engagement.",
    "recurrence_end_offset": "When the recurrence series ends, relative to engagement.",
    "start_offset": "When the goal becomes active, relative to engagement.",
    "target_offset": "When the goal should be achieved, relative to engagement.",
    "event_offset": "When the event happens, relative to engagement.",
    "decision_deadline_offset": "When the decision must be made, relative to engagement.",
    "tags": "One tag per line, or comma-separated.",
    "parent_template_uid": "Make this a subtask of another task template on this PathStep.",
    "fulfills_goal_template_uid": "Link this template to a goal template on the same PathStep.",
    "reinforces_habit_template_uid": "Link this template to a habit template on the same PathStep.",
    "scheduled_event_template_uid": "Pin this task to an event template on the same PathStep.",
    "inspired_by_choice_template_uid": "Goal that emerges from a choice template.",
    "selected_choice_option_template_uid": "Specific option this goal commits to.",
    "milestone_celebration_for_goal_template_uid": "Event template celebrating a goal milestone.",
}


# ============================================================================
# Form builders
# ============================================================================


def _build_custom_widgets(
    spec: DomainSpec,
    *,
    picker_options: dict[str, list[tuple[str, str]]],
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose RelativeOffset widgets and PS template pickers for one spec.

    Args:
        spec: The domain spec.
        picker_options: ``{target_domain: [(uid, title), ...]}`` — populated by
            the route layer from ``service.list_for_pathstep`` for every target
            type referenced in ``spec.ref_fields``.
        values: Per-field prefill values, used to mark the picker's selected
            option and prefill offset components.
    """
    widgets: dict[str, Any] = {}
    values = values or {}

    for field in spec.offset_fields:
        widgets[field] = RelativeOffsetWidget(field, values.get(field))

    for field, target_domain in spec.ref_fields.items():
        widgets[field] = PsTemplatePicker(
            field,
            picker_options.get(target_domain, []),
            value=values.get(field),
        )

    return widgets


def build_create_form(
    spec: DomainSpec,
    *,
    ps_uid: str,
    picker_options: dict[str, list[tuple[str, str]]],
) -> Any:
    """Build the create form for a given domain spec."""
    custom_widgets = _build_custom_widgets(spec, picker_options=picker_options)
    exclude = list(spec.excluded_create)
    return FormGenerator.from_model(
        spec.create_schema,
        action=f"/teaching/ps/{ps_uid}/templates/{spec.domain}/new",
        method="POST",
        sections=spec.sections,
        exclude_fields=exclude,
        custom_widgets=custom_widgets,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        submit_label=f"Create {spec.domain.title()} Template",
        form_attrs={"id": f"{spec.domain}-template-create-form"},
    )


def build_edit_form(
    spec: DomainSpec,
    *,
    ps_uid: str,
    template: Any,
    picker_options: dict[str, list[tuple[str, str]]],
) -> Any:
    """Build the edit form prefilled from a persisted template."""
    values = _instance_values(template, spec)
    custom_widgets = _build_custom_widgets(
        spec, picker_options=picker_options, values=values
    )
    exclude = list(spec.excluded_edit)
    return FormGenerator.from_instance(
        spec.update_schema,
        template,
        action=f"/teaching/ps/{ps_uid}/templates/{spec.domain}/edit?uid={template.uid}",
        method="POST",
        sections=spec.edit_sections,
        exclude_fields=exclude,
        custom_widgets=custom_widgets,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        submit_label="Save Changes",
        form_attrs={"id": f"{spec.domain}-template-edit-form"},
    )


def _instance_values(template: Any, spec: DomainSpec) -> dict[str, Any]:
    """Pull current values off a template for picker/offset widget prefill."""
    values: dict[str, Any] = {}
    for field in spec.offset_fields:
        values[field] = getattr(template, field, None)
    for field in spec.ref_fields:
        values[field] = getattr(template, field, None)
    return values


__all__ = [
    "CHOICE_SPEC",
    "DOMAIN_SPECS",
    "DomainSpec",
    "EVENT_SPEC",
    "GOAL_SPEC",
    "HABIT_SPEC",
    "PRINCIPLE_SPEC",
    "TASK_SPEC",
    "build_create_form",
    "build_edit_form",
]

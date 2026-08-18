"""
Activity Domain Forms Rendering Tests
=====================================

Smoke + convention tests for the 6 activity-domain forms (Tasks, Goals, Habits,
Events, Choices, Principles) plus the ``render_activity_form`` helper that
encodes their shared conventions.

What this pins:

- The three string conventions the helper encodes (form id, action URL, submit
  label) — these are untyped strings mypy can't protect.
- Each form's declared sections render in the output.
- EntityPicker custom widgets emit their hidden inputs where the create/edit
  forms wire them (Tasks: 3, Goals: 1 create, Events: 2).
- Edit forms prefill from the entity:
    - Habits: ``title`` / ``habit_category`` / ``habit_difficulty`` flow
      through auto-extraction (regression guard for the field-name rename
      that aligned HabitUpdateRequest with the Habit domain model).
    - Principles: ``why_important`` is split out of ``description`` via the
      marker, so both fields prefill independently.
- The helper's ``values=`` typo guard raises ``ValueError`` for unknown keys.
"""

from __future__ import annotations

import dataclasses
import html as html_lib
import re
from datetime import date, datetime

import pytest
from fasthtml.common import to_xml

from core.models.choice.choice import Choice
from core.models.enums import Priority, RecurrencePattern, TimeOfDay
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.principle_enums import (
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitUpdateRequest
from core.models.principle.principle import Principle
from core.models.task.task import Task
from ui.activities.choices_form import ChoiceCreateForm, ChoiceEditForm
from ui.activities.events_form import EventCreateForm, EventEditForm
from ui.activities.goals_form import GoalCreateForm, GoalEditForm
from ui.activities.habits_form import HabitCreateForm, HabitEditForm
from ui.activities.principles_form import PrincipleCreateForm, PrincipleEditForm
from ui.activities.tasks_form import TaskCreateForm, TaskEditForm
from ui.patterns.activity_form_helper import render_activity_form

# =============================================================================
# Entity fixtures — minimal valid instances for prefill assertions
# =============================================================================


def _now() -> datetime:
    return datetime(2026, 5, 14, 12, 0, 0)


@pytest.fixture
def task() -> Task:
    return Task(
        uid="task_x",
        user_uid="u",
        title="Write tests",
        description="Form rendering coverage",
        priority=Priority.HIGH,
        status=EntityStatus.ACTIVE,
        created_at=_now(),
        fulfills_goal_uid="goal_y",
        reinforces_habit_uid="habit_z",
    )


@pytest.fixture
def goal() -> Goal:
    return Goal(
        uid="goal_y",
        user_uid="u",
        title="Ship feature",
        description="By month end",
        goal_type=GoalType.OUTCOME,
        timeframe=GoalTimeframe.QUARTERLY,
        measurement_type=MeasurementType.BINARY,
        priority=Priority.HIGH,
        status=EntityStatus.ACTIVE,
        target_date=date(2026, 6, 1),
        created_at=_now(),
    )


@pytest.fixture
def habit() -> Habit:
    return Habit(
        uid="habit_z",
        user_uid="u",
        title="Read daily",
        description="Books, 30 min",
        polarity=HabitPolarity.BUILD,
        habit_category=HabitCategory.LEARNING,
        habit_difficulty=HabitDifficulty.EASY,
        recurrence_pattern=RecurrencePattern.DAILY,
        preferred_time=TimeOfDay.EVENING,
        duration_minutes=30,
        priority=Priority.HIGH,
        status=EntityStatus.ACTIVE,
        created_at=_now(),
    )


@pytest.fixture
def event() -> Event:
    return Event(
        uid="event_a",
        user_uid="u",
        title="Team standup",
        description="Daily sync",
        event_type="meeting",
        event_date=date(2026, 5, 15),
        priority=Priority.MEDIUM,
        status=EntityStatus.ACTIVE,
        created_at=_now(),
    )


@pytest.fixture
def choice() -> Choice:
    return Choice(
        uid="choice_b",
        user_uid="u",
        title="Frontend framework",
        description="React vs Solid",
        choice_type=ChoiceType.BINARY,
        decision_context="The current renderer can't do streaming.",
        priority=Priority.MEDIUM,
        status=EntityStatus.ACTIVE,
        created_at=_now(),
    )


@pytest.fixture
def principle() -> Principle:
    return Principle(
        uid="principle_c",
        user_uid="u",
        title="Be honest",
        statement="Always tell the truth",
        description="Foundational virtue.",
        why_important="Builds trust over time.",
        principle_category=PrincipleCategory.ETHICAL,
        principle_source=PrincipleSource.PERSONAL,
        strength=PrincipleStrength.CORE,
        priority=Priority.HIGH,
        status=EntityStatus.ACTIVE,
        created_at=_now(),
    )


# =============================================================================
# Helpers
# =============================================================================


def _form_tag(html: str) -> str:
    """Return the opening <form ...> tag from a rendered form."""
    match = re.search(r"<form[^>]*>", html)
    assert match, "No <form> tag in rendered output"
    return match.group()


def _submit_label(html: str) -> str:
    """Return the visible text of the submit button."""
    match = re.search(r'<button[^>]*type="submit"[^>]*>([^<]+)</button>', html)
    assert match, "No submit button in rendered output"
    return match.group(1)


def _hidden_input_names(html: str) -> set[str]:
    return set(re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"', html))


# =============================================================================
# Convention tests — parametrized over all 12 form/op combinations
# =============================================================================


def _build_form(form_callable, entity_obj):
    """Render a form, passing the entity for edit-form callables."""
    return form_callable(entity_obj) if entity_obj is not None else form_callable()


@pytest.fixture
def all_forms(task, goal, habit, event, choice, principle):
    """Yield (slug, entity_name, op, html) for every create+edit form."""
    return [
        ("tasks", "Task", "create", to_xml(TaskCreateForm())),
        ("tasks", "Task", "edit", to_xml(TaskEditForm(task))),
        ("goals", "Goal", "create", to_xml(GoalCreateForm())),
        ("goals", "Goal", "edit", to_xml(GoalEditForm(goal))),
        ("habits", "Habit", "create", to_xml(HabitCreateForm())),
        ("habits", "Habit", "edit", to_xml(HabitEditForm(habit))),
        ("events", "Event", "create", to_xml(EventCreateForm())),
        ("events", "Event", "edit", to_xml(EventEditForm(event))),
        ("choices", "Choice", "create", to_xml(ChoiceCreateForm())),
        ("choices", "Choice", "edit", to_xml(ChoiceEditForm(choice))),
        ("principles", "Principle", "create", to_xml(PrincipleCreateForm())),
        ("principles", "Principle", "edit", to_xml(PrincipleEditForm(principle))),
    ]


class TestFormConventions:
    """Pin the three untyped-string conventions render_activity_form encodes."""

    def test_form_id_matches_convention(self, all_forms) -> None:
        for slug, entity_name, op, html in all_forms:
            entity_slug = entity_name.lower()
            expected_id = f"{entity_slug}-{op}-form"
            assert f'id="{expected_id}"' in _form_tag(html), (
                f"{slug}/{op}: form id should be {expected_id!r}"
            )

    def test_form_action_matches_convention(self, all_forms) -> None:
        for slug, _entity_name, op, html in all_forms:
            tag = _form_tag(html)
            if op == "create":
                assert f'action="/{slug}/create"' in tag, f"{slug}/create action wrong"
            else:
                # edit forms include ?uid=<entity.uid>
                assert re.search(rf'action="/{slug}/edit\?uid=[^"]+"', tag), (
                    f"{slug}/edit action wrong: {tag}"
                )

    def test_submit_label_matches_convention(self, all_forms) -> None:
        for slug, entity_name, op, html in all_forms:
            expected = f"Create {entity_name}" if op == "create" else "Save Changes"
            assert _submit_label(html) == expected, f"{slug}/{op} submit label wrong"


# =============================================================================
# Section integrity — every declared section renders
# =============================================================================


_EXPECTED_SECTIONS: dict[tuple[str, str], list[str]] = {
    ("tasks", "create"): ["Basics", "Scheduling", "Organization", "Connections"],
    ("tasks", "edit"): ["Basics", "Scheduling", "Organization", "Connections"],
    ("goals", "create"): [
        "Basics",
        "Classification",
        "Measurement",
        "Timeline",
        "Motivation",
        "Hierarchy",
    ],
    ("goals", "edit"): ["Basics", "Classification", "Measurement", "Timeline", "Motivation"],
    ("habits", "create"): [
        "Basics",
        "Schedule",
        "Behavioral Science",
        "Identity",
        "Organization",
    ],
    ("habits", "edit"): ["Basics", "Schedule", "Behavioral Science", "Status & Priority"],
    ("events", "create"): [
        "Basics",
        "Scheduling",
        "Type & Visibility",
        "Location",
        "Attendees",
        "Reminder",
        "Connections",
        "Tracking",
    ],
    ("events", "edit"): [
        "Basics",
        "Scheduling",
        "Type & Visibility",
        "Location",
        "Reminder",
        "Connections",
        "Tracking",
    ],
    ("choices", "create"): ["Basics", "Classification", "Decision"],
    ("choices", "edit"): ["Basics", "Classification", "Decision"],
    ("principles", "create"): [
        "Basics",
        "Classification",
        "Context",
        "Reflection",
        "Organization",
    ],
    ("principles", "edit"): ["Basics", "Classification", "Context", "Reflection"],
}


class TestSectionRendering:
    def test_declared_sections_appear(self, all_forms) -> None:
        for slug, _entity_name, op, html in all_forms:
            # Section names like "Status & Priority" render as "Status &amp; Priority";
            # decode entities once so the assertion reads naturally.
            decoded = html_lib.unescape(html)
            for section_name in _EXPECTED_SECTIONS[(slug, op)]:
                assert section_name in decoded, f"{slug}/{op}: section {section_name!r} missing"


# =============================================================================
# EntityPicker widget wiring
# =============================================================================


class TestEntityPickerWiring:
    """The three domains with cross-domain single-UID fields use EntityPicker."""

    def test_tasks_create_picker_hidden_inputs(self) -> None:
        html = to_xml(TaskCreateForm())
        names = _hidden_input_names(html)
        assert {"parent_uid", "fulfills_goal_uid", "reinforces_habit_uid"} <= names

    def test_tasks_edit_picker_carries_entity_uid_values(self, task) -> None:
        # The habit picker value is resolved from the (Task)-[:REINFORCES_HABIT]->(Habit)
        # edge by the route layer and passed in via habit_uid (graph-native; no property).
        html = to_xml(TaskEditForm(task, habit_uid="habit_z"))
        # Pickers should be wired with the task's linked UIDs as hidden values
        assert re.search(
            r'<input[^>]*type="hidden"[^>]*name="fulfills_goal_uid"[^>]*value="goal_y"',
            html,
        ), "Goal-picker hidden value not set"
        assert re.search(
            r'<input[^>]*type="hidden"[^>]*name="reinforces_habit_uid"[^>]*value="habit_z"',
            html,
        ), "Habit-picker hidden value not set"

    def test_goals_create_has_parent_picker(self) -> None:
        names = _hidden_input_names(to_xml(GoalCreateForm()))
        assert "parent_goal_uid" in names

    def test_goals_edit_has_no_pickers(self, goal) -> None:
        """GoalUpdateRequest exposes no single-UID cross-domain fields."""
        html = to_xml(GoalEditForm(goal))
        # No EntityPicker hidden inputs — only the auto CSRF token may be hidden
        picker_names = _hidden_input_names(html) - {"_csrf_token", "csrf_token"}
        assert "parent_goal_uid" not in picker_names

    def test_events_create_pickers(self) -> None:
        names = _hidden_input_names(to_xml(EventCreateForm()))
        assert {"reinforces_habit_uid", "milestone_celebration_for_goal"} <= names

    def test_habits_create_has_no_pickers(self) -> None:
        """Habit's cross-domain fields are all list-typed — no EntityPicker widgets."""
        names = _hidden_input_names(to_xml(HabitCreateForm()))
        # CSRF or other framework-injected hidden fields may exist, but no domain pickers
        domain_pickers = {"parent_uid", "fulfills_goal_uid", "reinforces_habit_uid"}
        assert not (domain_pickers & names)


# =============================================================================
# Edit-form prefill — entity flows to inputs
# =============================================================================


class TestEditFormPrefill:
    """Auto-extraction (and split overrides) actually populate the inputs."""

    def test_habits_edit_prefills_renamed_fields(self, habit) -> None:
        """Regression guard: habit_category / habit_difficulty / title flow through.

        Before HabitUpdateRequest's fields were aligned with the Habit domain
        model, this required a hand-maintained ``values=`` dict that was
        easy to leave incomplete on field additions. Auto-extraction now
        handles it — verify nothing has regressed.
        """
        html = to_xml(HabitEditForm(habit))
        assert 'name="title"' in html
        assert 'value="Read daily"' in html
        assert "Books, 30 min" in html
        assert 'name="habit_category"' in html
        assert 'name="habit_difficulty"' in html

    def test_habits_form_offers_the_time_of_day_slots_not_a_free_text_box(self, habit) -> None:
        """The habitual-time field is a slot chooser, on both create and edit.

        It used to be a free-text input, which is how the graph came to hold an
        energy word in a time field (habit-rhythm arc M1/M3). Asserting every
        ``TimeOfDay`` member — rather than a sample — keeps a later slot from
        being added to the enum but missing from the form.
        """
        for label, form in (("create", HabitCreateForm()), ("edit", HabitEditForm(habit))):
            html = to_xml(form)
            select = re.search(r'<select[^>]*name="preferred_time".*?</select>', html, re.DOTALL)
            assert select, f"{label}: preferred_time is not rendered as a <select>"
            block = select.group(0)
            for slot in TimeOfDay:
                assert f'value="{slot.value}"' in block, f"{label}: slot {slot.value!r} missing"
            # Optional field → a blank choice, so "no declared slot" stays reachable.
            assert 'value=""' in block, f"{label}: no blank option"

    def test_habits_edit_preselects_the_stored_slot_and_duration(self, habit) -> None:
        html = to_xml(HabitEditForm(habit))
        assert re.search(r'<option[^>]*value="evening"[^>]*selected', html), (
            "stored slot not preselected"
        )
        assert re.search(r'<input[^>]*name="duration_minutes"[^>]*value="30"', html), (
            "stored duration not prefilled"
        )

    def test_choices_edit_prefills_decision_context(self, choice) -> None:
        """The promoted column is on the form and prefills from the entity."""
        html = to_xml(ChoiceEditForm(choice))
        assert 'name="decision_context"' in html
        assert "The current renderer can't do streaming." in html_lib.unescape(html)

    def test_principles_edit_prefills_why_important_from_its_own_column(self, principle) -> None:
        """Both fields prefill straight from the entity — no splice to reverse.

        The form passes no ``values`` override for either: ``why_important`` is a real
        ``Principle`` column, so ``entity=principle`` fills both textareas by name.
        """
        html = to_xml(PrincipleEditForm(principle))
        assert 'name="why_important"' in html
        assert "Foundational virtue." in html
        assert "Builds trust over time." in html

    def test_principles_edit_leaves_why_important_blank_when_unset(self, principle) -> None:
        """A Principle with no ``why_important`` renders the field empty, not absent."""
        plain = dataclasses.replace(
            principle, description="No motivation recorded.", why_important=None
        )

        html = to_xml(PrincipleEditForm(plain))
        assert "No motivation recorded." in html
        assert 'name="why_important"' in html
        assert "Builds trust over time." not in html

    def test_tasks_edit_prefills_title(self, task) -> None:
        html = to_xml(TaskEditForm(task))
        assert 'value="Write tests"' in html


# =============================================================================
# Helper guard — values keys must exist on the request model
# =============================================================================


class TestHelperValueKeyGuard:
    def test_unknown_values_key_raises(self, habit) -> None:
        with pytest.raises(ValueError, match=r"values keys.*not_a_field.*HabitUpdateRequest"):
            render_activity_form(
                domain_slug="habits",
                entity_name="Habit",
                request_model=HabitUpdateRequest,
                operation="edit",
                sections={"X": {"fields": ["title"]}},
                entity=habit,
                values={"not_a_field": "oops"},
            )

    def test_known_keys_pass_through(self, habit) -> None:
        """Sanity: a legitimate values override doesn't trip the guard."""
        ft = render_activity_form(
            domain_slug="habits",
            entity_name="Habit",
            request_model=HabitUpdateRequest,
            operation="edit",
            sections={"X": {"fields": ["title"]}},
            entity=habit,
            values={"title": "Overridden"},
        )
        html = to_xml(ft)
        assert 'value="Overridden"' in html

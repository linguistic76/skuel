"""The Tasks/Events edit forms can turn a linked edge and a checked box OFF.

This is the form→intent seam: the render half is pinned by
``tests/unit/ui/test_activity_forms_render.py``, the graph half by
``tests/integration/test_task_goal_edge_update_roundtrip.py``, and the step between them
decides whether "off" survives the submit at all.

Two controls have to post something for "off" to reach the write:

- An **edge picker** clear (``entityPicker.clear()`` in ``static/js/skuel.js``) blanks its
  hidden input, so the browser posts ``reinforces_habit_uid=""``. ``parse_form_body`` maps an
  empty string to ``None``, the field lands in ``model_fields_set``, and ``to_intent()``
  carries ``None`` — the ADR-066 explicit-clear signal both facades turn into an edge
  deletion (``TasksService._sync_relationship_edges`` / ``EventsService._replace_edge``).
- An **unchecked checkbox** is not a successful control, so ``FormGenerator`` renders a
  hidden ``"false"`` companion ahead of it. Without one the browser posts nothing, the
  field stays ``UNSET``, and the box cannot be turned off.

The mirror obligation: a field the edit form does **not** render stays ``UNSET``, so an
unrendered list field is never blanked into an edge wipe on save. The Tasks edit form
renders no goal picker for that reason: ``contributes_to_goal_uids`` is a full replace of
a task's goals, and a one-goal picker would wipe the rest.

Picker names are DERIVED from the rendered edit form rather than typed here, so renaming a
field on only one side of the seam fails the test instead of quietly dropping the value.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.form_helpers import parse_form_body
from core.models.enums import Priority
from core.models.enums.entity_enums import EntityStatus
from core.models.event.event import Event
from core.models.event.event_request import EventUpdateRequest
from core.models.sentinels import UNSET
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from ui.activities.events_form import EventEditForm
from ui.activities.tasks_form import TaskCreateForm, TaskEditForm


def _now() -> datetime:
    return datetime(2026, 5, 14, 12, 0, 0)


@pytest.fixture
def task() -> Task:
    return Task(
        uid="task_x",
        user_uid="u",
        title="Write tests",
        description="Edge-clear coverage",
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


# =============================================================================
# Helpers — derive the posted field names from the rendered form
# =============================================================================

_CSRF_NAMES = {"_csrf_token", "csrf_token"}


def _picker_names(html: str) -> set[str]:
    """Hidden-input names the EntityPicker widgets emit on this form.

    Every picker renders exactly one hidden input carrying the UID; the visible search box
    is deliberately unnamed so it never reaches the POST body. Keyed on the picker's own
    ``x-ref="hidden"`` marker rather than ``type="hidden"``, which every checkbox companion
    also carries.
    """
    names = {
        match.group(1)
        for tag in re.findall(r"<input[^>]*>", html)
        if 'x-ref="hidden"' in tag and (match := re.search(r'name="([^"]+)"', tag))
    }
    return names - _CSRF_NAMES


def _named_fields(html: str) -> set[str]:
    """Every field name the rendered form posts (inputs, selects, textareas)."""
    names = set(re.findall(r'<(?:input|select|textarea)[^>]*name="([^"]+)"', html))
    return names - _CSRF_NAMES


async def _parse[T](body: dict[str, str], schema: type[T]) -> T:
    request = Mock()
    request.form = AsyncMock(return_value=body)
    result = await parse_form_body(request, schema)
    assert not result.is_error, result.expect_error()
    return result.value


# =============================================================================
# Tasks
# =============================================================================


class TestTasksEditFormEdgeClear:
    def test_edit_form_renders_the_habit_picker_only(self, task: Task) -> None:
        """The derivation the clear tests rest on: one picker, named as the request is."""
        pickers = _picker_names(to_xml(TaskEditForm(task, habit_uid="habit_z")))
        assert pickers == {"reinforces_habit_uid"}
        assert pickers <= set(TaskUpdateRequest.model_fields), (
            "A picker posts a name TaskUpdateRequest does not declare — Pydantic would "
            "drop it and the edge would never change"
        )

    async def test_cleared_pickers_reach_the_intent_as_an_explicit_clear(self, task: Task) -> None:
        pickers = _picker_names(to_xml(TaskEditForm(task, habit_uid="habit_z")))
        body = {"title": task.title} | dict.fromkeys(pickers, "")

        intent = (await _parse(body, TaskUpdateRequest)).to_intent()

        assert intent.reinforces_habit_uid is None, "cleared habit picker must clear the edge"

    async def test_a_picked_uid_still_reaches_the_intent(self, task: Task) -> None:
        """The clear mapping must not swallow a real selection."""
        body = {"title": task.title, "reinforces_habit_uid": "habit_z"}

        intent = (await _parse(body, TaskUpdateRequest)).to_intent()

        assert intent.reinforces_habit_uid == "habit_z"

    async def test_fields_the_form_does_not_render_stay_untouched(self, task: Task) -> None:
        """Absent ≠ blank: a field off the form is UNSET, never an accidental clear.

        ``applies_knowledge_uids`` and ``contributes_to_goal_uids`` are on
        ``TaskUpdateRequest`` but on no edit section, so neither may reach the intent — were
        the form to render one as an empty input it would arrive as ``[]`` and wipe every
        APPLIES_KNOWLEDGE / CONTRIBUTES_TO_GOAL edge on save.
        """
        rendered = _named_fields(to_xml(TaskEditForm(task, habit_uid="habit_z")))
        assert "applies_knowledge_uids" not in rendered
        assert "contributes_to_goal_uids" not in rendered

        intent = (await _parse({"title": task.title}, TaskUpdateRequest)).to_intent()

        assert intent.applies_knowledge_uids is UNSET
        assert intent.contributes_to_goal_uids is UNSET
        assert "applies_knowledge_uids" not in intent.to_changes()


class TestTasksCreateFormGoalPicker:
    """The create form's goal picker posts one uid into a list field."""

    def test_the_picker_posts_the_request_field(self) -> None:
        pickers = _picker_names(to_xml(TaskCreateForm()))
        assert "contributes_to_goal_uids" in pickers
        assert pickers <= set(TaskCreateRequest.model_fields)

    async def test_a_picked_goal_is_a_one_goal_list(self) -> None:
        body = {"title": "Write tests", "contributes_to_goal_uids": "goal_y"}

        request = await _parse(body, TaskCreateRequest)

        assert request.contributes_to_goal_uids == ["goal_y"]

    async def test_an_empty_picker_is_no_goal(self) -> None:
        body = {"title": "Write tests", "contributes_to_goal_uids": ""}

        request = await _parse(body, TaskCreateRequest)

        assert request.contributes_to_goal_uids == []


# =============================================================================
# Events
# =============================================================================


class TestEventsEditFormEdgeClear:
    def test_edit_form_renders_both_pickers(self, event: Event) -> None:
        pickers = _picker_names(to_xml(EventEditForm(event)))
        assert pickers == {"reinforces_habit_uid", "milestone_celebration_for_goal"}
        assert pickers <= set(EventUpdateRequest.model_fields), (
            "A picker posts a name EventUpdateRequest does not declare — Pydantic would "
            "drop it and the edge would never change"
        )

    async def test_cleared_pickers_reach_the_intent_as_an_explicit_clear(
        self, event: Event
    ) -> None:
        pickers = _picker_names(to_xml(EventEditForm(event)))
        body = {"title": event.title} | dict.fromkeys(pickers, "")

        intent = (await _parse(body, EventUpdateRequest)).to_intent()

        assert intent.reinforces_habit_uid is None, "cleared habit picker must clear the edge"
        assert intent.milestone_celebration_for_goal is None, (
            "cleared goal picker must clear the edge"
        )

    async def test_a_picked_uid_still_reaches_the_intent(self, event: Event) -> None:
        body = {
            "title": event.title,
            "reinforces_habit_uid": "habit_z",
            "milestone_celebration_for_goal": "goal_y",
        }

        intent = (await _parse(body, EventUpdateRequest)).to_intent()

        assert intent.reinforces_habit_uid == "habit_z"
        assert intent.milestone_celebration_for_goal == "goal_y"


class TestEventsEditFormCheckboxOff:
    """An unchecked box reaches the write as False, not as an absent field."""

    def test_every_rendered_checkbox_has_a_hidden_false_companion(self, event: Event) -> None:
        html = to_xml(EventEditForm(event))
        checkboxes = {
            match.group(1)
            for tag in re.findall(r"<input[^>]*>", html)
            if 'type="checkbox"' in tag and (match := re.search(r'name="([^"]+)"', tag))
        }
        assert checkboxes, "the Events edit form renders booleans — the fixture must show one"
        for name in checkboxes:
            assert re.search(rf'<input type="hidden" name="{name}" value="false">', html), (
                f"{name} posts nothing when unchecked, so it could never be turned off"
            )

    async def test_unchecking_writes_false(self, event: Event) -> None:
        """The companion's value alone — what an unchecked box posts — means False."""
        body = {"title": event.title, "is_online": "false"}

        intent = (await _parse(body, EventUpdateRequest)).to_intent()

        assert intent.is_online is False
        assert intent.to_changes()["is_online"] is False

    async def test_checking_still_wins(self, event: Event) -> None:
        """A checked box appends "true" after the companion; FormData takes the last value."""
        body = {"title": event.title, "is_online": "true"}

        intent = (await _parse(body, EventUpdateRequest)).to_intent()

        assert intent.is_online is True

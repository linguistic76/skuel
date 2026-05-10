"""Unit tests for ``_SpawnOrchestrator``'s pure builder functions.

The builders ( ``_build_task``, ``_build_goal`` etc.) are pure: they take a
template, a UID map, and an engagement anchor, and return a frozen instance
dataclass. These tests verify:

- Template field copy-through is correct.
- Cross-template references resolve via the UID map.
- RelativeOffset fields resolve to absolute date/datetime against the anchor.
- ``template_uid`` and ``engagement_state`` are set correctly.

End-to-end ``spawn()`` is exercised by integration tests with a Neo4j fixture
(deferred — see Phase 4 verification block in the plan).
"""

from __future__ import annotations

from datetime import date, datetime

from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.event_template import EventTemplate
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.task_template import TaskTemplate
from core.services.ps_engagement._spawn_orchestrator import (
    _build_choice,
    _build_event,
    _build_goal,
    _build_habit,
    _build_principle,
    _build_task,
)

ANCHOR = datetime(2026, 5, 9, 12, 0, 0)
STUDENT = "user_alice"
PS = "ps_test"


class TestTaskBuilder:
    def test_basic_task_carries_template_uid_and_engaged_state(self) -> None:
        tt = TaskTemplate(uid="ttpl_a", title="Practice")
        task = _build_task(tt, STUDENT, ANCHOR, {"ttpl_a": "task_practice_xyz"})
        assert task.uid == "task_practice_xyz"
        assert task.user_uid == STUDENT
        assert task.template_uid == "ttpl_a"
        assert task.engagement_state == "engaged"
        assert task.title == "Practice"

    def test_due_offset_resolves_to_absolute_date(self) -> None:
        tt = TaskTemplate(
            uid="ttpl_off",
            title="t",
            due_offset=RelativeOffset(days=7),
            scheduled_offset=RelativeOffset(days=2),
        )
        task = _build_task(tt, STUDENT, ANCHOR, {"ttpl_off": "task_uid"})
        assert task.due_date == date(2026, 5, 16)
        assert task.scheduled_date == date(2026, 5, 11)

    def test_cross_template_refs_are_rewritten(self) -> None:
        tt = TaskTemplate(
            uid="ttpl_x",
            title="Task with refs",
            fulfills_goal_template_uid="gtpl_y",
            reinforces_habit_template_uid="htpl_z",
            scheduled_event_template_uid="etpl_w",
        )
        uid_map = {
            "ttpl_x": "task_uid",
            "gtpl_y": "goal_uid",
            "htpl_z": "habit_uid",
            "etpl_w": "event_uid",
        }
        task = _build_task(tt, STUDENT, ANCHOR, uid_map)
        assert task.fulfills_goal_uid == "goal_uid"
        assert task.reinforces_habit_uid == "habit_uid"
        assert task.scheduled_event_uid == "event_uid"

    def test_unset_offset_yields_none(self) -> None:
        tt = TaskTemplate(uid="ttpl_no_offset", title="t")
        task = _build_task(tt, STUDENT, ANCHOR, {"ttpl_no_offset": "task_uid"})
        assert task.due_date is None
        assert task.scheduled_date is None


class TestGoalBuilder:
    def test_goal_picks_up_source_path_step_uid(self) -> None:
        gt = GoalTemplate(uid="gtpl_a", title="Goal A")
        goal = _build_goal(gt, STUDENT, PS, ANCHOR, {"gtpl_a": "goal_a_uid"})
        assert goal.source_path_step_uid == PS
        assert goal.template_uid == "gtpl_a"
        assert goal.engagement_state == "engaged"

    def test_goal_offsets_resolve(self) -> None:
        gt = GoalTemplate(
            uid="gtpl_b",
            title="b",
            start_offset=RelativeOffset(days=0),
            target_offset=RelativeOffset(days=30),
        )
        goal = _build_goal(gt, STUDENT, PS, ANCHOR, {"gtpl_b": "goal_uid"})
        assert goal.start_date == date(2026, 5, 9)
        assert goal.target_date == date(2026, 6, 8)


class TestEventBuilder:
    def test_event_milestone_field_uses_asymmetric_instance_name(self) -> None:
        """Template field ends in `_template_uid`, instance field drops `_uid`."""
        et = EventTemplate(
            uid="etpl_party",
            title="Celebration",
            milestone_celebration_for_goal_template_uid="gtpl_target",
        )
        event = _build_event(
            et,
            STUDENT,
            ANCHOR,
            {"etpl_party": "event_uid", "gtpl_target": "goal_uid"},
        )
        assert event.milestone_celebration_for_goal == "goal_uid"
        # And the symmetric one too.
        assert event.template_uid == "etpl_party"


class TestHabitBuilder:
    def test_habit_recurrence_end_resolves(self) -> None:
        ht = HabitTemplate(
            uid="htpl_morning",
            title="Morning practice",
            recurrence_end_offset=RelativeOffset(days=90),
        )
        habit = _build_habit(ht, STUDENT, ANCHOR, {"htpl_morning": "habit_uid"})
        assert habit.recurrence_end_date == date(2026, 8, 7)
        assert habit.user_uid == STUDENT


class TestChoiceBuilder:
    def test_choice_decision_deadline_is_datetime_not_date(self) -> None:
        ct = ChoiceTemplate(
            uid="ctpl_pick",
            title="Pick path",
            decision_deadline_offset=RelativeOffset(days=3, hours=4),
        )
        choice = _build_choice(ct, STUDENT, PS, ANCHOR, {"ctpl_pick": "choice_uid"})
        assert isinstance(choice.decision_deadline, datetime)
        assert choice.decision_deadline == datetime(2026, 5, 12, 16, 0, 0)
        assert choice.source_path_step_uid == PS


class TestPrincipleBuilder:
    def test_principle_no_offset_no_refs_just_copy(self) -> None:
        pt = PrincipleTemplate(uid="ptpl_truth", title="Always truth-seek")
        principle = _build_principle(pt, STUDENT, PS, {"ptpl_truth": "principle_uid"})
        assert principle.uid == "principle_uid"
        assert principle.title == "Always truth-seek"
        assert principle.source_path_step_uid == PS
        assert principle.template_uid == "ptpl_truth"
        assert principle.engagement_state == "engaged"

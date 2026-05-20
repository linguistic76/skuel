"""Unit tests for ``_SpawnOrchestrator``'s pure builder functions.

The builders ( ``_build_task``, ``_build_goal`` etc.) are pure: they take a
template, the owning PathStep uid, a UID map, and an engagement anchor, and
return a frozen instance dataclass. These tests verify:

- Template field copy-through is correct.
- Cross-template references resolve via the UID map.
- RelativeOffset fields resolve to absolute date/datetime against the anchor.
- ``source_path_step_uid`` is populated uniformly on all six instances.
- ``engagement_state`` is set correctly. (The template back-reference is
  the ``(instance)-[:SPAWNED_FROM]->(template)`` graph edge, written
  atomically by the persistence layer — not by the builders themselves.
  See ``tests/integration/test_ps_engagement_lifecycle.py`` for the edge
  contract.)

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
    EVENT_CROSS_EDGES,
    TASK_CROSS_EDGES,
    _build_choice,
    _build_event,
    _build_goal,
    _build_habit,
    _build_principle,
    _build_task,
    _compute_cross_edges,
)

ANCHOR = datetime(2026, 5, 9, 12, 0, 0)
STUDENT = "user_alice"
PS = "ps_test"


class TestTaskBuilder:
    def test_basic_task_carries_engaged_state(self) -> None:
        tt = TaskTemplate(uid="ttpl_a", title="Practice")
        task = _build_task(tt, STUDENT, PS, ANCHOR, {"ttpl_a": "task_practice_xyz"})
        assert task.uid == "task_practice_xyz"
        assert task.user_uid == STUDENT
        assert task.engagement_state == "engaged"
        assert task.title == "Practice"
        assert task.source_path_step_uid == PS

    def test_due_offset_resolves_to_absolute_date(self) -> None:
        tt = TaskTemplate(
            uid="ttpl_off",
            title="t",
            due_offset=RelativeOffset(days=7),
            scheduled_offset=RelativeOffset(days=2),
        )
        task = _build_task(tt, STUDENT, PS, ANCHOR, {"ttpl_off": "task_uid"})
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
        task = _build_task(tt, STUDENT, PS, ANCHOR, uid_map)
        assert task.fulfills_goal_uid == "goal_uid"
        assert task.scheduled_event_uid == "event_uid"

    def test_habit_reinforcement_becomes_reinforces_habit_cross_edge(self) -> None:
        """Habit reinforcement is a REINFORCES_HABIT edge, not a property.

        ``_build_task`` no longer sets a ``reinforces_habit_uid`` property on the
        instance; the linkage is resolved by ``_compute_cross_edges`` into a
        ``(Task)-[:REINFORCES_HABIT]->(Habit)`` edge written by ``_persist``.
        """
        tt = TaskTemplate(
            uid="ttpl_x",
            title="Task with habit",
            reinforces_habit_template_uid="htpl_z",
        )
        uid_map = {"ttpl_x": "task_uid", "htpl_z": "habit_uid"}

        task = _build_task(tt, STUDENT, PS, ANCHOR, uid_map)
        # Derived field is not set by the builder (defaults to None).
        assert task.reinforces_habit_uid is None

        edges = _compute_cross_edges(tt, TASK_CROSS_EDGES, uid_map)
        assert edges == [("REINFORCES_HABIT", "habit_uid")]

    def test_unset_offset_yields_none(self) -> None:
        tt = TaskTemplate(uid="ttpl_no_offset", title="t")
        task = _build_task(tt, STUDENT, PS, ANCHOR, {"ttpl_no_offset": "task_uid"})
        assert task.due_date is None
        assert task.scheduled_date is None


class TestGoalBuilder:
    def test_goal_picks_up_source_path_step_uid(self) -> None:
        gt = GoalTemplate(uid="gtpl_a", title="Goal A")
        goal = _build_goal(gt, STUDENT, PS, ANCHOR, {"gtpl_a": "goal_a_uid"})
        assert goal.source_path_step_uid == PS
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
    def test_event_milestone_goal_becomes_celebrates_goal_cross_edge(self) -> None:
        """The milestone-celebration link is a CELEBRATES_GOAL edge, not a property.

        ``_build_event`` no longer sets a ``milestone_celebration_for_goal``
        property; the linkage is resolved by ``_compute_cross_edges`` into a
        ``(Event)-[:CELEBRATES_GOAL]->(Goal)`` edge that the orchestrator's
        ``_persist`` writes after the node.
        """
        et = EventTemplate(
            uid="etpl_party",
            title="Celebration",
            milestone_celebration_for_goal_template_uid="gtpl_target",
        )
        template_to_instance = {"etpl_party": "event_uid", "gtpl_target": "goal_uid"}

        # Builder produces a clean instance with no goal property.
        event = _build_event(et, STUDENT, PS, ANCHOR, template_to_instance)
        assert not hasattr(event, "milestone_celebration_for_goal")
        assert event.source_path_step_uid == PS

        # Cross-edge computation resolves the template ref to a CELEBRATES_GOAL edge.
        edges = _compute_cross_edges(et, EVENT_CROSS_EDGES, template_to_instance)
        assert edges == [("CELEBRATES_GOAL", "goal_uid")]


class TestHabitBuilder:
    def test_habit_recurrence_end_resolves(self) -> None:
        ht = HabitTemplate(
            uid="htpl_morning",
            title="Morning practice",
            recurrence_end_offset=RelativeOffset(days=90),
        )
        habit = _build_habit(ht, STUDENT, PS, ANCHOR, {"htpl_morning": "habit_uid"})
        assert habit.recurrence_end_date == date(2026, 8, 7)
        assert habit.user_uid == STUDENT
        assert habit.source_path_step_uid == PS


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
        assert principle.engagement_state == "engaged"

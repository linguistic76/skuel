"""Unit tests for ``_SpawnOrchestrator``'s pure spawn machinery.

``_build(spec, template, student_uid, ps_uid, anchor, uid_map)`` is pure: it
takes a ``DomainSpawnSpec``, a template, the owning PathStep uid, an engagement
anchor, and a UID map, and returns a frozen instance dataclass. These tests
verify, per domain spec:

- Template field copy-through is correct.
- Cross-template references resolve via the UID map (property rewrites) or via
  ``_compute_cross_edges`` (graph-edge rewrites).
- RelativeOffset fields resolve to absolute date/datetime against the anchor.
- ``source_path_step_uid`` is populated uniformly on all six instances.
- ``engagement_state`` is set to "engaged". (The template back-reference is the
  ``(instance)-[:SPAWNED_FROM]->(template)`` graph edge, written atomically by
  the persistence layer — not by ``_build``. See
  ``tests/integration/test_ps_engagement_lifecycle.py`` for the edge contract.)

``SPAWN_REGISTRY`` and its import-time validation are covered by ``TestRegistry``.
End-to-end ``spawn()`` is exercised by integration tests with a Neo4j fixture.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

from core.models.task.task import Task
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.event_template import EventTemplate
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.task_template import TaskTemplate
from core.services.ps_engagement._spawn_orchestrator import (
    CHOICE_SPEC,
    EVENT_SPEC,
    GOAL_SPEC,
    HABIT_SPEC,
    PRINCIPLE_SPEC,
    SPAWN_REGISTRY,
    TASK_SPEC,
    DomainSpawnSpec,
    _build,
    _compute_cross_edges,
    _validate_spawn_registry,
)

ANCHOR = datetime(2026, 5, 9, 12, 0, 0)
STUDENT = "user_alice"
PS = "ps_test"


class TestTaskBuilder:
    def test_basic_task_carries_engaged_state(self) -> None:
        tt = TaskTemplate(uid="ttpl_a", title="Practice")
        task = _build(TASK_SPEC, tt, STUDENT, PS, ANCHOR, {"ttpl_a": "task_practice_xyz"})
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
        task = _build(TASK_SPEC, tt, STUDENT, PS, ANCHOR, {"ttpl_off": "task_uid"})
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
        task = _build(TASK_SPEC, tt, STUDENT, PS, ANCHOR, uid_map)
        assert task.fulfills_goal_uid == "goal_uid"
        assert task.scheduled_event_uid == "event_uid"

    def test_habit_reinforcement_becomes_reinforces_habit_cross_edge(self) -> None:
        """Habit reinforcement is a REINFORCES_HABIT edge, not a property.

        ``_build`` does not set a ``reinforces_habit_uid`` property on the
        instance; the linkage is resolved by ``_compute_cross_edges`` into a
        ``(Task)-[:REINFORCES_HABIT]->(Habit)`` edge written by ``_persist``.
        """
        tt = TaskTemplate(
            uid="ttpl_x",
            title="Task with habit",
            reinforces_habit_template_uid="htpl_z",
        )
        uid_map = {"ttpl_x": "task_uid", "htpl_z": "habit_uid"}

        task = _build(TASK_SPEC, tt, STUDENT, PS, ANCHOR, uid_map)
        # Derived field is not set by the builder (defaults to None).
        assert task.reinforces_habit_uid is None

        edges = _compute_cross_edges(tt, TASK_SPEC.cross_edges, uid_map)
        assert edges == [("REINFORCES_HABIT", "habit_uid")]

    def test_unset_offset_yields_none(self) -> None:
        tt = TaskTemplate(uid="ttpl_no_offset", title="t")
        task = _build(TASK_SPEC, tt, STUDENT, PS, ANCHOR, {"ttpl_no_offset": "task_uid"})
        assert task.due_date is None
        assert task.scheduled_date is None


class TestGoalBuilder:
    def test_goal_picks_up_source_path_step_uid(self) -> None:
        gt = GoalTemplate(uid="gtpl_a", title="Goal A")
        goal = _build(GOAL_SPEC, gt, STUDENT, PS, ANCHOR, {"gtpl_a": "goal_a_uid"})
        assert goal.source_path_step_uid == PS
        assert goal.engagement_state == "engaged"

    def test_goal_offsets_resolve(self) -> None:
        gt = GoalTemplate(
            uid="gtpl_b",
            title="b",
            start_offset=RelativeOffset(days=0),
            target_offset=RelativeOffset(days=30),
        )
        goal = _build(GOAL_SPEC, gt, STUDENT, PS, ANCHOR, {"gtpl_b": "goal_uid"})
        assert goal.start_date == date(2026, 5, 9)
        assert goal.target_date == date(2026, 6, 8)

    def test_goal_inspired_by_choice_becomes_cross_edge(self) -> None:
        """``inspired_by_choice`` is an INSPIRED_BY_CHOICE edge, not a property."""
        gt = GoalTemplate(
            uid="gtpl_c",
            title="Inspired goal",
            inspired_by_choice_template_uid="ctpl_src",
        )
        uid_map = {"gtpl_c": "goal_uid", "ctpl_src": "choice_uid"}
        edges = _compute_cross_edges(gt, GOAL_SPEC.cross_edges, uid_map)
        assert edges == [("INSPIRED_BY_CHOICE", "choice_uid")]


class TestEventBuilder:
    def test_event_milestone_goal_becomes_celebrates_goal_cross_edge(self) -> None:
        """The milestone-celebration link is a CELEBRATES_GOAL edge, not a property.

        ``_build`` does not set a ``milestone_celebration_for_goal`` property;
        the linkage is resolved by ``_compute_cross_edges`` into a
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
        event = _build(EVENT_SPEC, et, STUDENT, PS, ANCHOR, template_to_instance)
        assert not hasattr(event, "milestone_celebration_for_goal")
        assert event.source_path_step_uid == PS

        # Cross-edge computation resolves the template ref to a CELEBRATES_GOAL edge.
        edges = _compute_cross_edges(et, EVENT_SPEC.cross_edges, template_to_instance)
        assert edges == [("CELEBRATES_GOAL", "goal_uid")]


class TestHabitBuilder:
    def test_habit_recurrence_end_resolves(self) -> None:
        ht = HabitTemplate(
            uid="htpl_morning",
            title="Morning practice",
            recurrence_end_offset=RelativeOffset(days=90),
        )
        habit = _build(HABIT_SPEC, ht, STUDENT, PS, ANCHOR, {"htpl_morning": "habit_uid"})
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
        choice = _build(CHOICE_SPEC, ct, STUDENT, PS, ANCHOR, {"ctpl_pick": "choice_uid"})
        assert isinstance(choice.decision_deadline, datetime)
        assert choice.decision_deadline == datetime(2026, 5, 12, 16, 0, 0)
        assert choice.source_path_step_uid == PS


class TestPrincipleBuilder:
    def test_principle_no_offset_no_refs_just_copy(self) -> None:
        pt = PrincipleTemplate(uid="ptpl_truth", title="Always truth-seek")
        principle = _build(PRINCIPLE_SPEC, pt, STUDENT, PS, ANCHOR, {"ptpl_truth": "principle_uid"})
        assert principle.uid == "principle_uid"
        assert principle.title == "Always truth-seek"
        assert principle.source_path_step_uid == PS
        assert principle.engagement_state == "engaged"


class TestRegistry:
    """The registry shape + its import-time fail-fast validation (ADR-061)."""

    def test_registry_covers_six_domains_in_layer_order(self) -> None:
        assert len(SPAWN_REGISTRY) == 6
        # Pre-allocation (declaration) order has non-decreasing layers, so the
        # orchestrator can build in declaration order without re-sorting.
        layers = [spec.layer for spec in SPAWN_REGISTRY]
        assert layers == sorted(layers)
        # Choice/Habit/Principle are layer 1; Task is the last layer.
        assert {CHOICE_SPEC.layer, HABIT_SPEC.layer, PRINCIPLE_SPEC.layer} == {1}
        assert TASK_SPEC.layer == max(layers)

    def test_every_spec_has_distinct_collection_attr(self) -> None:
        attrs = [spec.collection_attr for spec in SPAWN_REGISTRY]
        assert len(set(attrs)) == len(attrs)

    def test_validation_rejects_bad_offset_target(self) -> None:
        bad = replace(
            TASK_SPEC,
            offset_rewrites=(("due_offset", "not_a_real_task_field", "date"),),
        )
        with pytest.raises(ValueError, match="offset target 'not_a_real_task_field' not on Task"):
            _validate_spawn_registry((bad,))

    def test_validation_rejects_unknown_cross_edge_type(self) -> None:
        bad = replace(
            TASK_SPEC,
            cross_edges=(("reinforces_habit_template_uid", "NOT_A_REAL_EDGE"),),
        )
        with pytest.raises(ValueError, match="is not a RelationshipName"):
            _validate_spawn_registry((bad,))

    def test_validation_rejects_bad_collection_attr(self) -> None:
        bad = DomainSpawnSpec(
            instance_cls=Task,
            template_cls=TaskTemplate,
            layer=4,
            collection_attr="nonexistent",
            uid_prefix="task",
        )
        with pytest.raises(ValueError, match="collection_attr 'nonexistent'"):
            _validate_spawn_registry((bad,))

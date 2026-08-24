"""Completion stamping at the six Activity update chokepoints (PR-2 of the arc).

Three layers, matching how the stamp actually reaches the graph:

1. **The helper** (``completion_transition_patch`` / ``is_completion_transition``
   / ``is_reopen_transition``) — transition gating both ways, R1 reopen-clear,
   explicit-field authority, and the status-target legality check that turns
   ``EntityType.valid_statuses()`` from documentation into enforcement.
2. **The six chokepoints** — wiring tests assert the CALLER: each real
   ``update_<domain>`` core method is driven with a typed intent against a
   mocked backend, and the assertion is on what ``backend.update`` received.
   Posting ``status=completed`` lands a stamp; re-posting doesn't re-date;
   reopening clears; Principle's illegal ``completed`` is refused at the seam.
   (Route → facade-intent wiring is pinned separately in
   ``tests/unit/adapters/test_*_api_routes.py``.)
3. **The bypass doors fixed in this pass** — ``complete_tasks_bulk`` stamps per
   row (its gate is a write-time condition since ADR-087, like the Tasks
   chokepoint's); the DSL ``[x]`` create door parses the obsidian-tasks ``✅ date``
   into ``completion_date`` (falling back to today via the create-request default).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.choice.choice import Choice
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.event.event import Event
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.goal.goal import Goal
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.habit.habit import Habit
from core.models.habit.habit_update_intent import HabitUpdateIntent
from core.models.principle.principle import Principle
from core.models.principle.principle_update_intent import PrincipleUpdateIntent
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.completion_stamp import (
    completion_transition_patch,
    is_completion_transition,
    is_reopen_transition,
)
from core.utils.result_simplified import Result
from tests.helpers.status_guarded_backend import guarded_backend, guarded_rows_backend

USER = "user_stamp"


# ============================================================================
# 1. THE HELPER
# ============================================================================


class TestCompletionTransitionPatch:
    def test_no_status_in_changes_is_a_no_op(self):
        result = completion_transition_patch(EntityType.TASK, EntityStatus.ACTIVE, {"title": "x"})
        assert result.is_ok
        assert result.value == {}

    @pytest.mark.parametrize(
        ("entity_type", "field", "value_type"),
        [
            (EntityType.TASK, "completion_date", date),
            (EntityType.GOAL, "achieved_date", date),
            (EntityType.HABIT, "completed_at", datetime),
            (EntityType.EVENT, "completed_at", datetime),
            (EntityType.CHOICE, "completed_at", datetime),
        ],
    )
    def test_transition_into_completed_stamps_the_domain_field(
        self, entity_type, field, value_type
    ):
        result = completion_transition_patch(
            entity_type, EntityStatus.ACTIVE, {"status": "completed"}
        )
        assert result.is_ok
        assert set(result.value) == {field}
        assert type(result.value[field]) is value_type  # date, not datetime, for Task/Goal

    def test_reposting_completed_does_not_restamp(self):
        result = completion_transition_patch(
            EntityType.TASK, EntityStatus.COMPLETED, {"status": "completed"}
        )
        assert result.is_ok
        assert result.value == {}, "re-posting completed on a completed entity re-dated it"

    def test_reopen_clears_the_stamp(self):
        result = completion_transition_patch(
            EntityType.GOAL, EntityStatus.COMPLETED, {"status": "active"}
        )
        assert result.is_ok
        assert result.value == {"achieved_date": None}

    def test_explicit_completion_field_keeps_authority_on_complete(self):
        changes = {"status": "completed", "achieved_date": date(2026, 8, 1)}
        result = completion_transition_patch(EntityType.GOAL, EntityStatus.ACTIVE, changes)
        assert result.is_ok
        assert result.value == {}, "helper overrode an explicit complete path's own stamp"

    def test_explicit_completion_field_keeps_authority_on_reopen(self):
        changes = {"status": "active", "completion_date": date(2026, 8, 1)}
        result = completion_transition_patch(EntityType.TASK, EntityStatus.COMPLETED, changes)
        assert result.is_ok
        assert result.value == {}

    def test_unknown_old_status_is_treated_as_not_completed(self):
        result = completion_transition_patch(EntityType.TASK, None, {"status": "completed"})
        assert result.is_ok
        assert "completion_date" in result.value

    def test_lateral_transition_between_non_completed_statuses_is_a_no_op(self):
        result = completion_transition_patch(
            EntityType.TASK, EntityStatus.ACTIVE, {"status": "paused"}
        )
        assert result.is_ok
        assert result.value == {}

    def test_garbage_status_is_refused(self):
        result = completion_transition_patch(
            EntityType.TASK, EntityStatus.ACTIVE, {"status": "in_progress"}
        )
        assert result.is_error

    def test_none_status_is_refused(self):
        result = completion_transition_patch(EntityType.TASK, EntityStatus.ACTIVE, {"status": None})
        assert result.is_error

    def test_status_outside_the_types_lifecycle_is_refused(self):
        # COMPLETED is a canonical EntityStatus but not a valid Principle status.
        result = completion_transition_patch(
            EntityType.PRINCIPLE, EntityStatus.ACTIVE, {"status": "completed"}
        )
        assert result.is_error
        # ARCHIVED is not in Task's valid set either.
        result = completion_transition_patch(
            EntityType.TASK, EntityStatus.ACTIVE, {"status": "archived"}
        )
        assert result.is_error

    def test_principle_legal_status_passes_with_no_stamp(self):
        result = completion_transition_patch(
            EntityType.PRINCIPLE, EntityStatus.ACTIVE, {"status": "archived"}
        )
        assert result.is_ok
        assert result.value == {}


class TestIsCompletionTransition:
    def test_true_only_on_the_transition(self):
        assert is_completion_transition(EntityStatus.ACTIVE, {"status": "completed"})
        assert is_completion_transition("active", {"status": "completed"})
        assert not is_completion_transition(EntityStatus.COMPLETED, {"status": "completed"})
        assert not is_completion_transition(EntityStatus.ACTIVE, {"status": "paused"})
        assert not is_completion_transition(EntityStatus.ACTIVE, {"title": "x"})


class TestIsReopenTransition:
    """The mirror gate — what publishes ``TaskReopened`` (PR-6 of the arc)."""

    def test_true_only_on_the_transition_out(self):
        assert is_reopen_transition(EntityStatus.COMPLETED, {"status": "active"})
        assert is_reopen_transition("completed", {"status": "scheduled"})
        assert not is_reopen_transition(EntityStatus.COMPLETED, {"status": "completed"})
        assert not is_reopen_transition(EntityStatus.ACTIVE, {"status": "paused"})
        assert not is_reopen_transition(EntityStatus.COMPLETED, {"title": "x"})
        assert not is_reopen_transition(None, {"status": "active"})

    def test_an_unrecognized_target_is_not_a_reopen(self):
        """It is a validation failure in ``completion_transition_patch``, and the
        two must agree — otherwise a garbage status would publish a reopen that
        the write itself refuses."""
        assert not is_reopen_transition(EntityStatus.COMPLETED, {"status": "not_a_status"})

    def test_the_gate_agrees_with_the_stamp_clear(self):
        """Whenever this says reopen, the patch clears the stamp, and vice versa.

        Swept over every legal Task status so a new enum member cannot split the
        two apart unnoticed.
        """
        for old in (EntityStatus.COMPLETED, EntityStatus.ACTIVE):
            for new in sorted(s.value for s in EntityType.TASK.valid_statuses()):
                patch = completion_transition_patch(EntityType.TASK, old, {"status": new})
                assert patch.is_ok
                clears = patch.value.get("completion_date", "absent") is None
                assert clears is is_reopen_transition(old, {"status": new})


# ============================================================================
# 2. THE SIX CHOKEPOINTS — wiring tests assert the caller
# ============================================================================


def _mock_backend(current, updated):
    """Backend mock: ``get`` returns the current model, ``update`` the updated one."""
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(current))
    backend.update = AsyncMock(return_value=Result.ok(updated))
    return backend


def _written_changes(backend) -> dict:
    (_uid, changes) = backend.update.await_args.args
    return changes


@pytest.mark.asyncio
class TestTasksChokepoint:
    """Tasks states its stamp rules as write-time CONDITIONS now (ADR-087).

    The other five chokepoints below still resolve the patch in Python from a prior
    read beforehand; Tasks hands the condition to the write, which evaluates it
    against the status it captures under the node's lock. So the assertions here are
    on the guard the service built — plus, via the recorder, on what that guard would
    actually merge. That the database honours the condition is pinned against a real
    Neo4j in ``tests/integration/test_status_guarded_update.py``.
    """

    def _service(self, current_status: EntityStatus):
        from core.services.tasks.tasks_core_service import TasksCoreService

        current = Task(uid="task_1", user_uid=USER, title="t", status=current_status)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        backend, recorder = guarded_backend(current, updated)
        return TasksCoreService(backend=backend), backend, recorder

    async def test_completing_stamps_completion_date(self):
        service, _backend, recorder = self._service(EntityStatus.ACTIVE)
        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))
        assert result.is_ok
        # The stamp is offered CONDITIONALLY — only if the prior was not already
        # completed. That condition is what stops a re-post re-dating.
        assert recorder.last_guard.patch_if_prior_not_in == (
            frozenset({"completed"}),
            {"completion_date": date.today()},
        )
        assert recorder.merged_patch()["completion_date"] == date.today()

    async def test_reposting_completed_does_not_restamp(self):
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))
        assert result.is_ok
        # Same guard as above — the prior is what declines it.
        assert "completion_date" not in recorder.merged_patch()

    async def test_reopen_clears_the_stamp(self):
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_task("task_1", TaskUpdateIntent(status="active"))
        assert result.is_ok
        assert recorder.last_guard.patch_if_prior_in == (
            frozenset({"completed"}),
            {"completion_date": None},
        )
        assert recorder.merged_patch()["completion_date"] is None

    async def test_a_caller_supplied_stamp_keeps_authority(self):
        """An update that carries the field itself gets no patches at all — the
        same authority rule the Python-side helper enforces."""
        service, _backend, recorder = self._service(EntityStatus.ACTIVE)
        explicit = date(2026, 1, 1)
        result = await service.update_task(
            "task_1", TaskUpdateIntent(status="completed", completion_date=explicit)
        )
        assert result.is_ok
        assert recorder.last_guard.has_patches() is False
        assert recorder.merged_patch()["completion_date"] == explicit

    async def test_illegal_status_is_refused_before_the_write(self):
        service, backend, _recorder = self._service(EntityStatus.ACTIVE)
        result = await service.update_task("task_1", TaskUpdateIntent(status="archived"))
        assert result.is_error
        backend.update_with_status_guard.assert_not_awaited()

    async def test_a_status_write_no_longer_pre_reads_at_all(self):
        """The read whose failure used to be able to re-date a stamp is GONE: the
        prior now rides back on the write. What was defended by failing fast on a
        transient read error is defended by construction (ADR-087)."""
        service, backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))
        assert result.is_ok
        backend.get.assert_not_awaited()
        assert recorder.calls[-1][2].has_patches() is True

    async def test_a_failed_priority_read_still_fails_the_update(self):
        """The advisory read survives for the overdue-priority rule, and a
        transient failure there must not be read as "no rule applies"."""
        from core.utils.result_simplified import Errors

        service, backend, _recorder = self._service(EntityStatus.ACTIVE)
        backend.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "transient read failure"))
        )
        result = await service.update_task("task_1", TaskUpdateIntent(priority="high"))
        assert result.is_error
        backend.update_with_status_guard.assert_not_awaited()


@pytest.mark.asyncio
class TestGoalsChokepoint:
    def _service(self, current_status: EntityStatus):
        from core.services.goals.goals_core_service import GoalsCoreService

        current = Goal(uid="goal_1", user_uid=USER, title="g", status=current_status)
        updated = Goal(uid="goal_1", user_uid=USER, title="g", status=EntityStatus.COMPLETED)
        backend = _mock_backend(current, updated)
        return GoalsCoreService(backend=backend), backend

    async def test_completing_stamps_achieved_date(self):
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="completed"))
        assert result.is_ok
        assert _written_changes(backend)["achieved_date"] == date.today()

    async def test_reposting_completed_does_not_restamp(self):
        # Achievement immutability dropped (ruled 2026-08-22): completed goals
        # are editable like completed tasks, and the transition gate carries the
        # no-re-dating guarantee instead of the old blanket refusal.
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="completed"))
        assert result.is_ok
        assert "achieved_date" not in _written_changes(backend)

    async def test_reopen_clears_the_stamp(self):
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="active"))
        assert result.is_ok
        assert _written_changes(backend)["achieved_date"] is None

    async def test_reopen_resets_progress_percentage(self):
        # Codex round 3: without the reset a reopened goal stays a "100%
        # complete" ACTIVE goal — misread by progress consumers, and instantly
        # re-achieved by the next contribution increment.
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="active"))
        assert result.is_ok
        assert _written_changes(backend)["progress_percentage"] == 0.0

    async def test_reopen_caller_progress_keeps_authority(self):
        service, backend = self._service(EntityStatus.COMPLETED)
        intent = GoalUpdateIntent(status="active", progress_percentage=42.0)
        result = await service.update_goal("goal_1", intent)
        assert result.is_ok
        assert _written_changes(backend)["progress_percentage"] == 42.0

    async def test_activate_goal_reopens_a_completed_goal(self):
        # The live reopen door: POST /api/goals/{uid}/status → set_status →
        # activate_goal. The old rule killed this before the write.
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.activate_goal("goal_1")
        assert result.is_ok
        changes = _written_changes(backend)
        assert changes["status"] == EntityStatus.ACTIVE.value
        assert changes["achieved_date"] is None
        assert changes["progress_percentage"] == 0.0

    async def test_archive_goal_archives_a_completed_goal(self):
        # A terminal target is not a reopen: the historical 100% progress
        # stays (only the stamp obeys the non-null-exactly-when-completed
        # invariant).
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.archive_goal("goal_1")
        assert result.is_ok
        changes = _written_changes(backend)
        assert changes["status"] == EntityStatus.ARCHIVED.value
        assert "progress_percentage" not in changes

    async def test_cancel_transition_on_a_completed_goal_reaches_the_write(self):
        # The facade's cancel_goal delegates here after its active-tasks guard
        # (which is status-agnostic and unrelated to the deleted rule).
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="cancelled"))
        assert result.is_ok
        assert _written_changes(backend)["status"] == EntityStatus.CANCELLED.value
        assert _written_changes(backend)["achieved_date"] is None

    async def test_complete_goal_transition_stamps_today(self):
        # complete_goal's default path carries no achieved_date — the stamp
        # comes from the transition gate at the chokepoint.
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.complete_goal("goal_1")
        assert result.is_ok
        assert _written_changes(backend)["achieved_date"] == date.today()

    async def test_complete_goal_on_an_already_completed_goal_does_not_redate(self):
        # Codex P1: set_status("completed") on an already-completed goal
        # dispatches here; with the immutability rule gone, a re-posted
        # complete must keep the original achieved_date.
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.complete_goal("goal_1")
        assert result.is_ok
        assert "achieved_date" not in _written_changes(backend)

    async def test_pause_goal_single_write_carries_status_and_metadata(self):
        # Codex P2: pause metadata rides the status write, so one Result
        # answers for both (no discarded second write).
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.pause_goal("goal_1", reason="resting")
        assert result.is_ok
        assert backend.update.await_count == 1
        changes = _written_changes(backend)
        assert changes["status"] == EntityStatus.PAUSED.value
        assert changes["metadata"]["pause_reason"] == "resting"

    def _flaky_pre_read_service(self):
        # Pre-read fails transiently, any later read would succeed — the
        # scenario where a swallowed pre-read error becomes a silent
        # metadata-less "success" (Codex round 2).
        from core.services.goals.goals_core_service import GoalsCoreService
        from core.utils.result_simplified import Errors

        current = Goal(uid="goal_1", user_uid=USER, title="g", status=EntityStatus.ACTIVE)
        backend = _mock_backend(current, current)
        backend.get = AsyncMock(
            side_effect=[
                Result.fail(Errors.database("get", "transient read failure")),
                Result.ok(current),
            ]
        )
        return GoalsCoreService(backend=backend), backend

    async def test_pause_goal_failed_pre_read_fails_the_pause(self):
        service, backend = self._flaky_pre_read_service()
        result = await service.pause_goal("goal_1", reason="resting")
        assert result.is_error
        backend.update.assert_not_awaited()

    async def test_archive_goal_failed_pre_read_fails_the_archive(self):
        service, backend = self._flaky_pre_read_service()
        result = await service.archive_goal("goal_1")
        assert result.is_error
        backend.update.assert_not_awaited()

    async def test_complete_goal_failed_notes_pre_read_fails_the_complete(self):
        service, backend = self._flaky_pre_read_service()
        result = await service.complete_goal("goal_1", completion_notes="done")
        assert result.is_error
        backend.update.assert_not_awaited()

    async def test_explicit_achieved_date_keeps_authority(self):
        # complete_goal's path: the intent already carries achieved_date.
        service, backend = self._service(EntityStatus.ACTIVE)
        intent = GoalUpdateIntent(status="completed", achieved_date=date(2026, 8, 1))
        result = await service.update_goal("goal_1", intent)
        assert result.is_ok
        assert _written_changes(backend)["achieved_date"] == date(2026, 8, 1)


@pytest.mark.asyncio
class TestHabitsChokepoint:
    def _service(self, current_status: EntityStatus):
        from core.services.habits.habits_core_service import HabitsCoreService

        current = Habit(uid="habit_1", user_uid=USER, title="h", status=current_status)
        updated = Habit(uid="habit_1", user_uid=USER, title="h", status=EntityStatus.COMPLETED)
        backend = _mock_backend(current, updated)
        return HabitsCoreService(backend=backend), backend

    async def test_completing_stamps_completed_at(self):
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.update_habit("habit_1", HabitUpdateIntent(status="completed"))
        assert result.is_ok
        assert isinstance(_written_changes(backend)["completed_at"], datetime)

    async def test_reposting_completed_does_not_restamp(self):
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_habit("habit_1", HabitUpdateIntent(status="completed"))
        assert result.is_ok
        assert "completed_at" not in _written_changes(backend)

    async def test_reopen_clears_the_stamp(self):
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_habit("habit_1", HabitUpdateIntent(status="active"))
        assert result.is_ok
        assert _written_changes(backend)["completed_at"] is None


@pytest.mark.asyncio
class TestEventsChokepoint:
    def _service(self, current_status: EntityStatus):
        from core.services.events.events_core_service import EventsCoreService

        # Today's event: past-event immutability must not gate the transition.
        current = Event(
            uid="event_1", user_uid=USER, title="e", status=current_status, event_date=date.today()
        )
        updated = Event(
            uid="event_1",
            user_uid=USER,
            title="e",
            status=EntityStatus.COMPLETED,
            event_date=date.today(),
        )
        backend = _mock_backend(current, updated)
        return EventsCoreService(backend=backend), backend

    async def test_completing_stamps_completed_at(self):
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.update_event("event_1", EventUpdateIntent(status="completed"))
        assert result.is_ok
        assert isinstance(_written_changes(backend)["completed_at"], datetime)

    async def test_reposting_completed_does_not_restamp(self):
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_event("event_1", EventUpdateIntent(status="completed"))
        assert result.is_ok
        assert "completed_at" not in _written_changes(backend)

    async def test_reopen_clears_the_stamp(self):
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_event("event_1", EventUpdateIntent(status="active"))
        assert result.is_ok
        assert _written_changes(backend)["completed_at"] is None


@pytest.mark.asyncio
class TestChoicesChokepoint:
    def _service(self, current_status: EntityStatus):
        from core.services.choices.choices_core_service import ChoicesCoreService

        # DRAFT current: decision immutability blocks status changes on
        # ACTIVE/COMPLETED choices, so the completable state is DRAFT.
        current = Choice(uid="choice_1", user_uid=USER, title="c", status=current_status)
        updated = Choice(uid="choice_1", user_uid=USER, title="c", status=EntityStatus.COMPLETED)
        backend = _mock_backend(current, updated)
        return ChoicesCoreService(backend=backend), backend

    async def test_completing_stamps_completed_at(self):
        service, backend = self._service(EntityStatus.DRAFT)
        result = await service.update_choice("choice_1", ChoiceUpdateIntent(status="completed"))
        assert result.is_ok
        assert isinstance(_written_changes(backend)["completed_at"], datetime)

    async def test_illegal_status_is_refused_before_the_write(self):
        # PAUSED is canonical but outside Choice's lifecycle.
        service, backend = self._service(EntityStatus.DRAFT)
        result = await service.update_choice("choice_1", ChoiceUpdateIntent(status="paused"))
        assert result.is_error
        backend.update.assert_not_awaited()


@pytest.mark.asyncio
class TestPrinciplesChokepoint:
    def _service(self, current_status: EntityStatus):
        from core.services.principles.principles_core_service import PrinciplesCoreService

        current = Principle(uid="principle_1", user_uid=USER, title="p", status=current_status)
        updated = Principle(
            uid="principle_1", user_uid=USER, title="p", status=EntityStatus.ARCHIVED
        )
        backend = _mock_backend(current, updated)
        return PrinciplesCoreService(backend=backend), backend

    async def test_illegal_completed_write_is_refused(self):
        # The bug this fixes: POST /api/principles/{uid}/status happily wrote
        # an illegal `completed` — nothing enforced the transition map.
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.update_principle(
            "principle_1", PrincipleUpdateIntent(status="completed")
        )
        assert result.is_error
        backend.update.assert_not_awaited()

    async def test_legal_status_writes_with_no_stamp(self):
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.update_principle(
            "principle_1", PrincipleUpdateIntent(status="archived")
        )
        assert result.is_ok
        changes = _written_changes(backend)
        assert changes["status"] == "archived"
        assert "completed_at" not in changes


# ============================================================================
# 3. BYPASS DOORS FIXED IN THIS PASS
# ============================================================================


@pytest.mark.asyncio
class TestCompleteTasksBulk:
    async def test_bulk_complete_stamps_only_the_transitioning_rows(self):
        # A bulk list may contain already-completed tasks (retry, mixed
        # selection) — their original completion_date must survive (Codex P2 on
        # #1123: unconditional stamping is the re-dating bug in miniature). Since
        # ADR-087 the row's OWN write decides that, from the status it captured
        # under that node's lock, so the assertion is on the patch each row merged.
        from core.services.tasks.tasks_core_service import TasksCoreService

        active = Task(uid="task_active", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        done = Task(
            uid="task_done",
            user_uid=USER,
            title="t",
            status=EntityStatus.COMPLETED,
            completion_date=date(2026, 8, 1),
        )
        backend, store = guarded_rows_backend({"task_active": active, "task_done": done})
        service = TasksCoreService(backend=backend)

        result = await service.complete_tasks_bulk(["task_active", "task_done"], USER)

        assert result.is_ok
        assert result.value == 2
        assert store.merged["task_active"]["status"] == EntityStatus.COMPLETED.value
        assert store.merged["task_active"]["completion_date"] == date.today()
        assert "completion_date" not in store.merged["task_done"], (
            "bulk-completing an already-completed task re-dated its completion"
        )
        # One guard for the whole batch, offering the stamp CONDITIONALLY — the
        # per-row priors are what accept or decline it.
        assert all(guard is store.calls[0][2] for _uid, _updates, guard in store.calls)

    async def test_bulk_complete_skips_rows_that_cannot_be_written(self):
        # A row the write cannot find is skipped (not counted) rather than counted
        # as a completion nothing made. Before ADR-087 this was a failed pre-READ;
        # the read is gone, so the write's own not-found is the same protection.
        from core.services.tasks.tasks_core_service import TasksCoreService

        # Annotated: an all-``None`` map carries no row for the generic to infer from,
        # and a generic FUNCTION is not subscriptable at runtime (PEP 695) — so the
        # binding has to come through the argument's own type.
        rows: dict[str, Task | None] = {"task_1": None}
        backend, store = guarded_rows_backend(rows)
        service = TasksCoreService(backend=backend)

        result = await service.complete_tasks_bulk(["task_1"], USER)

        assert result.is_ok
        assert result.value == 0
        assert store.merged == {}


class TestDslDoneDateParse:
    def test_checked_line_with_done_date_parses_it(self):
        from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed

        parsed = obsidian_task_line_to_parsed("- [x] Review notes ✅ 2026-08-15")
        assert parsed is not None
        assert parsed.is_checked
        assert parsed.completion_date == date(2026, 8, 15)
        assert "✅" not in parsed.description

    def test_checked_line_without_done_date_has_none(self):
        from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed

        parsed = obsidian_task_line_to_parsed("- [x] Review notes")
        assert parsed is not None
        assert parsed.completion_date is None

    def test_unchecked_line_carries_no_completion_claim(self):
        from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed

        parsed = obsidian_task_line_to_parsed("- [ ] Review notes ✅ 2026-08-15")
        assert parsed is not None
        assert parsed.completion_date is None

    def test_converter_carries_the_done_date_onto_the_request(self):
        from core.services.dsl.activity_domain_converters import activity_to_task_request
        from core.services.dsl.activity_dsl_parser import ParsedActivityLine

        activity = ParsedActivityLine(
            description="Review notes",
            contexts=[EntityType.TASK],
            is_checked=True,
            completion_date=date(2026, 8, 15),
        )
        result = activity_to_task_request(activity)
        assert result.is_ok
        request = result.value
        assert isinstance(request, TaskCreateRequest)
        assert request.status == EntityStatus.COMPLETED
        assert request.completion_date == date(2026, 8, 15)

    def test_checked_line_with_no_date_falls_back_to_today(self):
        from core.services.dsl.activity_domain_converters import activity_to_task_request
        from core.services.dsl.activity_dsl_parser import ParsedActivityLine

        activity = ParsedActivityLine(
            description="Review notes", contexts=[EntityType.TASK], is_checked=True
        )
        result = activity_to_task_request(activity)
        assert result.is_ok
        request = result.value
        assert isinstance(request, TaskCreateRequest)
        assert request.completion_date == date.today()

    def test_unchecked_line_yields_no_completion_date(self):
        from core.services.dsl.activity_domain_converters import activity_to_task_request
        from core.services.dsl.activity_dsl_parser import ParsedActivityLine

        activity = ParsedActivityLine(description="Review notes", contexts=[EntityType.TASK])
        result = activity_to_task_request(activity)
        assert result.is_ok
        request = result.value
        assert isinstance(request, TaskCreateRequest)
        assert request.status == EntityStatus.DRAFT
        assert request.completion_date is None


class TestTaskCreateRequestCompletionDefault:
    def test_completed_create_defaults_to_today(self):
        request = TaskCreateRequest(title="t", status=EntityStatus.COMPLETED)
        assert request.completion_date == date.today()

    def test_completion_date_on_a_non_completed_create_is_refused(self):
        # A DRAFT task carrying a completion stamp would break the field's
        # invariant (non-null exactly when completed) — Codex P2 on #1123.
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="completion_date requires"):
            TaskCreateRequest(title="t", completion_date=date(2026, 8, 15))

    def test_future_completion_date_is_refused(self):
        # A future completion is semantically impossible and would pin itself
        # atop completion-date-ordered reads — Codex P2 on #1123.
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="cannot be in the future"):
            TaskCreateRequest(
                title="t",
                status=EntityStatus.COMPLETED,
                completion_date=date.today() + timedelta(days=1),
            )

    def test_supplied_date_is_kept(self):
        request = TaskCreateRequest(
            title="t", status=EntityStatus.COMPLETED, completion_date=date(2026, 8, 15)
        )
        assert request.completion_date == date(2026, 8, 15)

    def test_draft_create_stays_dateless(self):
        request = TaskCreateRequest(title="t")
        assert request.completion_date is None

    def test_from_request_carries_the_stamp_onto_the_task(self):
        request = TaskCreateRequest(
            title="t", status=EntityStatus.COMPLETED, completion_date=date(2026, 8, 15)
        )
        task = Task.from_request(request, user_uid=USER)
        assert task.completion_date == date(2026, 8, 15)


# ============================================================================
# 4. THE EXPLICIT COMPLETE PATH (PR-3)
# ============================================================================


@pytest.mark.asyncio
class TestCompleteTaskWithCascade:
    """``complete_task_with_cascade`` gates its own stamp on the same transition.

    It writes through the *generic* CRUD update, so the six-chokepoint helper
    never sees this path — the stamp is the method's own, and used to be
    unconditional. Two live callers re-enter it behind an ownership check only
    (``POST /today/tasks/{uid}/complete`` and
    ``UserContextService.complete_task_with_context``), so a repeat call is
    reachable; with the vault ``✅`` now reading ``completion_date``, a re-date
    would propagate into the user's own files.
    """

    @staticmethod
    def _service_over(task: Task):
        from core.services.tasks.tasks_progress_service import TasksProgressService

        stored = task.to_dto().to_dict()
        backend, recorder = guarded_backend(stored, stored)
        backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
        return TasksProgressService(backend=backend), recorder

    async def test_completing_an_active_task_stamps_today(self):
        task = Task(uid="task_a", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        service, recorder = self._service_over(task)

        result = await service.complete_task_with_cascade("task_a", user_context=None)

        assert result.is_ok
        # The stamp is OFFERED, conditionally on the prior not already being
        # completed — the door no longer picks it from a status it read first.
        assert recorder.last_guard.patch_if_prior_not_in == (
            frozenset({"completed"}),
            {"completion_date": date.today()},
        )
        merged = recorder.merged_patch()
        assert merged["status"] == EntityStatus.COMPLETED.value
        assert merged["completion_date"] == date.today()

    async def test_re_completing_does_not_re_date_the_completion(self):
        task = Task(
            uid="task_b",
            user_uid=USER,
            title="t",
            status=EntityStatus.COMPLETED,
            completion_date=date(2026, 4, 2),
        )
        service, recorder = self._service_over(task)

        result = await service.complete_task_with_cascade("task_b", user_context=None)

        assert result.is_ok
        # Same guard as above — the prior is what declines it. The write still
        # happens: a repeat complete stays a real complete (the repair path).
        merged = recorder.merged_patch()
        assert merged["status"] == EntityStatus.COMPLETED.value
        assert "completion_date" not in merged, (
            "re-completing an already-completed task re-dated its completion"
        )

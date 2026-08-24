"""Completion stamping at the six Activity update chokepoints (ADR-087 arc).

Three layers, matching how the stamp actually reaches the graph:

1. **The helper** (``completion_transition_patch`` / ``is_completion_transition``
   / ``is_reopen_transition``) — transition gating both ways, R1 reopen-clear,
   explicit-field authority, and the status-target legality check that turns
   ``EntityType.valid_statuses()`` from documentation into enforcement.
2. **The six chokepoints** — wiring tests assert the CALLER: each real
   ``update_<domain>`` core method is driven with a typed intent against a
   mocked backend. Five of them (Task, Goal, Habit, Event, Choice) state their
   rules as write-time CONDITIONS since ADR-087, so the assertion is on the
   ``StatusWriteGuard`` the service built — and, via the recorder, on what that
   guard would actually merge for a given prior. Principle still resolves its
   (legality-only) check in Python and is asserted on ``backend.update``.
   Posting ``status=completed`` lands a stamp; re-posting doesn't re-date;
   reopening clears; Principle's illegal ``completed`` is refused at the seam.
   Each domain also has a test that its ``_validate_update`` rules still FIRE:
   moving these chokepoints off ``CrudOperationsMixin.update`` took the hook off
   the path, so the explicit call is now the only thing keeping them alive.
   (Route → facade-intent wiring is pinned separately in
   ``tests/unit/adapters/test_*_api_routes.py``.)
3. **The bypass doors** — ``complete_tasks_bulk`` stamps per
   row (its gate is a write-time condition since ADR-087, like the Tasks
   chokepoint's); the DSL ``[x]`` create door parses the obsidian-tasks ``✅ date``
   into ``completion_date`` (falling back to today via the create-request default).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.events.base import BaseEvent
from core.events.calendar_event_events import CalendarEventCompleted
from core.events.goal_events import GoalAchieved
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
from tests.helpers.status_guarded_backend import (
    StatusGuardedWriteRecorder,
    guarded_backend,
    guarded_rows_backend,
)

if TYPE_CHECKING:
    from core.services.choices.choices_core_service import ChoicesCoreService
    from core.services.events.events_core_service import EventsCoreService
    from core.services.goals.goals_core_service import GoalsCoreService
    from core.services.habits.habits_core_service import HabitsCoreService

USER = "user_stamp"


class _CapturingBus:
    """Records what a chokepoint publishes; ``publish_async`` is the whole contract.

    ``of`` narrows to the subtype asked for, so a test that reads a field off the
    result is type-checked against the event it actually selected.
    """

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


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
    """Goals states its stamp rules — and the reopen progress reset — as write-time
    CONDITIONS (ADR-087 PR-3). Both condition on the same prior ("was it completed?"),
    so they merge into one patch the write picks or declines as a unit.
    """

    def _service(
        self, current_status: EntityStatus, **current_fields: Any
    ) -> tuple[GoalsCoreService, Mock, StatusGuardedWriteRecorder[Goal]]:
        from core.services.goals.goals_core_service import GoalsCoreService

        current = Goal(
            uid="goal_1", user_uid=USER, title="g", status=current_status, **current_fields
        )
        updated = Goal(uid="goal_1", user_uid=USER, title="g", status=EntityStatus.COMPLETED)
        backend, recorder = guarded_backend(current, updated)
        return GoalsCoreService(backend=backend), backend, recorder

    async def test_completing_stamps_achieved_date(self):
        service, _backend, recorder = self._service(EntityStatus.ACTIVE)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="completed"))
        assert result.is_ok
        assert recorder.last_guard.patch_if_prior_not_in == (
            frozenset({"completed"}),
            {"achieved_date": date.today()},
        )
        assert recorder.merged_patch()["achieved_date"] == date.today()

    async def test_reposting_completed_does_not_restamp(self):
        # Achievement immutability dropped (ruled 2026-08-22): completed goals
        # are editable like completed tasks, and the transition gate carries the
        # no-re-dating guarantee instead of the old blanket refusal.
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="completed"))
        assert result.is_ok
        assert "achieved_date" not in recorder.merged_patch()

    async def test_reopen_clears_the_stamp(self):
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="active"))
        assert result.is_ok
        assert recorder.merged_patch()["achieved_date"] is None

    async def test_reopen_resets_progress_percentage(self):
        # Without the reset a reopened goal stays a "100% complete" ACTIVE goal —
        # misread by progress consumers, and instantly re-achieved by the next
        # contribution increment. The reset rides the SAME prior-conditional patch
        # as the stamp clear, so an open goal is never zeroed by it.
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="active"))
        assert result.is_ok
        assert recorder.last_guard.patch_if_prior_in == (
            frozenset({"completed"}),
            {"achieved_date": None, "progress_percentage": 0.0},
        )
        assert recorder.merged_patch()["progress_percentage"] == 0.0

    async def test_an_open_goal_is_not_zeroed_by_the_reopen_reset(self):
        """The reset is conditional, not unconditional: a lateral move between two
        open statuses must leave progress alone. Only the write knows the prior, so
        this is a property of the condition, not of the caller."""
        service, _backend, recorder = self._service(EntityStatus.PAUSED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="active"))
        assert result.is_ok
        assert "progress_percentage" not in recorder.merged_patch()

    async def test_reopen_caller_progress_keeps_authority(self):
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        intent = GoalUpdateIntent(status="active", progress_percentage=42.0)
        result = await service.update_goal("goal_1", intent)
        assert result.is_ok
        assert recorder.merged_patch()["progress_percentage"] == 42.0

    async def test_a_reopen_carrying_its_own_stamp_still_resets_progress(self):
        """The trap in the migration. An intent that supplies ``achieved_date`` keeps
        authority over the STAMP, which makes ``status_transition_guard`` return a guard
        with NO patches at all — so a reset that merely EXTENDED the existing reopen
        patch would silently vanish for exactly these intents. The authority rule is
        about the stamp field; it says nothing about progress."""
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        intent = GoalUpdateIntent(status="active", achieved_date=date(2026, 1, 1))
        result = await service.update_goal("goal_1", intent)
        assert result.is_ok
        assert recorder.last_guard.patch_if_prior_in == (
            frozenset({"completed"}),
            {"progress_percentage": 0.0},
        )
        merged = recorder.merged_patch()
        assert merged["progress_percentage"] == 0.0
        assert merged["achieved_date"] == date(2026, 1, 1), "the caller's stamp kept authority"

    async def test_activate_goal_reopens_a_completed_goal(self):
        # The live reopen door: POST /api/goals/{uid}/status → set_status →
        # activate_goal.
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.activate_goal("goal_1")
        assert result.is_ok
        merged = recorder.merged_patch()
        assert merged["status"] == EntityStatus.ACTIVE.value
        assert merged["achieved_date"] is None
        assert merged["progress_percentage"] == 0.0

    async def test_archive_goal_archives_a_completed_goal(self):
        # A terminal target is not a reopen: the historical 100% progress
        # stays (only the stamp obeys the non-null-exactly-when-completed
        # invariant).
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.archive_goal("goal_1")
        assert result.is_ok
        merged = recorder.merged_patch()
        assert merged["status"] == EntityStatus.ARCHIVED.value
        assert "progress_percentage" not in merged

    async def test_cancel_transition_on_a_completed_goal_reaches_the_write(self):
        # The facade's cancel_goal delegates here after its active-tasks guard
        # (which is status-agnostic).
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="cancelled"))
        assert result.is_ok
        merged = recorder.merged_patch()
        assert merged["status"] == EntityStatus.CANCELLED.value
        assert merged["achieved_date"] is None

    async def test_complete_goal_transition_stamps_today(self):
        # complete_goal's default path carries no achieved_date — the stamp
        # comes from the transition condition at the chokepoint.
        service, _backend, recorder = self._service(EntityStatus.ACTIVE)
        result = await service.complete_goal("goal_1")
        assert result.is_ok
        assert recorder.merged_patch()["achieved_date"] == date.today()

    async def test_complete_goal_on_an_already_completed_goal_does_not_redate(self):
        # set_status("completed") on an already-completed goal dispatches here;
        # with the immutability rule gone, a re-posted complete must keep the
        # original achieved_date.
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.complete_goal("goal_1")
        assert result.is_ok
        assert "achieved_date" not in recorder.merged_patch()

    async def test_pause_goal_single_write_carries_status_and_metadata(self):
        # Pause metadata rides the status write, so one Result answers for both
        # (no discarded second write).
        service, backend, recorder = self._service(EntityStatus.ACTIVE)
        result = await service.pause_goal("goal_1", reason="resting")
        assert result.is_ok
        assert backend.update_with_status_guard.await_count == 1
        merged = recorder.merged_patch()
        assert merged["status"] == EntityStatus.PAUSED.value
        assert merged["metadata"]["pause_reason"] == "resting"

    def _flaky_pre_read_service(
        self,
    ) -> tuple[GoalsCoreService, Mock, StatusGuardedWriteRecorder[Goal]]:
        # Pre-read fails transiently, any later read would succeed — the
        # scenario where a swallowed pre-read error becomes a silent
        # metadata-less "success".
        from core.services.goals.goals_core_service import GoalsCoreService
        from core.utils.result_simplified import Errors

        current = Goal(uid="goal_1", user_uid=USER, title="g", status=EntityStatus.ACTIVE)
        backend, recorder = guarded_backend(current, current)
        backend.get = AsyncMock(
            side_effect=[
                Result.fail(Errors.database("get", "transient read failure")),
                Result.ok(current),
            ]
        )
        return GoalsCoreService(backend=backend), backend, recorder

    async def test_pause_goal_failed_pre_read_fails_the_pause(self):
        service, backend, _recorder = self._flaky_pre_read_service()
        result = await service.pause_goal("goal_1", reason="resting")
        assert result.is_error
        backend.update_with_status_guard.assert_not_awaited()

    async def test_archive_goal_failed_pre_read_fails_the_archive(self):
        service, backend, _recorder = self._flaky_pre_read_service()
        result = await service.archive_goal("goal_1")
        assert result.is_error
        backend.update_with_status_guard.assert_not_awaited()

    async def test_complete_goal_failed_notes_pre_read_fails_the_complete(self):
        service, backend, _recorder = self._flaky_pre_read_service()
        result = await service.complete_goal("goal_1", completion_notes="done")
        assert result.is_error
        backend.update_with_status_guard.assert_not_awaited()

    async def test_explicit_achieved_date_keeps_authority(self):
        # complete_goal's path: the intent already carries achieved_date.
        service, _backend, recorder = self._service(EntityStatus.ACTIVE)
        intent = GoalUpdateIntent(status="completed", achieved_date=date(2026, 8, 1))
        result = await service.update_goal("goal_1", intent)
        assert result.is_ok
        assert recorder.last_guard.has_patches() is False
        assert recorder.merged_patch()["achieved_date"] == date(2026, 8, 1)

    async def test_a_status_write_no_longer_pre_reads_at_all(self):
        """The read whose failure used to be able to re-date a stamp is GONE for a
        status-only update: the prior rides back on the write."""
        service, backend, _recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_goal("goal_1", GoalUpdateIntent(status="completed"))
        assert result.is_ok
        backend.get.assert_not_awaited()

    async def test_the_date_rule_still_fires_and_still_refuses(self):
        """``_validate_update`` is now called explicitly. The facade routes the generic
        CRUD here, so the inherited hook that used to run it is unreachable — dropping
        the explicit call would kill this rule silently."""
        service, backend, _recorder = self._service(
            EntityStatus.ACTIVE, start_date=date(2026, 6, 1)
        )
        result = await service.update_goal("goal_1", GoalUpdateIntent(target_date=date(2026, 5, 1)))
        assert result.is_error
        assert "after start date" in result.expect_error().message
        backend.update_with_status_guard.assert_not_awaited()

    async def test_the_date_rule_reads_the_goal_it_is_gated_on(self):
        """The rule falls back to the STORED dates when the update supplies only one,
        so the read is gated on the date fields — not, as it once was, on ``status``."""
        service, backend, _recorder = self._service(
            EntityStatus.ACTIVE, start_date=date(2026, 1, 1)
        )
        result = await service.update_goal("goal_1", GoalUpdateIntent(target_date=date(2026, 9, 1)))
        assert result.is_ok
        backend.get.assert_awaited_once()

    async def test_a_failed_date_read_still_fails_the_update(self):
        """A transient failure on the advisory read must not be read as "no rule
        applies"."""
        from core.utils.result_simplified import Errors

        service, backend, _recorder = self._service(EntityStatus.ACTIVE)
        backend.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "transient read failure"))
        )
        result = await service.update_goal("goal_1", GoalUpdateIntent(target_date=date(2026, 9, 1)))
        assert result.is_error
        backend.update_with_status_guard.assert_not_awaited()

    @pytest.mark.parametrize(
        ("write_prior", "expect_achieved"),
        [(EntityStatus.ACTIVE, True), (EntityStatus.COMPLETED, False)],
    )
    async def test_goal_achieved_follows_the_write_not_a_read(
        self, write_prior: EntityStatus, expect_achieved: bool
    ) -> None:
        """The verdict is sourced from the status the WRITE captured, in both
        directions. A fake driven by ``backend.get`` could only ever agree with the
        read — which is precisely the coupling the primitive removed."""
        from core.services.goals.goals_core_service import GoalsCoreService

        bus = _CapturingBus()
        current = Goal(uid="goal_1", user_uid=USER, title="g", status=write_prior)
        updated = Goal(uid="goal_1", user_uid=USER, title="g", status=EntityStatus.COMPLETED)
        backend, _recorder = guarded_backend(current, updated)
        service = GoalsCoreService(backend=backend, event_bus=bus)

        result = await service.update_goal("goal_1", GoalUpdateIntent(status="completed"))
        assert result.is_ok
        assert bool(bus.of(GoalAchieved)) is expect_achieved


@pytest.mark.asyncio
class TestHabitsChokepoint:
    def _service(
        self, current_status: EntityStatus, **current_fields: Any
    ) -> tuple[HabitsCoreService, Mock, StatusGuardedWriteRecorder[Habit]]:
        from core.services.habits.habits_core_service import HabitsCoreService

        current = Habit(
            uid="habit_1", user_uid=USER, title="h", status=current_status, **current_fields
        )
        updated = Habit(uid="habit_1", user_uid=USER, title="h", status=EntityStatus.COMPLETED)
        backend, recorder = guarded_backend(current, updated)
        return HabitsCoreService(backend=backend), backend, recorder

    async def test_completing_stamps_completed_at(self):
        service, _backend, recorder = self._service(EntityStatus.ACTIVE)
        result = await service.update_habit("habit_1", HabitUpdateIntent(status="completed"))
        assert result.is_ok
        statuses, patch = recorder.last_guard.patch_if_prior_not_in
        assert statuses == frozenset({"completed"})
        assert isinstance(patch["completed_at"], datetime)
        assert isinstance(recorder.merged_patch()["completed_at"], datetime)

    async def test_reposting_completed_does_not_restamp(self):
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_habit("habit_1", HabitUpdateIntent(status="completed"))
        assert result.is_ok
        assert "completed_at" not in recorder.merged_patch()

    async def test_reopen_clears_the_stamp(self):
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_habit("habit_1", HabitUpdateIntent(status="active"))
        assert result.is_ok
        assert recorder.merged_patch()["completed_at"] is None

    async def test_the_streak_rule_still_fires_and_still_refuses(self):
        """Habits was already Shape A — its explicit ``_validate_habit_update`` call
        survives the write swap, and so does the transient ``force_archive`` bypass."""
        service, backend, _recorder = self._service(EntityStatus.ACTIVE, current_streak=9)
        result = await service.update_habit("habit_1", HabitUpdateIntent(status="archived"))
        assert result.is_error
        assert "9-day streak" in result.expect_error().message
        backend.update_with_status_guard.assert_not_awaited()

    async def test_force_archive_still_bypasses_the_streak_rule(self):
        service, _backend, recorder = self._service(EntityStatus.ACTIVE, current_streak=9)
        result = await service.update_habit(
            "habit_1", HabitUpdateIntent(status="archived"), force_archive=True
        )
        assert result.is_ok
        assert recorder.last_updates["status"] == EntityStatus.ARCHIVED.value
        assert "force_archive" not in recorder.last_updates, (
            "the transient directive must never reach the write"
        )


@pytest.mark.asyncio
class TestEventsChokepoint:
    def _service(
        self, current_status: EntityStatus, event_date: date | None = None
    ) -> tuple[EventsCoreService, Mock, StatusGuardedWriteRecorder[Event]]:
        from core.services.events.events_core_service import EventsCoreService

        # Today's event by default: past-event immutability must not gate the transition.
        current = Event(
            uid="event_1",
            user_uid=USER,
            title="e",
            status=current_status,
            event_date=event_date or date.today(),
        )
        updated = Event(
            uid="event_1",
            user_uid=USER,
            title="e",
            status=EntityStatus.COMPLETED,
            event_date=event_date or date.today(),
        )
        backend, recorder = guarded_backend(current, updated)
        return EventsCoreService(backend=backend), backend, recorder

    async def test_completing_stamps_completed_at(self):
        service, _backend, recorder = self._service(EntityStatus.ACTIVE)
        result = await service.update_event("event_1", EventUpdateIntent(status="completed"))
        assert result.is_ok
        statuses, patch = recorder.last_guard.patch_if_prior_not_in
        assert statuses == frozenset({"completed"})
        assert isinstance(patch["completed_at"], datetime)
        assert isinstance(recorder.merged_patch()["completed_at"], datetime)

    async def test_reposting_completed_does_not_restamp(self):
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_event("event_1", EventUpdateIntent(status="completed"))
        assert result.is_ok
        assert "completed_at" not in recorder.merged_patch()

    async def test_reopen_clears_the_stamp(self):
        service, _backend, recorder = self._service(EntityStatus.COMPLETED)
        result = await service.update_event("event_1", EventUpdateIntent(status="active"))
        assert result.is_ok
        assert recorder.merged_patch()["completed_at"] is None

    async def test_past_event_immutability_still_fires_and_still_refuses(self):
        """Events' rule reads ``current.event_date`` and applies to EVERY field of
        EVERY update, which is why this chokepoint's advisory read is unconditional.
        Drop the explicit ``_validate_update`` call and the rule dies silently."""
        service, backend, _recorder = self._service(
            EntityStatus.ACTIVE, event_date=date.today() - timedelta(days=3)
        )
        result = await service.update_event("event_1", EventUpdateIntent(title="rewritten"))
        assert result.is_error
        assert "Cannot modify past events" in result.expect_error().message
        backend.update_with_status_guard.assert_not_awaited()

    async def test_the_retrospective_exception_still_reaches_the_write(self):
        """The rule's escape hatch: notes / tags / quality_score may still be added to a
        past event. ``tags`` is the one of the three ``EventUpdateIntent`` can carry —
        the other two, and the duration rule's ``duration_minutes``, are fields the intent
        has no member for, so this door cannot reach them (the same intent-vs-validator
        drift already registered for Principles; out of this PR's scope)."""
        service, _backend, recorder = self._service(
            EntityStatus.ACTIVE, event_date=date.today() - timedelta(days=3)
        )
        result = await service.update_event("event_1", EventUpdateIntent(tags=["afterthought"]))
        assert result.is_ok
        assert recorder.last_updates["tags"] == ["afterthought"]

    async def test_a_non_status_update_still_reads_for_the_rule(self):
        """Unlike Tasks and Goals, Events cannot narrow its read: a title-only update
        is exactly what past-event immutability exists to refuse."""
        service, backend, _recorder = self._service(EntityStatus.ACTIVE)
        result = await service.update_event("event_1", EventUpdateIntent(title="renamed"))
        assert result.is_ok
        backend.get.assert_awaited_once()

    @pytest.mark.parametrize(
        ("write_prior", "expect_completed_event"),
        [(EntityStatus.ACTIVE, True), (EntityStatus.COMPLETED, False)],
    )
    async def test_the_completion_event_follows_the_write_not_the_read(
        self, write_prior: EntityStatus, expect_completed_event: bool
    ) -> None:
        """The advisory read says ACTIVE either way; the WRITE's prior is what decides.
        Sourcing the verdict from the read would announce a completion another writer
        already made."""
        from core.services.events.events_core_service import EventsCoreService

        bus = _CapturingBus()
        read_shape = Event(
            uid="event_1",
            user_uid=USER,
            title="e",
            status=EntityStatus.ACTIVE,
            event_date=date.today(),
        )
        write_prior_shape = Event(
            uid="event_1", user_uid=USER, title="e", status=write_prior, event_date=date.today()
        )
        updated = Event(
            uid="event_1",
            user_uid=USER,
            title="e",
            status=EntityStatus.COMPLETED,
            event_date=date.today(),
        )
        backend, _recorder = guarded_backend(write_prior_shape, updated)
        backend.get = AsyncMock(return_value=Result.ok(read_shape))
        service = EventsCoreService(backend=backend, event_bus=bus)

        result = await service.update_event("event_1", EventUpdateIntent(status="completed"))
        assert result.is_ok
        assert bool(bus.of(CalendarEventCompleted)) is expect_completed_event


@pytest.mark.asyncio
class TestChoicesChokepoint:
    def _service(
        self, current_status: EntityStatus
    ) -> tuple[ChoicesCoreService, Mock, StatusGuardedWriteRecorder[Choice]]:
        from core.services.choices.choices_core_service import ChoicesCoreService

        # DRAFT current: decision immutability blocks critical-field changes on
        # ACTIVE/COMPLETED choices, so the completable state is DRAFT.
        current = Choice(uid="choice_1", user_uid=USER, title="c", status=current_status)
        updated = Choice(uid="choice_1", user_uid=USER, title="c", status=EntityStatus.COMPLETED)
        backend, recorder = guarded_backend(current, updated)
        return ChoicesCoreService(backend=backend), backend, recorder

    async def test_completing_stamps_completed_at(self):
        service, _backend, recorder = self._service(EntityStatus.DRAFT)
        result = await service.update_choice("choice_1", ChoiceUpdateIntent(status="completed"))
        assert result.is_ok
        statuses, patch = recorder.last_guard.patch_if_prior_not_in
        assert statuses == frozenset({"completed"})
        assert isinstance(patch["completed_at"], datetime)
        assert isinstance(recorder.merged_patch()["completed_at"], datetime)

    async def test_illegal_status_is_refused_before_the_write(self):
        # PAUSED is canonical but outside Choice's lifecycle.
        service, backend, _recorder = self._service(EntityStatus.DRAFT)
        result = await service.update_choice("choice_1", ChoiceUpdateIntent(status="paused"))
        assert result.is_error
        backend.update_with_status_guard.assert_not_awaited()

    async def test_decision_immutability_still_fires_and_still_refuses(self):
        """The pre-read half of the rule: dropping the explicit ``_validate_update``
        call would kill it silently, because the facade routes the generic CRUD here."""
        service, backend, _recorder = self._service(EntityStatus.ACTIVE)
        result = await service.update_choice("choice_1", ChoiceUpdateIntent(status="completed"))
        assert result.is_error
        assert "Decisions are historical records" in result.expect_error().message
        backend.update_with_status_guard.assert_not_awaited()

    async def test_a_non_critical_edit_of_a_decided_choice_still_writes(self):
        service, _backend, recorder = self._service(EntityStatus.ACTIVE)
        result = await service.update_choice(
            "choice_1", ChoiceUpdateIntent(description="hindsight")
        )
        assert result.is_ok
        assert recorder.last_guard.refuse_if_prior_in == frozenset(), (
            "an edit that touches no decision field must not be gated on the prior"
        )
        assert recorder.last_updates["description"] == "hindsight"

    async def test_the_write_refuses_a_choice_decided_after_the_read(self):
        """The race the guard closes, and the reason the rule is asked twice.
        ``make_decision`` moves a DRAFT choice to ACTIVE with a raw write that never
        passes through this chokepoint — so the pre-read can say DRAFT while the write
        finds a decided choice. The refusal comes from the LOCKED prior."""
        service, backend, recorder = self._service(EntityStatus.ACTIVE)
        backend.get = AsyncMock(
            return_value=Result.ok(
                Choice(uid="choice_1", user_uid=USER, title="c", status=EntityStatus.DRAFT)
            )
        )
        result = await service.update_choice("choice_1", ChoiceUpdateIntent(status="completed"))
        assert result.is_error
        assert "Decisions are historical records" in result.expect_error().message
        assert recorder.last_guard.refuse_if_prior_in == frozenset({"active", "completed"})


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

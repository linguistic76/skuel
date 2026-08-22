"""Completion stamping at the six Activity update chokepoints (PR-2 of the arc).

Three layers, matching how the stamp actually reaches the graph:

1. **The helper** (``completion_transition_patch`` / ``is_completion_transition``)
   — transition gating, R1 reopen-clear, explicit-field authority, and the
   status-target legality check that turns ``EntityType.valid_statuses()`` from
   documentation into enforcement.
2. **The six chokepoints** — wiring tests assert the CALLER: each real
   ``update_<domain>`` core method is driven with a typed intent against a
   mocked backend, and the assertion is on what ``backend.update`` received.
   Posting ``status=completed`` lands a stamp; re-posting doesn't re-date;
   reopening clears; Principle's illegal ``completed`` is refused at the seam.
   (Route → facade-intent wiring is pinned separately in
   ``tests/unit/adapters/test_*_api_routes.py``.)
3. **The bypass doors fixed in this pass** — ``complete_tasks_bulk`` stamps in
   place; the DSL ``[x]`` create door parses the obsidian-tasks ``✅ date`` into
   ``completion_date`` (falling back to today via the create-request default).
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
from core.services.completion_stamp import completion_transition_patch, is_completion_transition
from core.utils.result_simplified import Result

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
    def _service(self, current_status: EntityStatus):
        from core.services.tasks.tasks_core_service import TasksCoreService

        current = Task(uid="task_1", user_uid=USER, title="t", status=current_status)
        updated = Task(uid="task_1", user_uid=USER, title="t", status=EntityStatus.COMPLETED)
        backend = _mock_backend(current, updated)
        return TasksCoreService(backend=backend), backend

    async def test_completing_stamps_completion_date(self):
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))
        assert result.is_ok
        assert _written_changes(backend)["completion_date"] == date.today()

    async def test_reposting_completed_does_not_restamp(self):
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))
        assert result.is_ok
        assert "completion_date" not in _written_changes(backend)

    async def test_reopen_clears_the_stamp(self):
        service, backend = self._service(EntityStatus.COMPLETED)
        result = await service.update_task("task_1", TaskUpdateIntent(status="active"))
        assert result.is_ok
        assert _written_changes(backend)["completion_date"] is None

    async def test_illegal_status_is_refused_before_the_write(self):
        service, backend = self._service(EntityStatus.ACTIVE)
        result = await service.update_task("task_1", TaskUpdateIntent(status="archived"))
        assert result.is_error
        backend.update.assert_not_awaited()

    async def test_failed_old_status_read_fails_the_update(self):
        # A transient read failure must not be read as "not completed" — that
        # plus a completed re-post would re-date the original stamp (Codex P2).
        from core.utils.result_simplified import Errors

        service, backend = self._service(EntityStatus.COMPLETED)
        backend.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "transient read failure"))
        )
        result = await service.update_task("task_1", TaskUpdateIntent(status="completed"))
        assert result.is_error
        backend.update.assert_not_awaited()


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

    async def test_updates_on_an_achieved_goal_are_refused_before_the_write(self):
        # Goals' pre-existing achievement-immutability rule (`_validate_update`)
        # refuses ANY update on a COMPLETED goal, so both the re-post and the
        # reopen die before the write: no re-dating, and no R1 clear either —
        # reopening an achieved goal is not a legal Goal transition.
        service, backend = self._service(EntityStatus.COMPLETED)
        for target in ("completed", "active"):
            result = await service.update_goal("goal_1", GoalUpdateIntent(status=target))
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
        # #1123: unconditional stamping is the re-dating bug in miniature).
        from core.services.tasks.tasks_core_service import TasksCoreService

        active = Task(uid="task_active", user_uid=USER, title="t", status=EntityStatus.ACTIVE)
        done = Task(
            uid="task_done",
            user_uid=USER,
            title="t",
            status=EntityStatus.COMPLETED,
            completion_date=date(2026, 8, 1),
        )

        async def get_by_uid(uid):
            return Result.ok(done if uid == "task_done" else active)

        backend = Mock()
        backend.get = AsyncMock(side_effect=get_by_uid)
        backend.update = AsyncMock(return_value=Result.ok(active))
        service = TasksCoreService(backend=backend)

        result = await service.complete_tasks_bulk(["task_active", "task_done"], USER)

        assert result.is_ok
        assert result.value == 2
        written = {call.args[0]: call.args[1] for call in backend.update.await_args_list}
        assert written["task_active"]["status"] == EntityStatus.COMPLETED.value
        assert written["task_active"]["completion_date"] == date.today()
        assert "completion_date" not in written["task_done"], (
            "bulk-completing an already-completed task re-dated its completion"
        )

    async def test_bulk_complete_skips_rows_whose_state_cannot_be_read(self):
        # A failed per-row read must not pass as "not completed" — the row is
        # skipped (not flipped, not counted) rather than risk re-dating.
        from core.services.tasks.tasks_core_service import TasksCoreService
        from core.utils.result_simplified import Errors

        backend = Mock()
        backend.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "transient read failure"))
        )
        backend.update = AsyncMock()
        service = TasksCoreService(backend=backend)

        result = await service.complete_tasks_bulk(["task_1"], USER)

        assert result.is_ok
        assert result.value == 0
        backend.update.assert_not_awaited()


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

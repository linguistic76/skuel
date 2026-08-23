"""``TaskCompleted.is_repeat`` — the subscriber side of the idempotency contract.

The cascade genuinely re-runs when an already-completed task is completed again
(both explicit-complete doors sit behind an ownership check with no
already-completed guard, and the re-run is deliberately preserved as a repair
path). ``is_repeat`` is the single seam that makes that safe:

    Handlers that **recompute** state ignore ``is_repeat`` and do their work
    every time. Handlers that **count** or **append** skip when it is true.

These tests pin both halves in one place, because the contract is one thing
split across five services:

  Counting / appending — must no-op on a repeat
    1. TaskEventHandlerService   duration-calibration EMA + task_completion_count
    2. TaskEventHandlerService   overdue PersistedInsight append
    3. MetricsEventHandler       Prometheus entities_completed{task} (monotonic —
                                 the one that cannot be fixed anywhere else)

  Recomputing — must keep running on a repeat, and land on the same state
    4. GoalsProgressService      recomputes progress from count_linked_tasks
    5. PsEngagementService       auto-complete filtered on state='engaged'

  Both at once — the count derives, the stamps accumulate
    6. CrossDomainAnalyticsService  ProductivityAnalytics.tasks_completed is
                                 counted from the graph on every complete
                                 (PR-6 moved it off the increment), but
                                 first/last_completion_at are gated: a repeat
                                 carries a fresh occurred_at with nothing
                                 transitioned

  Both at once — the reason the contract names appending separately
    7. TaskEventHandlerService   principle alignment: the graph read recomputes
                                 and runs every time, the PersistedInsight
                                 append is gated

The publisher half (``is_repeat`` is the inverse of the completion-stamp gate)
lives in ``tests/unit/test_tasks_progress_service.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.events.task_events import TaskCompleted, TaskReopened, TasksBulkCompleted
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.insight.persisted_insight import InsightType
from core.models.task.task import Task
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
from core.services.goals.goals_progress_service import GoalsProgressService
from core.services.ps_engagement._auto_completion_handler import _AutoCompletionHandler
from core.services.ps_engagement.ps_engagement_service import PsEngagementService
from core.services.tasks.task_event_handler_service import TaskEventHandlerService
from core.utils.result_simplified import Result

_USER = "user_repeat"
_TASK = "task_repeat_abc"


def _event(*, is_repeat: bool, was_overdue: bool = False) -> TaskCompleted:
    return TaskCompleted(
        task_uid=_TASK,
        user_uid=_USER,
        was_overdue=was_overdue,
        is_repeat=is_repeat,
        occurred_at=datetime(2026, 8, 22, 12, 0),
    )


# ---------------------------------------------------------------------------
# 1 + 2. TaskEventHandlerService — counting halves skip, recompute halves stay
# ---------------------------------------------------------------------------


def _timed_task() -> Mock:
    task = Mock(spec=Task)
    task.uid = _TASK
    task.title = "Timed Task"
    task.duration_minutes = 60
    task.actual_minutes = 90
    task.priority = "medium"
    return task


def _event_handler() -> tuple[TaskEventHandlerService, Mock, AsyncMock, AsyncMock, AsyncMock]:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(_timed_task()))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.get_user_learning_state = AsyncMock(return_value=Result.ok({}))
    backend.update_user_learning_state = AsyncMock(return_value=Result.ok({}))

    relationships = AsyncMock()
    relationships.get_related_uids = AsyncMock(return_value=Result.ok(["principle_test"]))

    insight_store = AsyncMock()
    insight_store.create_insight = AsyncMock(return_value=Result.ok(True))

    ku_generation = AsyncMock()
    ku_generation.extract_knowledge_from_completed_tasks = AsyncMock(return_value=Result.ok([]))

    service = TaskEventHandlerService(
        backend=backend,
        relationship_service=relationships,
        insight_store=insight_store,
        ku_generation_service=ku_generation,
    )
    return service, backend, relationships, insight_store, ku_generation


@pytest.mark.asyncio
async def test_duration_calibration_counts_a_first_complete() -> None:
    """Baseline: a non-repeat still folds the sample into the EMA."""
    service, backend, _, _, _ = _event_handler()

    await service.handle_task_completed(_event(is_repeat=False))

    backend.update_user_learning_state.assert_called_once()
    assert backend.update_user_learning_state.call_args[0][1]["task_completion_count"] == 1


@pytest.mark.asyncio
async def test_duration_calibration_skips_a_repeat() -> None:
    """A repeat must not fold the same sample in twice nor bump the counter."""
    service, backend, _, _, _ = _event_handler()

    await service.handle_task_completed(_event(is_repeat=True))

    backend.update_user_learning_state.assert_not_called()
    # ...and no predicted_duration_minutes write-back either.
    backend.update.assert_not_called()


def _insights_of(insight_store: AsyncMock, insight_type: InsightType) -> list[Any]:
    """The insights of one type handed to the store — the handler persists more
    than one kind per completion (overdue *and* principle alignment)."""
    return [
        call.args[0]
        for call in insight_store.create_insight.call_args_list
        if call.args[0].insight_type is insight_type
    ]


@pytest.mark.asyncio
async def test_overdue_insight_is_appended_on_a_first_complete() -> None:
    """Baseline: the overdue insight is persisted when the completion is new."""
    service, _, _, insight_store, _ = _event_handler()

    await service.handle_task_completed(_event(is_repeat=False, was_overdue=True))

    assert len(_insights_of(insight_store, InsightType.COMPLETION_PATTERN)) == 1


@pytest.mark.asyncio
async def test_overdue_insight_skips_a_repeat() -> None:
    """The insight UID embeds a per-second timestamp, so a repeat would duplicate it."""
    service, _, _, insight_store, _ = _event_handler()

    await service.handle_task_completed(_event(is_repeat=True, was_overdue=True))

    assert _insights_of(insight_store, InsightType.COMPLETION_PATTERN) == []


@pytest.mark.asyncio
async def test_recompute_shaped_handlers_still_run_on_a_repeat() -> None:
    """The alignment graph read and knowledge generation are the repair path.

    Neither reads ``is_repeat``: they recompute from the graph, so re-running
    them converges rather than accumulating. Only the append inside the
    alignment step is gated — see the pair of tests below.
    """
    service, _, relationships, _, ku_generation = _event_handler()

    await service.handle_task_completed(_event(is_repeat=True))

    relationships.get_related_uids.assert_awaited()
    ku_generation.extract_knowledge_from_completed_tasks.assert_awaited()


@pytest.mark.asyncio
async def test_alignment_insight_is_appended_on_a_first_complete() -> None:
    """Baseline: the alignment insight is persisted when the completion is new."""
    service, _, _, insight_store, _ = _event_handler()

    await service.handle_task_completed(_event(is_repeat=False))

    assert len(_insights_of(insight_store, InsightType.PRINCIPLE_ALIGNMENT)) == 1


@pytest.mark.asyncio
async def test_alignment_insight_skips_a_repeat_but_the_read_still_runs() -> None:
    """The half of step 3 that appends is gated; the half that recomputes is not.

    ``PersistedInsight.generate_uid`` embeds a per-second timestamp, so an
    ungated repeat lands a second row describing the same alignment — the same
    duplicate the overdue insight is gated against.
    """
    service, _, relationships, insight_store, _ = _event_handler()

    await service.handle_task_completed(_event(is_repeat=True))

    relationships.get_related_uids.assert_awaited()
    assert _insights_of(insight_store, InsightType.PRINCIPLE_ALIGNMENT) == []


# ---------------------------------------------------------------------------
# 3. MetricsEventHandler — the monotonic Prometheus counter
# ---------------------------------------------------------------------------


def _metrics_handler() -> tuple[Any, Mock]:
    from core.infrastructure.monitoring.metrics_event_handler import MetricsEventHandler

    counter = Mock()
    counter.labels = Mock(return_value=counter)
    counter.inc = Mock()

    metrics = Mock()
    metrics.domains.entities_created = counter
    metrics.domains.entities_completed = counter

    handler = MetricsEventHandler(event_bus=Mock(), prometheus_metrics=metrics)
    return handler, counter


def test_prometheus_counts_a_first_complete() -> None:
    handler, counter = _metrics_handler()

    handler._on_task_completed(_event(is_repeat=False))

    counter.inc.assert_called_once()


def test_prometheus_skips_a_repeat() -> None:
    """A monotonic counter has no un-increment — the source is the only fix."""
    handler, counter = _metrics_handler()

    handler._on_task_completed(_event(is_repeat=True))

    counter.inc.assert_not_called()


def test_bulk_completion_is_counted_per_row_not_per_batch() -> None:
    """PR-4 inverts what PR-2 pinned here.

    ``complete_tasks_bulk`` now fans out one ``TaskCompleted`` per transitioning
    row, so the metrics handler no longer subscribes to ``TasksBulkCompleted`` —
    counting both would double every bulk completion, and the batch count
    included rows that were already completed.
    """
    handler, _ = _metrics_handler()
    bus = handler.event_bus

    subscribed = {call.args[0] for call in bus.subscribe.call_args_list}
    assert TaskCompleted in subscribed
    assert TasksBulkCompleted not in subscribed


# ---------------------------------------------------------------------------
# 4. CrossDomainAnalyticsService — recomputes tasks_completed from the graph
# ---------------------------------------------------------------------------


def _analytics_service() -> tuple[CrossDomainAnalyticsService, Mock]:
    backend = Mock()
    backend.recompute_productivity_analytics = AsyncMock(return_value=Result.ok([]))
    backend.upsert_habit_analytics = AsyncMock(return_value=Result.ok([]))
    return CrossDomainAnalyticsService(backend=backend), backend


@pytest.mark.asyncio
async def test_productivity_analytics_recomputes_on_a_first_complete() -> None:
    service, backend = _analytics_service()

    result = await service.handle_task_completed(_event(is_repeat=False))

    assert result.is_ok
    backend.recompute_productivity_analytics.assert_awaited_once_with(
        user_uid=_USER, occurred_at="2026-08-22T12:00:00"
    )


@pytest.mark.asyncio
async def test_productivity_analytics_recomputes_on_a_repeat_too() -> None:
    """PR-6 inverts what PR-2 pinned here.

    The handler used to skip a repeat entirely because ``ON MATCH SET
    tasks_completed = tasks_completed + 1`` could not tell a re-post from a
    second task. It now counts the user's currently-COMPLETED tasks from the
    graph, which *can*, so the count is rebuilt on every complete and converges
    instead of inflating.
    """
    service, backend = _analytics_service()

    first = await service.handle_task_completed(_event(is_repeat=False))
    repeat = await service.handle_task_completed(_event(is_repeat=True))

    assert first.is_ok and repeat.is_ok
    assert backend.recompute_productivity_analytics.await_count == 2


@pytest.mark.asyncio
async def test_a_repeat_complete_records_no_completion_moment() -> None:
    """``is_repeat`` did not disappear from this handler — it changed job.

    It no longer decides whether to do the work; it decides whether a new
    *completion moment* occurred. The explicit-complete cascade re-runs on an
    already-completed task and publishes a **fresh** ``occurred_at`` with
    nothing transitioned, so stamping it would stretch the velocity window
    without raising the numerator — every repair click quietly lowering the
    reported velocity (Codex #1134 P2). Same invariant as the reopen path.
    """
    service, backend = _analytics_service()

    await service.handle_task_completed(_event(is_repeat=False))
    await service.handle_task_completed(_event(is_repeat=True))

    calls = backend.recompute_productivity_analytics.await_args_list
    assert calls[0].kwargs["occurred_at"] == "2026-08-22T12:00:00", (
        "a genuine completion must still advance last_completion_at"
    )
    assert calls[1].kwargs["occurred_at"] is None, "a repeat is not a completion moment"
    assert calls[1].kwargs["user_uid"] == _USER, "but the count is still recomputed for the user"


@pytest.mark.asyncio
async def test_a_reopen_recomputes_without_moving_the_completion_stamps() -> None:
    """``occurred_at=None`` is the whole signal: a reopen is not a completion, so
    the backend recomputes the count and leaves ``last_completion_at`` — the
    endpoint of the velocity denominator — exactly where it was."""
    service, backend = _analytics_service()

    result = await service.handle_task_reopened(TaskReopened(task_uid=_TASK, user_uid=_USER))

    assert result.is_ok
    backend.recompute_productivity_analytics.assert_awaited_once_with(
        user_uid=_USER, occurred_at=None
    )


@pytest.mark.asyncio
async def test_habit_counter_still_increments_through_the_shared_helper() -> None:
    """``_upsert_counter_analytics`` is deliberately untouched by PR-6 — habits
    and events have no "currently completed" set to count, and a habit completed
    fifty times genuinely has fifty completions."""
    service, backend = _analytics_service()

    habit_event = Mock()
    habit_event.user_uid = _USER
    habit_event.habit_uid = "habit_daily"
    habit_event.occurred_at = datetime(2026, 8, 22, 12, 0)

    result = await service.handle_habit_completed(habit_event)

    assert result.is_ok
    backend.upsert_habit_analytics.assert_awaited_once()
    backend.recompute_productivity_analytics.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. GoalsProgressService — recomputes, so it runs on a repeat
# ---------------------------------------------------------------------------


class _RecordingBus:
    def __init__(self, sink: list[object]) -> None:
        self._sink = sink

    async def publish_async(self, event: object) -> None:
        self._sink.append(event)


def _goals_service() -> tuple[GoalsProgressService, Mock]:
    goal = Goal(
        uid="goal_repeat",
        user_uid=_USER,
        title="Ship the thing",
        measurement_type=MeasurementType.TASK_BASED,
        target_value=5.0,
        current_value=0.0,
        progress_percentage=0.0,
    )
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(goal))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.find_linked_goals_for_task = AsyncMock(return_value=Result.ok(["goal_repeat"]))
    backend.count_linked_tasks = AsyncMock(
        return_value=Result.ok({"total_tasks": 5, "completed_tasks": 2})
    )
    service = GoalsProgressService(backend=backend, event_bus=_RecordingBus([]))
    return service, backend


@pytest.mark.asyncio
async def test_goal_progress_recomputes_on_a_repeat_and_lands_identically() -> None:
    """Progress is derived from ``count_linked_tasks``, never incremented, so
    running it again is the repair path and converges on the same numbers."""
    service, backend = _goals_service()

    await service.handle_task_completed(_event(is_repeat=False))
    assert backend.update.await_count == 1
    first_patch = dict(backend.update.await_args.args[1])

    await service.handle_task_completed(_event(is_repeat=True))
    assert backend.update.await_count == 2, "recompute handlers must run on a repeat"
    second_patch = dict(backend.update.await_args.args[1])

    assert second_patch["progress_percentage"] == first_patch["progress_percentage"] == 40.0
    assert second_patch["current_value"] == first_patch["current_value"] == 2.0
    assert second_patch["target_value"] == first_patch["target_value"] == 5.0


# ---------------------------------------------------------------------------
# 6. PsEngagementService — auto-complete filtered on state='engaged'
# ---------------------------------------------------------------------------


@dataclass
class _EngagementBackend:
    """Returns siblings until the engagement edge leaves ``engaged``."""

    rows: list[dict[str, Any]]
    calls: int = 0

    async def fetch_auto_complete_siblings(
        self, student_uid: str, instance_uid: str
    ) -> Result[list[dict[str, Any]]]:
        self.calls += 1
        return Result.ok(self.rows)


def _ps_engagement(backend: _EngagementBackend, complete: AsyncMock) -> PsEngagementService:
    svc = PsEngagementService.__new__(PsEngagementService)
    svc._backend = backend  # type: ignore[assignment]
    svc.logger = Mock()
    svc.complete_pathstep = complete  # type: ignore[method-assign]
    return svc


@pytest.mark.asyncio
async def test_ps_auto_complete_runs_on_a_repeat_and_is_a_no_op_second_time() -> None:
    """The handler never reads ``is_repeat`` — idempotency comes from the
    ``state='engaged'`` filter, which stops matching once the edge transitions."""
    all_terminal = [
        {
            "ps_uid": "ps_x",
            "siblings": [{"entity_type": "task", "status": "completed"}],
        }
    ]
    backend = _EngagementBackend(rows=all_terminal)
    complete = AsyncMock(return_value=Result.ok(None))
    service = _ps_engagement(backend, complete)
    handler = _AutoCompletionHandler(service)

    await handler.on_task_completed(_event(is_repeat=False))
    assert complete.await_count == 1

    # After the first auto-complete the engagement edge is no longer 'engaged',
    # so the sibling query matches nothing.
    backend.rows = []

    await handler.on_task_completed(_event(is_repeat=True))

    assert backend.calls == 2, "the auto-complete check must still run on a repeat"
    assert complete.await_count == 1, "but it must not complete the engagement twice"

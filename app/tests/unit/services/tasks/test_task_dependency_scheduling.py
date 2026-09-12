"""``TaskEventHandlerService.handle_dependent_scheduling`` — the one write a completion cascades into.

A ``TRIGGERS_ON_COMPLETION`` dependent is moved to ``scheduled`` when its upstream
task completes; a dependent that has already finished is left exactly as it is.
The subscriber is its own ``TaskCompleted`` handler with its own exception
boundary, so an optional intelligence step failing in ``handle_task_completed``
cannot leave a dependent unscheduled behind a completion that reported success.

Latent on the live graph today (0 TRIGGERS_ON_COMPLETION edges), so these tests
carry the whole proof.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.task_events import TaskCompleted
from core.models.enums import EntityStatus, EntityType, Priority
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.type_hints import Neo4jProperties
from core.models.update_contracts import StatusGuardedOutcome, StatusWriteGuard
from core.services.tasks.task_event_handler_service import TaskEventHandlerService
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.result_simplified import Errors, Result
from tests.helpers.status_guarded_backend import prior_status_of, resolve_merged_patch

_TASK_STATUSES = EntityType.TASK.valid_statuses()
#: Derived from the enum, never typed out: the subscriber decides the skip with
#: ``EntityStatus.terminal_values()``, and an inline ``== COMPLETED`` literal would
#: pass the completed case while failing cancelled and failed.
_TERMINAL_DEPENDENT_STATUSES = [s for s in EntityStatus if s in _TASK_STATUSES and s.is_terminal()]
_LIVE_DEPENDENT_STATUSES = [s for s in EntityStatus if s in _TASK_STATUSES and not s.is_terminal()]


def _task(uid: str, status: EntityStatus, **fields: Any) -> Task:
    """Build a Task the way a backend read does — status as the enum.

    ``**fields`` is forwarded verbatim to ``TaskDTO``, whose ~40 optional fields
    span dates, ints, strings and enums — genuinely heterogeneous, which is the
    one thing ``Any`` is for.
    """  # boundary: dto-kwargs
    return Task.from_dto(
        TaskDTO(
            uid=uid,
            user_uid="user_demo",
            title=f"Task {uid}",
            priority=Priority.MEDIUM.value,
            status=status,
            created_at=datetime.now(),
            **fields,
        )
    )


class _FakeTaskGraph:
    """A node store with Neo4j write semantics that hands back domain models.

    Three fidelity points a plain dict-returning mock does not carry, all
    load-bearing here:

    * ``UniversalNeo4jBackend.get`` returns a ``from_neo4j_node`` domain model, not
      a property dict, and ``update_with_status_guard`` returns one inside its
      outcome.
    * ``SET n += $updates`` REMOVES a property set to null and leaves untouched
      keys alone — the invariant under test is about a property surviving (or
      not surviving) a write. The payload is serialized on the way in, as the real
      method does, so a stamp lands as the ISO string every writer stores.
    * The terminal skip is the WRITE's refusal, so the store evaluates the guard
      the way the Cypher does and records only the writes that applied.
    """

    def __init__(self, *tasks: Task) -> None:
        self.nodes: dict[str, Neo4jProperties] = {t.uid: t.to_dto().to_dict() for t in tasks}
        #: The writes that actually mutated a node — a refused guard records nothing,
        #: because a refused write leaves the node byte-identical.
        self.writes: list[tuple[str, Neo4jProperties]] = []

    def snapshot(self, uid: str) -> Neo4jProperties:
        """The stored properties of one node, detached from the store."""
        return dict(self.nodes[uid])

    async def get(self, uid: str) -> Result[Task | None]:
        node = self.nodes.get(uid)
        return Result.ok(from_neo4j_node(dict(node), Task) if node is not None else None)

    async def update_with_status_guard(
        self, uid: str, updates: Neo4jProperties, guard: StatusWriteGuard
    ) -> Result[StatusGuardedOutcome[Task]]:
        node = self.nodes.get(uid)
        if node is None:
            return Result.fail(Errors.not_found("resource", f"Entity {uid} not found"))
        prior = prior_status_of(node)
        applied = prior not in guard.refuse_if_prior_in
        if applied:
            merged = to_neo4j_node(resolve_merged_patch(prior, updates, guard))
            self.writes.append((uid, dict(merged)))
            for key, value in merged.items():
                if value is None:
                    node.pop(key, None)
                else:
                    node[key] = value
        return Result.ok(
            StatusGuardedOutcome(
                applied=applied,
                prior_status=prior,
                entity=from_neo4j_node(dict(node), Task),
            )
        )


def _rig(dependent: Task) -> tuple[TaskEventHandlerService, Task, _FakeTaskGraph, Mock]:
    """An upstream task that TRIGGERS_ON_COMPLETION the given dependent, and the
    subscriber over a backend answering from the fake graph."""
    upstream = _task("task:upstream", EntityStatus.COMPLETED)
    graph = _FakeTaskGraph(upstream, dependent)
    backend = Mock()
    backend.get = AsyncMock(side_effect=graph.get)
    backend.update_with_status_guard = AsyncMock(side_effect=graph.update_with_status_guard)

    async def _related(
        uid: str, relationship: RelationshipName, direction: str = "outgoing"
    ) -> Result[list[str]]:
        if uid == upstream.uid and relationship == RelationshipName.TRIGGERS_ON_COMPLETION:
            return Result.ok([dependent.uid])
        return Result.ok([])

    backend.get_related_uids = AsyncMock(side_effect=_related)
    return TaskEventHandlerService(backend=backend), upstream, graph, backend


def _completed(upstream: Task) -> TaskCompleted:
    return TaskCompleted(task_uid=upstream.uid, user_uid="user_demo")


@pytest.mark.asyncio
async def test_a_completed_dependent_keeps_its_status_and_its_stamp() -> None:
    """A completed dependent keeps BOTH its status and its ``completion_date``.

    A blind ``status=scheduled`` would move a completed dependent out of COMPLETED
    while leaving the stamp behind — breaking the invariant that
    ``completion_date`` is non-null exactly when the task is completed.
    """
    dependent = _task("task:dependent", EntityStatus.COMPLETED, completion_date=date(2026, 8, 1))
    service, upstream, graph, _backend = _rig(dependent)
    before = graph.snapshot(dependent.uid)

    await service.handle_dependent_scheduling(_completed(upstream))

    assert graph.writes == [], "the dependent must not be written"
    assert graph.snapshot(dependent.uid) == before
    assert graph.nodes[dependent.uid]["completion_date"] == before["completion_date"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal",
    _TERMINAL_DEPENDENT_STATUSES,
    ids=[s.value for s in _TERMINAL_DEPENDENT_STATUSES],
)
async def test_every_terminal_dependent_is_skipped(terminal: EntityStatus) -> None:
    """The gate is the enum's terminal set, not a COMPLETED literal.

    Cancelled and failed dependents are equally not this cascade's to resurrect,
    and keying on the enum's own predicate means a new terminal status is honoured
    without editing the subscriber.
    """
    dependent = _task("task:dependent", terminal)
    service, upstream, graph, _backend = _rig(dependent)

    await service.handle_dependent_scheduling(_completed(upstream))

    assert graph.writes == []
    assert graph.nodes[dependent.uid]["status"] == terminal.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "live",
    _LIVE_DEPENDENT_STATUSES,
    ids=[s.value for s in _LIVE_DEPENDENT_STATUSES],
)
async def test_a_live_dependent_is_scheduled(live: EntityStatus) -> None:
    """The subscriber still does its job — nothing but a terminal state is skipped."""
    dependent = _task("task:dependent", live)
    service, upstream, graph, _backend = _rig(dependent)

    await service.handle_dependent_scheduling(_completed(upstream))

    assert graph.writes == [(dependent.uid, {"status": EntityStatus.SCHEDULED.value})]
    assert graph.nodes[dependent.uid]["status"] == EntityStatus.SCHEDULED.value


@pytest.mark.asyncio
async def test_the_write_is_asked_to_refuse_every_terminal_status() -> None:
    """The skip is a CONDITION the write evaluates, not a status read beforehand.

    A dependent completed concurrently is exactly what a read-then-write gate
    misses, so assert the guard itself: every terminal status of the enum, and no
    stamp patches (the only prior a reopen clear could apply to is COMPLETED, which
    this guard refuses outright).
    """
    dependent = _task("task:dependent", EntityStatus.ACTIVE)
    service, upstream, _graph, backend = _rig(dependent)

    await service.handle_dependent_scheduling(_completed(upstream))

    dependent_calls = [
        call
        for call in backend.update_with_status_guard.await_args_list
        if call.args[0] == dependent.uid
    ]
    assert len(dependent_calls) == 1
    guard = dependent_calls[0].args[2]
    assert guard.refuse_if_prior_in == EntityStatus.terminal_values()
    assert set(guard.refuse_if_prior_in) >= {s.value for s in _TERMINAL_DEPENDENT_STATUSES}
    assert guard.has_patches() is False


@pytest.mark.asyncio
async def test_a_dangling_dependent_edge_is_survived() -> None:
    """A TRIGGERS_ON_COMPLETION edge pointing at nothing fails that write, not the handler."""
    dependent = _task("task:dependent", EntityStatus.ACTIVE)
    service, upstream, graph, _backend = _rig(dependent)
    del graph.nodes[dependent.uid]

    await service.handle_dependent_scheduling(_completed(upstream))

    assert graph.writes == []


@pytest.mark.asyncio
async def test_a_failed_dependents_read_schedules_nothing_and_raises_nothing() -> None:
    dependent = _task("task:dependent", EntityStatus.ACTIVE)
    service, upstream, graph, backend = _rig(dependent)
    backend.get_related_uids = AsyncMock(
        return_value=Result.fail(Errors.database("get_related_uids", "boom"))
    )

    await service.handle_dependent_scheduling(_completed(upstream))

    assert graph.writes == []


@pytest.mark.asyncio
async def test_a_raising_backend_is_contained_by_the_subscriber_boundary() -> None:
    """Fire-and-forget: the boundary is the subscriber's own, so nothing escapes to
    the bus or to the completing request."""
    dependent = _task("task:dependent", EntityStatus.ACTIVE)
    service, upstream, _graph, backend = _rig(dependent)
    backend.update_with_status_guard = AsyncMock(side_effect=NEO4J_EXCEPTIONS[0]("boom"))

    await service.handle_dependent_scheduling(_completed(upstream))  # must not raise

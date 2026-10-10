"""Every link written or removed through ``UnifiedRelationshipService`` is announced.

The owner's cached context reads the links (``principle_supported_goals``,
``habits_by_goal``, ``life_path_goal_uids``, …), so each write and each removal
publishes one ``EntityLinksChanged`` per owner of the entity the link starts from —
the owner its admission read, or, for a removal, read before anything is deleted.
A refused link writes and announces nothing; a link from shared content (owned by
nobody) has no context to stale and announces nothing.

The subscription to context invalidation over a real graph:
``tests/integration/routes/test_link_door_context_invalidation.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from core.events import EntityLinksChanged
from core.events.base import BaseEvent
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import GOALS_CONFIG, KU_CONFIG
from core.services.mixins.link_edge_guard import HABIT_FAR_END, KNOWLEDGE_FAR_END
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Errors, Result
from tests.unit.services.test_link_far_end_admission import ALICE, WritingEndpoints

pytestmark = pytest.mark.asyncio


@dataclass
class _Bus:
    """The one bus call ``publish_event`` makes, recorded."""

    published: list[BaseEvent] = field(default_factory=list)

    async def publish_async(self, event: BaseEvent) -> None:
        self.published.append(event)


@dataclass
class _Backend(WritingEndpoints):
    """The endpoint reads and the batch write, plus the single-edge delete."""

    deleted: list[tuple[str, str]] = field(default_factory=list)

    async def delete_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        from_label: str | None = None,
        to_label: str | None = None,
    ) -> Result[bool]:
        self.deleted.append((from_uid, to_uid))
        return Result.ok(True)


def _goals(backend: _Backend, bus: _Bus) -> UnifiedRelationshipService:
    # boundary: the fake backend stands in for the goals backend's operations
    return UnifiedRelationshipService(backend=backend, config=GOALS_CONFIG, event_bus=bus)  # type: ignore[arg-type]


def _announced(bus: _Bus) -> list[tuple[str, str]]:
    assert all(isinstance(event, EntityLinksChanged) for event in bus.published)
    return [(event.user_uid, event.entity_uid) for event in bus.published]  # type: ignore[attr-defined]


async def test_a_link_written_is_announced_for_the_sources_owner() -> None:
    backend, bus = _Backend(), _Bus()

    linked = await _goals(backend, bus).create_relationship(
        "supporting_habits", "goal_alice", "habit_alice", far_end=HABIT_FAR_END
    )

    assert linked.is_ok, linked
    assert backend.written
    assert _announced(bus) == [(ALICE, "goal_alice")]


async def test_a_link_written_on_an_earlier_admission_is_announced_without_a_second_read() -> None:
    backend, bus = _Backend(), _Bus()
    service = _goals(backend, bus)
    admitted = await service.admit_far_ends("goal_alice", ["habit_alice"], HABIT_FAR_END)
    assert admitted.is_ok, admitted
    reads = len(backend.asked)

    linked = await service.create_relationship(
        "supporting_habits", "goal_alice", "habit_alice", far_end=admitted.value
    )

    assert linked.is_ok, linked
    assert len(backend.asked) == reads
    assert _announced(bus) == [(ALICE, "goal_alice")]


async def test_a_refused_link_writes_and_announces_nothing() -> None:
    backend, bus = _Backend(), _Bus()

    refused = await _goals(backend, bus).create_relationship(
        "supporting_habits", "goal_alice", "habit_bob", far_end=HABIT_FAR_END
    )

    assert refused.is_error
    assert backend.written == []
    assert bus.published == []


async def test_a_batch_is_announced_once() -> None:
    backend, bus = _Backend(), _Bus()

    created = await _goals(backend, bus).create_relationships_batch(
        "goal_alice",
        {"supporting_habits": ["habit_alice"], "knowledge": ["ku_shared"]},
        far_ends={"supporting_habits": HABIT_FAR_END, "knowledge": KNOWLEDGE_FAR_END},
    )

    assert created.is_ok, created
    assert _announced(bus) == [(ALICE, "goal_alice")]


async def test_a_link_removed_is_announced_for_the_sources_owner() -> None:
    backend, bus = _Backend(), _Bus()

    removed = await _goals(backend, bus).delete_relationship(
        "supporting_habits", "goal_alice", "habit_alice"
    )

    assert removed.is_ok, removed
    assert backend.deleted
    assert _announced(bus) == [(ALICE, "goal_alice")]


async def test_an_unreadable_owner_removes_nothing() -> None:
    backend, bus = _Backend(owners_error=True), _Bus()

    removed = await _goals(backend, bus).delete_relationship(
        "supporting_habits", "goal_alice", "habit_alice"
    )

    assert removed.is_error
    assert backend.deleted == []
    assert bus.published == []


async def test_a_link_from_shared_content_announces_nothing() -> None:
    backend, bus = _Backend(), _Bus()
    # boundary: the fake backend stands in for the Ku backend's operations
    service: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=backend,  # type: ignore[arg-type]
        config=KU_CONFIG,
        event_bus=bus,  # type: ignore[arg-type]
    )

    removed = await service.delete_relationship(
        KU_CONFIG.relationships[0].method_key, "ku_shared", "ku_draft"
    )

    assert removed.is_ok, removed
    assert bus.published == []


async def test_a_failed_removal_announces_nothing() -> None:
    @dataclass
    class _Failing(_Backend):
        async def delete_relationship(self, *args: object, **kwargs: object) -> Result[bool]:
            return Result.fail(Errors.database("delete_relationship", "unreachable"))

    bus = _Bus()

    removed = await _goals(_Failing(), bus).delete_relationship(
        "supporting_habits", "goal_alice", "habit_alice"
    )

    assert removed.is_error
    assert bus.published == []


async def test_a_door_that_writes_on_its_own_statement_announces_through_the_service() -> None:
    """The life-path link admits here and writes through its own backend statement."""
    backend, bus = _Backend(), _Bus()
    service = _goals(backend, bus)
    admitted = await service.admit_far_ends("goal_alice", ["habit_alice"], HABIT_FAR_END)
    assert admitted.is_ok, admitted

    await service.links_changed(admitted.value)

    assert _announced(bus) == [(ALICE, "goal_alice")]

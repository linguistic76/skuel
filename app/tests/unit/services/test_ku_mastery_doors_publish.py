"""Every Ku-mastery door publishes ``KnowledgeMastered`` for the write that created the edge.

Three doors master a Ku — report approval (``PsMasteryService.mark_mastered``), the
Ku page's "understood" (``KuService.mark_as_understood``) and the pathways progress
route (``UserProgressRecorderService.record_knowledge_mastery``). The progress chain
(path-step and path progress, the derived step mastery, the ZPD snapshot) hangs off
the event, so a door that wrote the edge silently would leave a step whose last Ku was
mastered through it unmastered. And only the transition is an event: the chain counts
per event (the velocity counter, ``paths_completed``), so a retry or a second "understood"
on a mastered Ku publishes nothing, and the event carries the score the graph stored.
The report-approval door is covered by ``test_ps_step_mastery_derived``; these pin the
other two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.events.learning_events import KnowledgeMastered
from core.models.type_hints import UserUID
from core.services.user.user_progress_recorder_service import UserProgressRecorderService
from core.utils.result_simplified import Errors, Result

USER = UserUID("user_1")


@dataclass
class _Bus:
    published: list[object] = field(default_factory=list)

    async def publish_async(self, event: object) -> None:
        self.published.append(event)


def _mastered(bus: _Bus) -> list[KnowledgeMastered]:
    return [e for e in bus.published if isinstance(e, KnowledgeMastered)]


# ---------------------------------------------------------------------------
# KuService.mark_as_understood
# ---------------------------------------------------------------------------


def _ku_service(write: Result, bus: _Bus):
    from core.services.ku_service import KuService

    with patch("core.services.curriculum_domain_config.create_curriculum_sub_services") as factory:
        factory.return_value = MagicMock()
        backend = MagicMock()
        backend.mark_mastered = AsyncMock(return_value=write)
        return KuService(backend=backend, graph_intel=MagicMock(), event_bus=bus)


@pytest.mark.asyncio
async def test_understood_publishes_the_transition_with_the_stored_score() -> None:
    bus = _Bus()
    service = _ku_service(Result.ok([{"mastery_score": 0.7, "was_mastered": False}]), bus)

    result = await service.mark_as_understood(USER, "ku.a")

    assert result.is_ok
    [event] = _mastered(bus)
    assert (event.ku_uid, event.user_uid, event.mastery_score) == ("ku.a", USER, 0.7)


@pytest.mark.asyncio
async def test_understood_of_a_ku_already_mastered_publishes_nothing() -> None:
    """A report mastered it at 0.95; "understood" keeps that score and is not an event."""
    bus = _Bus()
    service = _ku_service(Result.ok([{"mastery_score": 0.95, "was_mastered": True}]), bus)

    result = await service.mark_as_understood(USER, "ku.a")

    assert result.is_ok
    assert bus.published == []


@pytest.mark.asyncio
async def test_understood_of_a_missing_ku_publishes_nothing() -> None:
    bus = _Bus()
    service = _ku_service(Result.ok([]), bus)

    await service.mark_as_understood(USER, "ku.gone")

    assert bus.published == []


@pytest.mark.asyncio
async def test_understood_failed_write_publishes_nothing() -> None:
    bus = _Bus()
    service = _ku_service(Result.fail(Errors.database("mark_mastered", "down")), bus)

    result = await service.mark_as_understood(USER, "ku.a")

    assert result.is_error
    assert bus.published == []


# ---------------------------------------------------------------------------
# UserProgressRecorderService.record_knowledge_mastery
# ---------------------------------------------------------------------------


def _recorder(write: Result, bus: _Bus) -> UserProgressRecorderService:
    repo = MagicMock()
    repo.record_knowledge_mastery = AsyncMock(return_value=write)
    repo.get_learning_state = AsyncMock(return_value=Result.ok({}))
    repo.update_learning_state = AsyncMock(return_value=Result.ok(True))
    return UserProgressRecorderService(repo, event_bus=bus)


@pytest.mark.asyncio
async def test_recorded_mastery_publishes_the_transition_with_the_stored_score() -> None:
    bus = _Bus()
    service = _recorder(Result.ok({"mastery_score": 0.9, "was_mastered": False}), bus)

    result = await service.record_knowledge_mastery(USER, "ku.b", 0.9, update_progress=False)

    assert result.is_ok
    [event] = _mastered(bus)
    assert (event.ku_uid, event.user_uid, event.mastery_score) == ("ku.b", USER, 0.9)


@pytest.mark.asyncio
async def test_recorded_mastery_retry_publishes_nothing() -> None:
    bus = _Bus()
    service = _recorder(Result.ok({"mastery_score": 0.9, "was_mastered": True}), bus)

    result = await service.record_knowledge_mastery(USER, "ku.b", 0.9, update_progress=False)

    assert result.is_ok
    assert bus.published == []


@pytest.mark.asyncio
async def test_recorded_mastery_failed_write_publishes_nothing() -> None:
    bus = _Bus()
    service = _recorder(Result.fail(Errors.database("record_knowledge_mastery", "down")), bus)

    result = await service.record_knowledge_mastery(USER, "ku.b", 0.9, update_progress=False)

    assert result.is_error
    assert bus.published == []

"""``create_event_with_context`` credits only the knowledge its admission read admitted.

The request's ``practices_knowledge_uids`` become ``KnowledgePracticedInEvent``s; each
uid is admitted first (a published Ku or PathStep the three endpoint reads vouch for).
These pin the two shapes the integration test cannot: a repeated uid is one credit,
and an endpoint read that fails credits nothing — the event is still created.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.knowledge_substance_events import KnowledgePracticedInEvent
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest
from core.services.events._orchestration_mixin import _OrchestrationMixin
from core.utils.result_simplified import Errors, Result

USER = "user_1"
KU = "ku.a"
DRAFT = "ku.draft"
GONE = "ku.gone"
STEP = "ps.a"
TASK = "task_other"


class _Bus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish_async(self, event: object) -> None:
        self.published.append(event)


async def _echo(entity: Event) -> Result[Event]:
    return Result.ok(entity)


class _Host(_OrchestrationMixin):
    def __init__(self, *, reads_fail: bool = False) -> None:
        # The mock kept under its own name: the mixin types ``backend`` as the
        # protocol, which has no assert_* members.
        self.mock = MagicMock()
        self.backend = self.mock
        self.mock.create = AsyncMock(side_effect=_echo)
        if reads_fail:
            failed: Result[dict[str, list[str]]] = Result.fail(
                Errors.database("get_owner_uids_batch", "down")
            )
            self.mock.get_owner_uids_batch = AsyncMock(return_value=failed)
        else:
            self.mock.get_owner_uids_batch = AsyncMock(
                return_value=Result.ok({TASK: ["user_other"]})
            )
        self.mock.get_node_labels_batch = AsyncMock(
            return_value=Result.ok(
                {
                    KU: ["Entity", "Ku"],
                    DRAFT: ["Entity", "Ku"],
                    STEP: ["Entity", "PathStep"],
                    TASK: ["Entity", "Task"],
                }
            )
        )
        self.mock.get_published_uids_batch = AsyncMock(
            return_value=Result.ok(frozenset({KU, STEP, TASK}))
        )
        self.event_bus = _Bus()
        self.logger = MagicMock()


def _request(*uids: str) -> EventCreateRequest:
    return EventCreateRequest.model_validate(
        {
            "title": "Practice",
            "event_date": date(2026, 10, 10).isoformat(),
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "practices_knowledge_uids": list(uids),
        }
    )


def _credited(bus: _Bus) -> list[str]:
    return [e.knowledge_uid for e in bus.published if isinstance(e, KnowledgePracticedInEvent)]


@pytest.mark.asyncio
async def test_only_admitted_knowledge_is_credited_once_each() -> None:
    host = _Host()
    context = SimpleNamespace(user_uid=USER, active_habit_uids=set())

    result = await host.create_event_with_context(
        _request(KU, DRAFT, GONE, TASK, STEP, KU), context
    )

    assert result.is_ok, result
    assert _credited(host.event_bus) == [KU, STEP]
    host.mock.get_owner_uids_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failed_endpoint_read_credits_nothing_and_still_creates_the_event() -> None:
    host = _Host(reads_fail=True)
    context = SimpleNamespace(user_uid=USER, active_habit_uids=set())

    result = await host.create_event_with_context(_request(KU, STEP), context)

    assert result.is_ok, result
    assert _credited(host.event_bus) == []


@pytest.mark.asyncio
async def test_no_knowledge_reads_nothing() -> None:
    host = _Host()
    context = SimpleNamespace(user_uid=USER, active_habit_uids=set())

    result = await host.create_event_with_context(_request(), context)

    assert result.is_ok, result
    assert _credited(host.event_bus) == []
    host.mock.get_owner_uids_batch.assert_not_awaited()

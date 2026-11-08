"""A principle's appends are planned from the principle under its lock and write their field alone.

``PrinciplesCoreService.rewrite_principle`` hands the planner the locked principle and
writes what it answers through ``rewrite_under_lock`` with no status condition;
``create_principle_expression`` is its expression append. Held here against the
in-memory recorder (``tests/helpers/status_guarded_backend.py``); the lock itself, and
the races it closes, are held against Neo4j in
``tests/integration/test_principle_expression_door.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.events import PrincipleUpdated
from core.models.enums.entity_enums import EntityStatus
from core.models.principle.principle import Principle
from core.models.principle.principle_types import PrincipleExpression
from core.models.update_contracts import StatusWriteGuard
from core.services.principles.principles_core_service import PrinciplesCoreService
from core.services.principles_service import PrinciplesService
from core.utils.result_simplified import ErrorCategory, Errors, Result
from tests.helpers.seed_uids import seed_user_uid
from tests.helpers.status_guarded_backend import StatusGuardedWriteRecorder, guarded_backend

pytestmark = pytest.mark.asyncio

USER = seed_user_uid("principle-rewrite")
HOME = PrincipleExpression(context="Home", behavior="Rest")


def _principle(status: EntityStatus = EntityStatus.ACTIVE) -> Principle:
    return Principle(
        uid="principle_1", user_uid=USER, title="p", status=status, expressions=(HOME,)
    )


def _core(
    current: Principle,
) -> tuple[PrinciplesCoreService, StatusGuardedWriteRecorder[Principle], Mock]:
    backend, recorder = guarded_backend(current, current)
    event_bus = Mock()
    event_bus.publish_async = AsyncMock()
    return PrinciplesCoreService(backend=backend, event_bus=event_bus), recorder, event_bus


def _facade(core: PrinciplesCoreService) -> PrinciplesService:
    service = PrinciplesService(
        backend=Mock(), graph_intel=Mock(), cross_domain_query=AsyncMock(), event_bus=None
    )
    service.core = core
    return service


async def test_an_expression_append_writes_the_expressions_alone() -> None:
    core, recorder, _bus = _core(_principle(EntityStatus.PAUSED))

    result = await _facade(core).create_principle_expression(
        {"principle_uid": "principle_1", "context": "Work", "behavior": "Focus"}
    )

    assert result.is_ok, result
    assert result.value == {"context": "Work", "behavior": "Focus", "example": None}
    [(uid, updates, guard)] = recorder.calls
    assert uid == "principle_1"
    assert updates == {"expressions": [HOME, PrincipleExpression(context="Work", behavior="Focus")]}
    assert guard == StatusWriteGuard()


async def test_an_expression_on_a_missing_principle_is_not_found() -> None:
    core, recorder, _bus = _core(_principle())
    core.backend.rewrite_under_lock = AsyncMock(
        return_value=Result.fail(Errors.not_found("Principle", "principle_9"))
    )

    result = await _facade(core).create_principle_expression(
        {"principle_uid": "principle_9", "context": "Work", "behavior": "Focus"}
    )

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.NOT_FOUND
    assert recorder.calls == []


async def test_an_expression_without_a_behavior_is_refused_before_the_write() -> None:
    core, recorder, _bus = _core(_principle())

    result = await _facade(core).create_principle_expression(
        {"principle_uid": "principle_1", "context": "Work", "behavior": ""}
    )

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.VALIDATION
    assert recorder.calls == []


def _keep_expressions(principle: Principle) -> dict[str, list[PrincipleExpression]]:
    return {"expressions": list(principle.expressions)}


async def test_a_rewrite_announces_the_fields_it_wrote() -> None:
    core, _recorder, bus = _core(_principle())

    result = await core.rewrite_principle("principle_1", _keep_expressions)

    assert result.is_ok, result
    [updated] = [
        call.args[0]
        for call in bus.publish_async.await_args_list
        if isinstance(call.args[0], PrincipleUpdated)
    ]
    assert updated.principle_uid == "principle_1"
    assert updated.user_uid == USER
    assert updated.updated_fields == {"expressions": [HOME]}


async def test_a_rewrite_naming_an_illegal_status_writes_nothing() -> None:
    core, recorder, _bus = _core(_principle())

    def complete(_principle: Principle) -> dict[str, str]:
        return {"status": EntityStatus.COMPLETED.value}

    result = await core.rewrite_principle("principle_1", complete)

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.VALIDATION
    assert recorder.calls == []

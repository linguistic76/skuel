"""``UserContextService.complete_task_with_context`` records the time invested.

The context-aware completion API is the only surface that collects "how long did
this actually take", and it used to throw the number away: the value was
destructured out of an untyped ``dict[str, Any]`` at the top of the method and
then dropped in a ``TODO(deferred)`` block, while ``TasksService.complete_task``
had accepted an ``actual_minutes`` argument all along.

These pin the wiring in both directions — a supplied value reaches
``complete_task`` as ``actual_minutes``, and an absent one passes ``None``, which
the completion cascade turns into "omit the property" rather than a null that
would erase a previously recorded value.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.task.task import Task
from core.services.user.user_context_service import UserContextService
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_TASK_UID = "task_1"


def _task(user_uid: str = _USER_UID) -> Task:
    return Task(uid=_TASK_UID, title="Write the thing", user_uid=user_uid)


def _service(task: Task | None = None) -> tuple[UserContextService, Any]:
    tasks = MagicMock()
    tasks.get = AsyncMock(return_value=Result.ok(task if task is not None else _task()))
    tasks.complete_task = AsyncMock(return_value=Result.ok(_task()))
    service = UserContextService(
        context_builder=MagicMock(),
        user_service=MagicMock(),
        tasks_service=tasks,
    )
    return service, tasks


class TestTimeInvestedReachesTheTask:
    @pytest.mark.asyncio
    async def test_minutes_forwarded_as_actual_minutes(self) -> None:
        service, tasks = _service()

        result = await service.complete_task_with_context(
            _TASK_UID, _USER_UID, time_invested_minutes=120
        )

        assert result.is_ok
        tasks.complete_task.assert_awaited_once_with(_TASK_UID, actual_minutes=120)

    @pytest.mark.asyncio
    async def test_absent_minutes_forwards_none(self) -> None:
        """``None`` is passed through, not coerced to 0.

        Zero would be a claim ("this took no time"); ``None`` means "not
        reported", which the cascade honours by leaving the property alone.
        """
        service, tasks = _service()

        result = await service.complete_task_with_context(_TASK_UID, _USER_UID)

        assert result.is_ok
        tasks.complete_task.assert_awaited_once_with(_TASK_UID, actual_minutes=None)

    @pytest.mark.asyncio
    async def test_zero_minutes_is_forwarded_verbatim(self) -> None:
        """0 is a legal reported value (``ge=0``) and must not be read as absent."""
        service, tasks = _service()

        result = await service.complete_task_with_context(
            _TASK_UID, _USER_UID, time_invested_minutes=0
        )

        assert result.is_ok
        tasks.complete_task.assert_awaited_once_with(_TASK_UID, actual_minutes=0)


class TestDeliberatelyUnwiredContext:
    @pytest.mark.asyncio
    async def test_knowledge_applied_and_quality_do_not_reach_the_task(self) -> None:
        """Accepted and validated, but not yet acted on — by decision.

        ``knowledge_applied`` means APPLIES_KNOWLEDGE edges and substance
        events (a feature, not a repair), and ``quality`` is a string while
        ``complete_task``'s ``quality_score`` is a 1-5 int feeding a logging
        stub. Neither is invented here; this pins that they stay out of the
        write until they are designed.
        """
        service, tasks = _service()

        result = await service.complete_task_with_context(
            _TASK_UID,
            _USER_UID,
            time_invested_minutes=30,
            knowledge_applied=["ku.python"],
            quality="great",
        )

        assert result.is_ok
        assert tasks.complete_task.await_args.kwargs == {"actual_minutes": 30}


class TestOwnership:
    @pytest.mark.asyncio
    async def test_foreign_task_is_not_completed(self) -> None:
        """404, and no write — the ownership guard runs before the completion."""
        service, tasks = _service(task=_task(user_uid="user_someone_else"))

        result = await service.complete_task_with_context(
            _TASK_UID, _USER_UID, time_invested_minutes=120
        )

        assert result.is_error
        tasks.complete_task.assert_not_awaited()

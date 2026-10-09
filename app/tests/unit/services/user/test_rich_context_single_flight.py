"""One MEGA-QUERY per cold miss, however many readers miss together.

``UserService.get_rich_unified_context`` caches a user's rich context for five
minutes; on a miss it builds it. The six Insights cards load one page as six
concurrent fragment requests, and the Today surface reads beside the sidebar —
readers that miss together must share the one build, not each run the
MEGA-QUERY. A reader cancelled mid-build must not cancel the build under the
others; a settled build must be forgotten so the next miss starts a fresh one.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.user._context_planning_mixin import _ContextPlanningMixin
from core.services.user.unified_user_context import RichUserContext
from core.utils.result_simplified import Result

USER = "user_single_flight"


class _Service(_ContextPlanningMixin):
    """The planning mixin over a builder that takes a moment, and a cache that misses."""

    def __init__(self, builder_delay: float = 0.05) -> None:
        self._rich_context_builds = {}
        self.builds = 0

        async def _build(user_uid: str, min_confidence: float) -> Result[RichUserContext]:
            self.builds += 1
            await asyncio.sleep(builder_delay)
            return Result.ok(RichUserContext(user_uid=user_uid))

        self.context_builder: Any = MagicMock()
        self.context_builder.build_rich = AsyncMock(side_effect=_build)
        self.activity: Any = MagicMock()
        self.activity.get_valid_context = MagicMock(return_value=None)
        self.activity.cache_context = MagicMock()


@pytest.mark.asyncio
async def test_six_readers_missing_together_share_one_build() -> None:
    service = _Service()

    results = await asyncio.gather(*(service.get_rich_unified_context(USER) for _ in range(6)))

    assert all(r.is_ok for r in results)
    assert service.builds == 1
    assert {id(r.value) for r in results} == {id(results[0].value)}
    assert service._rich_context_builds == {}  # forgotten once settled


@pytest.mark.asyncio
async def test_a_later_miss_builds_again() -> None:
    service = _Service()
    await service.get_rich_unified_context(USER)
    await service.get_rich_unified_context(USER)
    assert service.builds == 2


@pytest.mark.asyncio
async def test_a_cancelled_reader_does_not_cancel_the_build_under_the_others() -> None:
    service = _Service()
    first = asyncio.create_task(service.get_rich_unified_context(USER))
    await asyncio.sleep(0)  # the first reader has started the build
    second = asyncio.create_task(service.get_rich_unified_context(USER))
    await asyncio.sleep(0)
    first.cancel()

    result = await second

    assert result.is_ok and service.builds == 1
    with pytest.raises(asyncio.CancelledError):
        await first


@pytest.mark.asyncio
async def test_different_confidences_are_different_builds() -> None:
    service = _Service()
    await asyncio.gather(
        service.get_rich_unified_context(USER, min_confidence=0.7),
        service.get_rich_unified_context(USER, min_confidence=0.9),
    )
    assert service.builds == 2

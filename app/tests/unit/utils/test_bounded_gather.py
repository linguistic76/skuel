"""``gather_bounded``: every result, in order, with a ceiling on what is in flight."""

import asyncio

import pytest

from core.constants import RelationshipFanOut
from core.utils.bounded_gather import gather_bounded


class _InFlight:
    """Counts how many ``work`` calls are running at once."""

    def __init__(self) -> None:
        self.now = 0
        self.peak = 0

    async def work(self, value: int) -> int:
        self.now += 1
        self.peak = max(self.peak, self.now)
        await asyncio.sleep(0)
        self.now -= 1
        return value


async def test_results_keep_the_input_order():
    tracker = _InFlight()

    results = await gather_bounded((tracker.work(i) for i in range(20)), limit=4)

    assert results == list(range(20))


async def test_no_more_than_the_limit_run_at_once():
    tracker = _InFlight()

    await gather_bounded((tracker.work(i) for i in range(20)), limit=4)

    assert tracker.peak == 4


async def test_the_default_limit_is_the_relationship_fan_out_ceiling():
    tracker = _InFlight()

    await gather_bounded(tracker.work(i) for i in range(20))

    assert tracker.peak == RelationshipFanOut.MAX_ENTITIES_IN_FLIGHT


async def test_an_empty_input_is_an_empty_list():
    assert await gather_bounded(iter(())) == []


async def test_an_items_exception_propagates():
    async def fails() -> int:
        raise RuntimeError("boom")

    tracker = _InFlight()

    with pytest.raises(RuntimeError, match="boom"):
        await gather_bounded([tracker.work(1), fails()], limit=2)

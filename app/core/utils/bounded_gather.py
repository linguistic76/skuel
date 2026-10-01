"""
Bounded concurrent fan-out
==========================

``asyncio.gather`` over a collection starts everything at once. When each item
is a graph read — a per-entity relationship fetch runs about a dozen queries —
a large collection asks the driver's connection pool for thousands of
connections in one burst, and every other request waits behind it.

``gather_bounded`` runs the same awaitables with a ceiling on how many are in
flight, and returns their results in the order given.
"""

import asyncio
from collections.abc import Awaitable, Iterable

from core.constants import RelationshipFanOut


async def gather_bounded[T](
    awaitables: Iterable[Awaitable[T]],
    *,
    limit: int = RelationshipFanOut.MAX_ENTITIES_IN_FLIGHT,
) -> list[T]:
    """
    Await every item, at most ``limit`` at a time; results keep the input order.

    The first exception raised by an item propagates, as it does from
    ``asyncio.gather``.

    Args:
        awaitables: The work to run — one awaitable per item.
        limit: The most awaitables in flight at once.
    """
    in_flight = asyncio.Semaphore(limit)

    async def _run(awaitable: Awaitable[T]) -> T:
        async with in_flight:
            return await awaitable

    return list(await asyncio.gather(*[_run(awaitable) for awaitable in awaitables]))

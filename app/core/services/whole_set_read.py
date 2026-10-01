"""
Whole-set reads — bounded, and audible when the bound is reached
================================================================

``backend.find_by`` is the generic query door and returns a page: ``limit=100``
unless the caller writes one, in no particular order unless the caller asks for
one. A service whose question is about a WHOLE set — every task a user owns,
every step in a category — and that counts, averages or ranks what comes back is
answering about an arbitrary hundred of them.

``find_all_by`` is the read for that question. It asks for
``QueryLimit.MAXIMUM`` rows and, when exactly that many come back, logs a
warning: a full page may not be the whole set, and the figures computed from it
may be short.

``warn_if_capped`` is the warning half alone, for a whole-set read that goes
through another door (``find_by_date_range``, ``get_user_entities``) with the
same bound.
"""

from collections.abc import Sized
from typing import Protocol

from core.constants import QueryLimit
from core.models.protocols import DomainModelProtocol
from core.models.type_hints import Neo4jValue
from core.ports.base_protocols import EntitySearchOperations
from core.utils.result_simplified import Result


class WarningLogger(Protocol):
    """The one logger method these helpers call — stdlib and structlog both provide it."""

    def warning(self, msg: str, /, *args: object) -> object: ...


def warn_if_capped(
    logger: WarningLogger, reading: str, rows: Sized, /, **scope: Neo4jValue
) -> None:
    """
    Log a warning when a whole-set read came back with ``QueryLimit.MAXIMUM`` rows.

    Args:
        logger: The calling service's logger.
        reading: What the caller computes from the set ("Task performance analytics").
        rows: The rows the read returned.
        **scope: The filters that define the set, for the log line.
    """
    if len(rows) >= QueryLimit.MAXIMUM:
        logger.warning(
            "%s read %d rows, the cap, for %s — the set may be larger and the result truncated",
            reading,
            QueryLimit.MAXIMUM,
            scope,
        )


async def find_all_by[T: DomainModelProtocol](
    backend: EntitySearchOperations[T],
    logger: WarningLogger,
    reading: str,
    /,
    **filters: Neo4jValue,
) -> Result[list[T]]:
    """
    Read every entity matching ``filters``, up to ``QueryLimit.MAXIMUM``.

    A failed read is returned as it failed. A read that fills the cap is returned
    whole and logged through ``warn_if_capped``.

    Args:
        backend: The calling service's backend.
        logger: The calling service's logger.
        reading: What the caller computes from the set, for the log line.
        **filters: ``find_by`` filters; ``limit`` is this function's to set.

    Backend: UniversalNeo4jBackend.find_by
    """
    result = await backend.find_by(limit=QueryLimit.MAXIMUM, **filters)
    if result.is_ok:
        warn_if_capped(logger, reading, result.value or [], **filters)
    return result

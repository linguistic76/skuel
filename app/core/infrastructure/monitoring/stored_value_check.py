"""In-app stored-value check — the stored-value census, read by the graph-health poller.

A stored value its field's declared type cannot read fails every backend read of
its node (``UnreadableStoredValueError``, ``adapters/persistence/neo4j/neo4j_mapper.py``).
The stored-value census (``./dev stored-value-census``,
``scripts/stored_value_census.py``) names each one; this is the same verdict read
where it binds, by the running app. The 5-min graph-health poller
(``scripts/dev/bootstrap.py``) reads the graph's unreadable values through
``StoredValueCensusBackend.read_summary``, sets the gauge
``skuel_stored_values_unreadable_count`` that the dev stack's
``StoredValueUnreadable`` alert reads, and calls ``check_stored_values``. Production
runs no Prometheus, so this check's ERROR log is its alert: every cycle while one
is stored (the uid grammar check's posture, ``uid_grammar_check.py``).
"""

from dataclasses import dataclass
from typing import Final

from core.utils.logging import get_logger

logger = get_logger("skuel.monitoring.stored_values")

#: How many unreadable values the poller logs by name.
STORED_VALUE_SAMPLE: Final = 5

_REMEDIATION = (
    "every read of each node fails until its value is migrated — "
    "run ./dev stored-value-census to name each one"
)


@dataclass(frozen=True)
class UnreadableStoredValues:
    """The graph's unreadable stored values, counted, with a few named.

    Each sample entry reads ``{class} {uid}.{field}``.
    """

    count: int
    sample: tuple[str, ...] = ()


def check_stored_values(found: UnreadableStoredValues) -> None:
    """Log ERROR while the graph holds an unreadable value; silent when it holds none."""
    if found.count:
        logger.error(
            f"unreadable stored values: {found.count:,} "
            f"(e.g. {', '.join(found.sample)}) — {_REMEDIATION}"
        )

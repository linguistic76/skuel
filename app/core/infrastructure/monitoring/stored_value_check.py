"""In-app stored-value check — the stored-value census, read by the graph-health poller.

A stored value its field's declared type cannot read, or a field its class requires
that the node does not hold, fails every backend read of its node
(``UnreadableStoredValueError``, ``adapters/persistence/neo4j/neo4j_mapper.py``).
A stored property that is neither a field nor registered node state of its node's
class (``core/models/node_state.py``) fails no read, but no read reads it: its writer
stored a key nothing declares. The stored-value census (``./dev stored-value-census``,
``scripts/stored_value_census.py``) names each of both; this is the same verdict read
where it binds, by the running app. The 5-min graph-health poller
(``scripts/dev/bootstrap.py``) reads both through
``StoredValueCensusBackend.read_summary``, sets the gauges
``skuel_stored_values_unreadable_count`` and ``skuel_stored_keys_undeclared_count``
that the dev stack's ``StoredValueUnreadable`` and ``StoredKeyUndeclared`` alerts
read, and calls ``check_stored_values`` and ``check_undeclared_keys``. Production runs
no Prometheus, so these checks' logs are its alert: every cycle while one is stored —
ERROR for an unreadable value (the uid grammar check's posture, ``uid_grammar_check.py``),
WARNING for a key no read reads.
"""

from dataclasses import dataclass
from typing import Final

from core.utils.logging import get_logger

logger = get_logger("skuel.monitoring.stored_values")

#: How many unreadable values the poller logs by name.
STORED_VALUE_SAMPLE: Final = 5

_REMEDIATION = (
    "every read of each node fails until it is migrated — "
    "run ./dev stored-value-census to name each one"
)

_UNDECLARED_REMEDIATION = (
    "no read reads them — run ./dev stored-value-census to name each one, then "
    "fix its writer, or register the key as node state (core/models/node_state.py)"
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


@dataclass(frozen=True)
class UndeclaredStoredKeys:
    """The graph's stored properties no read reads, counted, with a few named.

    Each sample entry reads ``{class} {uid}.{key}``.
    """

    count: int
    sample: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoredNodeCensus:
    """One read of the stored-value census: unreadable values and keys no read reads."""

    unreadable: UnreadableStoredValues
    undeclared: UndeclaredStoredKeys


def check_undeclared_keys(found: UndeclaredStoredKeys) -> None:
    """Log WARNING while the graph holds a key no read reads; silent when it holds none."""
    if found.count:
        logger.warning(
            f"stored keys no read reads: {found.count:,} "
            f"(e.g. {', '.join(found.sample)}) — {_UNDECLARED_REMEDIATION}"
        )

"""
Stored-Value Census Backend — every stored value read as its field's type
=========================================================================

Read-only. For every label a backend reads through ``from_neo4j_node``, reads each
node's properties (the embedding vector left out) and reads every one as its
field's type through the mapper's own rule (``unreadable_fields``), so the census
refuses exactly what a read refuses.
``scripts/stored_value_census.py`` (``./dev stored-value-census``) lists them; the
graph-health poller counts them. Nothing is written.

Like the uid census backend, it spans every label, so it takes a
``Neo4jQueryExecutor`` directly rather than extending ``UniversalNeo4jBackend``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from adapters.persistence.neo4j.neo4j_mapper import UnreadableStoredValueError, unreadable_fields
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.infrastructure.monitoring.stored_value_check import UnreadableStoredValues
from core.models.auth.session import Session
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.models.user.user import User
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

#: A label and the class its backend reads its nodes as.
MapperReader = tuple[NeoLabel, type]

#: The node readers that are not ``UniversalNeo4jBackend``s.
_DEDICATED_READERS: tuple[MapperReader, ...] = (
    (NeoLabel.USER, User),
    (NeoLabel.SESSION, Session),
)


def mapper_readers(backends: Iterable[object]) -> tuple[MapperReader, ...]:
    """Every (label, class) the given backends read nodes as, plus users and sessions.

    The base ``Entity`` reader is left out: each of its nodes is read as its own
    kind under its own label, so it would name every unreadable value twice.
    """
    readers: dict[MapperReader, None] = dict.fromkeys(_DEDICATED_READERS)
    for backend in backends:
        if isinstance(backend, UniversalNeo4jBackend) and backend.entity_class is not Entity:
            readers[(backend.label, backend.entity_class)] = None
    return tuple(sorted(readers, key=_reader_order))


def _reader_order(reader: MapperReader) -> tuple[str, str]:
    return reader[0].value, reader[1].__name__


class StoredValueCensusBackend:
    """Read every converted property of every node a backend reads, as its field's type."""

    def __init__(
        self, executor: Neo4jQueryExecutor, readers: tuple[MapperReader, ...] = ()
    ) -> None:
        """``readers`` is set by ``create_all_backends`` once every backend is built."""
        self._executor = executor
        self.readers = readers

    async def read_unreadable(self) -> Result[list[UnreadableStoredValueError]]:
        """Each stored value a read would refuse, once per node and field."""
        found: dict[tuple[object, str], UnreadableStoredValueError] = {}
        for label, entity_class in self.readers:
            # Every property, with the vector overridden so it is not shipped: a
            # thousand floats a node on every poll, written only by the embedding
            # writer. Naming each converted field instead would draw a server
            # warning for every one the graph has never stored.
            result = await self._executor.execute_query(
                f"MATCH (n:`{label.value}`) RETURN n {{.*, embedding: null}} AS n"
            )
            if result.is_error:
                return Result.fail(result)
            for row in result.value:
                for refusal in unreadable_fields(row["n"], entity_class):
                    found.setdefault((refusal.uid, refusal.field), refusal)
        return Result.ok(list(found.values()))

    async def read_summary(self, sample: int) -> Result[UnreadableStoredValues]:
        """How many stored values a read would refuse, ``sample`` of them named."""
        found = await self.read_unreadable()
        if found.is_error:
            return Result.fail(found)
        return Result.ok(
            UnreadableStoredValues(
                count=len(found.value),
                sample=tuple(
                    f"{refusal.entity_class} {refusal.uid}.{refusal.field}"
                    for refusal in found.value[:sample]
                ),
            )
        )

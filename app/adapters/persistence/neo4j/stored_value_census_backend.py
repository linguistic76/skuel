"""
Stored-Value Census Backend — every stored value read as its field's type
=========================================================================

Read-only. For every label a backend reads through ``from_neo4j_node``, reads each
node's properties (the embedding vector left out) and reads every field of the
node's class through the mapper's own rule (``unreadable_fields``) — each stored
value as its type, each required field as present — so the census refuses exactly
what a read refuses. It also names each stored property no read reads: a key that is
neither a field nor registered node state of the node's class (``undeclared_keys``,
``core/models/node_state.py``).
``scripts/stored_value_census.py`` (``./dev stored-value-census``) lists both; the
graph-health poller counts both; the integration suite's graph census
(``tests/integration/_graph_census.py``) fails a test on either it wrote, from one read
(``read_findings``). Nothing is written.

Like the uid census backend, it spans every label, so it takes a
``Neo4jQueryExecutor`` directly rather than extending ``UniversalNeo4jBackend``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from adapters.persistence.neo4j.neo4j_mapper import (
    UnreadableStoredValueError,
    undeclared_keys,
    unreadable_fields,
)
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.infrastructure.monitoring.stored_value_check import (
    StoredNodeCensus,
    UndeclaredStoredKeys,
    UnreadableStoredValues,
)
from core.models.auth.session import Session
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import Neo4jProperties
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


def _census_order(refusal: UnreadableStoredValueError) -> tuple[str, str, str]:
    return refusal.entity_class, str(refusal.uid), refusal.field


class StoredValueCensusBackend:
    """Read every converted property of every node a backend reads, as its field's type."""

    def __init__(
        self, executor: Neo4jQueryExecutor, readers: tuple[MapperReader, ...] = ()
    ) -> None:
        """``readers`` is set by ``create_all_backends`` once every backend is built."""
        self._executor = executor
        self.readers = readers

    async def read_unreadable(self) -> Result[list[UnreadableStoredValueError]]:
        """Each field a read would refuse, once per node and field.

        A stored value its type cannot read, or a field the class requires that the
        node does not hold. Each node is read as every class its labels name.
        """
        nodes = await self._read_nodes()
        if nodes.is_error:
            return Result.fail(nodes)
        return Result.ok(_unreadable(nodes.value))

    async def read_undeclared(self) -> Result[list[UndeclaredStoredKey]]:
        """Each stored property no read reads, once per node and key.

        A key that is neither a field nor registered node state
        (``core/models/node_state.py``) of any class the node's labels name: the read
        skips it, so nothing reads what its writer stored.
        """
        nodes = await self._read_nodes()
        if nodes.is_error:
            return Result.fail(nodes)
        return Result.ok(_undeclared(nodes.value))

    async def read_findings(self) -> Result[StoredNodeFindings]:
        """Each field a read would refuse and each stored property no read reads — from
        one read of the graph."""
        nodes = await self._read_nodes()
        if nodes.is_error:
            return Result.fail(nodes)
        return Result.ok(
            StoredNodeFindings(
                unreadable=_unreadable(nodes.value), undeclared=_undeclared(nodes.value)
            )
        )

    async def read_summary(self, sample: int) -> Result[StoredNodeCensus]:
        """How many fields a read would refuse and how many stored keys no read reads,
        ``sample`` of each named — from one read of the graph."""
        findings = await self.read_findings()
        if findings.is_error:
            return Result.fail(findings)
        unreadable = findings.value.unreadable
        undeclared = findings.value.undeclared
        return Result.ok(
            StoredNodeCensus(
                unreadable=UnreadableStoredValues(
                    count=len(unreadable),
                    sample=tuple(
                        f"{refusal.entity_class} {refusal.uid}.{refusal.field}"
                        for refusal in unreadable[:sample]
                    ),
                ),
                undeclared=UndeclaredStoredKeys(
                    count=len(undeclared),
                    sample=tuple(
                        f"{key.entity_class} {key.uid}.{key.key}" for key in undeclared[:sample]
                    ),
                ),
            )
        )

    async def _read_nodes(self) -> Result[list[_CensusNode]]:
        """Every node carrying a label some backend reads, with the classes it is read as.

        One statement, not one per label: each is a round trip, and the integration suite
        reads this around every test.
        """
        classes_by_label: dict[str, list[type]] = {}
        for label, entity_class in self.readers:
            classes_by_label.setdefault(label.value, []).append(entity_class)
        # Every property, with the vector overridden so it is not shipped: a thousand
        # floats a node on every poll, written only by the embedding writer. Naming
        # each converted field instead would draw a server warning for every one the
        # graph has never stored. The override lands on every node, so whether one
        # stores a vector comes back beside it.
        result = await self._executor.execute_query(
            "MATCH (n) WHERE any(label IN labels(n) WHERE label IN $labels) "
            "RETURN labels(n) AS labels, n {.*, embedding: null} AS n, "
            "n.embedding IS NOT NULL AS embedded",
            {"labels": sorted(classes_by_label)},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                _CensusNode(
                    properties=_stored_properties(row["n"], embedded=row["embedded"]),
                    classes=tuple(
                        entity_class
                        for label in row["labels"]
                        for entity_class in classes_by_label.get(label, ())
                    ),
                )
                for row in result.value
            ]
        )


def _stored_properties(projected: Neo4jProperties, *, embedded: bool) -> Neo4jProperties:
    """The node's properties as stored: the vector's key only where one is stored."""
    if embedded:
        return projected
    return {key: value for key, value in projected.items() if key != "embedding"}


@dataclass(frozen=True)
class _CensusNode:
    """One node's properties and every class its labels name."""

    properties: Neo4jProperties
    classes: tuple[type, ...]


def _unreadable(nodes: list[_CensusNode]) -> list[UnreadableStoredValueError]:
    found: dict[tuple[object, str], UnreadableStoredValueError] = {}
    for node in nodes:
        for entity_class in node.classes:
            for refusal in unreadable_fields(node.properties, entity_class):
                found.setdefault((refusal.uid, refusal.field), refusal)
    return sorted(found.values(), key=_census_order)


def _undeclared(nodes: list[_CensusNode]) -> list[UndeclaredStoredKey]:
    found: list[UndeclaredStoredKey] = []
    for node in nodes:
        if not node.classes:
            continue
        # A key one of the node's classes declares or registers is read; it is
        # undeclared only when every class it is read as leaves it.
        undeclared = set.intersection(
            *(set(undeclared_keys(node.properties, cls)) for cls in node.classes)
        )
        found.extend(
            UndeclaredStoredKey(
                entity_class=node.classes[0].__name__,
                uid=node.properties.get("uid"),
                key=key,
            )
            for key in sorted(undeclared)
        )
    return sorted(found, key=_undeclared_order)


@dataclass(frozen=True)
class UndeclaredStoredKey:
    """A stored property no read reads: neither a field nor node state of its node's class."""

    entity_class: str
    uid: object
    key: str


def _undeclared_order(found: UndeclaredStoredKey) -> tuple[str, str, str]:
    return found.entity_class, str(found.uid), found.key


@dataclass(frozen=True)
class StoredNodeFindings:
    """What one read of the graph finds: each field a read refuses, each key no read reads."""

    unreadable: list[UnreadableStoredValueError]
    undeclared: list[UndeclaredStoredKey]

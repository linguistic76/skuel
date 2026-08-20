"""
Relationship Builder — the typed fluent front door for writing one edge
=======================================================================

Philosophy: "Plain English in, working code out." A relationship written in
code should read as the sentence it represents::

    await (
        relate(self.backend, task.uid)
        .via(RelationshipName.APPLIES_KNOWLEDGE)
        .to(ku.uid)
        .with_properties(confidence=0.85)
        .create()
    )

**What this is.** A facade over ``backend.add_relationship`` with *no logic of
its own* — it accumulates three values and delegates. That restraint is the
point: SKUEL keeps paying for having several implementations of one operation
(three badge-stat implementations, three "the user's completions" reads), so
this deliberately adds a front door, not a second path.

**What it buys over calling ``add_relationship`` directly**, and why it is worth
a file:

- **Source and target cannot be swapped.** They are set at different call sites
  in a forced order, so passing one where the other belongs is not expressible.
  ``add_relationship(from_uid, to_uid, ...)`` takes two adjacent ``str``
  parameters — swapping them writes a backwards edge silently.
- **Nothing can be omitted.** Each step returns a *different type*, so mypy
  rejects ``.create()`` before the edge is complete. The service-facing
  ``RelationshipOperationsMixin.add_relationship`` needs a runtime
  ``if not all([from_uid, rel_type, to_uid])`` guard; here that state cannot be
  constructed.
- **The edge type is the enum, never a string.** No ``RelationshipName[...]``
  lookup that can raise at runtime — SKUEL013/SKUEL030 exist to keep edge names
  out of string form, and this door has no string form to keep out.

**What this is NOT.** It does not replace
``UnifiedRelationshipService.create_relationship``, which is registry-driven and
*direction-aware*: it resolves an edge from a config key and orients it per the
registry (an ``incoming`` spec is stored related→owner). That answers "attach
this related entity per my domain config". This answers "write exactly this edge
in exactly this direction" — two different jobs, and conflating them would
reintroduce the orientation bugs the registry exists to prevent.

**Why it lives here and not in ``core/services/relationships/``.** That package's
``__init__`` eagerly imports ``UnifiedRelationshipService``, which imports
``BaseService``, which imports the mixin that uses this builder — a circular
import at runtime. Mypy does not execute imports and reported nothing; the test
suite failed to collect 46 modules. ``core/services/`` is a namespace package
with no ``__init__``, so nothing runs on the way to this module.

See: /docs/patterns/protocol_architecture.md (why the previous fluent attempt,
``RelationshipBuilder`` in ``adapters/persistence/neo4j/``, could never be called
from a service).
"""

from typing import final

from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, Neo4jValue
from core.ports.base_protocols import RelationshipCrudOperations
from core.utils.result_simplified import Result


@final
class _EdgeAwaitingType:
    """A source is set; the edge type is not. Only ``via`` is available."""

    __slots__ = ("_backend", "_source_uid")

    def __init__(self, backend: RelationshipCrudOperations, source_uid: str) -> None:
        self._backend = backend
        self._source_uid = source_uid

    def via(self, relationship: RelationshipName) -> "_EdgeAwaitingTarget":
        """Name the edge type. Takes the enum — there is no string overload."""
        return _EdgeAwaitingTarget(self._backend, self._source_uid, relationship)


@final
class _EdgeAwaitingTarget:
    """Source and type are set; the target is not. Only ``to`` is available."""

    __slots__ = ("_backend", "_relationship", "_source_uid")

    def __init__(
        self,
        backend: RelationshipCrudOperations,
        source_uid: str,
        relationship: RelationshipName,
    ) -> None:
        self._backend = backend
        self._source_uid = source_uid
        self._relationship = relationship

    def to(self, target_uid: str) -> "_EdgeReady":
        """Name the target. The edge is now complete and can be written."""
        return _EdgeReady(self._backend, self._source_uid, self._relationship, target_uid)


@final
class _EdgeReady:
    """A complete edge. This is the only stage that exposes ``create``."""

    __slots__ = ("_backend", "_properties", "_relationship", "_source_uid", "_target_uid")

    def __init__(
        self,
        backend: RelationshipCrudOperations,
        source_uid: str,
        relationship: RelationshipName,
        target_uid: str,
    ) -> None:
        self._backend = backend
        self._source_uid = source_uid
        self._relationship = relationship
        self._target_uid = target_uid
        self._properties: Neo4jProperties = {}

    def with_properties(self, **properties: Neo4jValue) -> "_EdgeReady":
        """Add edge properties. Repeat calls merge; later keys win."""
        self._properties.update(properties)
        return self

    async def create(self) -> Result[bool]:
        """Write the edge. ``MERGE`` semantics belong to the backend, not here."""
        return await self._backend.add_relationship(
            from_uid=self._source_uid,
            to_uid=self._target_uid,
            relationship_type=self._relationship,
            properties=self._properties or None,
        )


def relate(backend: RelationshipCrudOperations, source_uid: str) -> _EdgeAwaitingType:
    """Begin writing one edge from ``source_uid``.

    The return type changes at every step, so the compiler — not a runtime guard
    — enforces that an edge is complete before it can be written.
    """
    return _EdgeAwaitingType(backend, source_uid)


__all__ = ["relate"]

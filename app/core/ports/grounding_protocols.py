"""
Knowledge-Grounding Port
========================

The persistence contract of Ku grounding: a source entity's stored embedding is
matched against the Ku vector index and the matches are written as inferred
``APPLIES_KNOWLEDGE`` edges. Two sources ground through it — a UserEntry on a
grounded pipeline (``EntryGroundingBackend``) and a Task (``TaskGroundingBackend``)
— and both run the one pass in ``KnowledgeGroundingService``.

Implementations: ``adapters/persistence/neo4j/knowledge_grounding_backend.py``
(the shared statements) and its two sources, ``entry_grounding_backend.py`` and
``task_grounding_backend.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.models.type_hints import UserUID
from core.ports.query_types import GroundingRemovalRow, GroundingSourceRow
from core.utils.result_simplified import Result


@runtime_checkable
class KnowledgeGroundingBackendOperations(Protocol):
    """Pending reads, inferred-edge writes, the grounded stamp and the removal, for one source.

    Every method takes the source entity's uid. Which entities may ground is the
    source's own rule (an entry's pipeline and privacy, a task's status), held by the
    pending read and again under the entity's write-lock by the write and the stamp.
    """

    async def get_pending(
        self,
        user_uid: str | None = None,
        force: bool = False,
        source_uid: str | None = None,
    ) -> Result[list[GroundingSourceRow]]:
        """Embedded entities that may ground and whose grounding stamp is missing or stale.

        ``user_uid`` scopes to one owner, ``source_uid`` to one entity; ``force``
        includes entities whose stamp is current.
        """
        ...

    async def write_applies_knowledge(
        self, source_uid: str, ku_uid: str, confidence: float
    ) -> Result[bool]:
        """Ground an entity in a published Ku, stamping provenance on first write only.

        True iff this call created the link — a link the owner already made is never
        restamped as inferred, and the caller publishes the substance event only on
        True. A draft Ku, a pair the owner removed, or an entity the source's rule does
        not admit at the write links nothing (False).
        """
        ...

    async def stamp_grounded(self, source_uid: str, text_hash: str, version: int) -> Result[None]:
        """Mark the entity's grounding pass complete for its current embedding text.

        A no-op when the source's rule does not admit the entity at the stamp, or its
        embedding text is not the text the pass read.
        """
        ...

    async def remove_grounded_edge(
        self, source_uid: str, ku_uid: str, user_uid: UserUID
    ) -> Result[GroundingRemovalRow | None]:
        """Ownership-scoped delete of an INFERRED edge + rejection record.

        None when nothing matched: the entity is not the user's, the edge is absent,
        or the owner made the link (an owner's link is not removed here).
        """
        ...


__all__ = ["KnowledgeGroundingBackendOperations"]

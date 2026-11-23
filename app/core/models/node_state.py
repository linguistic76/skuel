"""
Node state — properties a node carries that its class does not declare.
=======================================================================

Some properties of a node are written and read only by a backend's own Cypher, never
through the model: learning state a handler calibrates (ADR-048), stamps a background
pass leaves (embedding, grounding), the vault sweep's retirement marks, counters a
credit increments. The model declares none of them, so ``from_neo4j_node`` skips them
and the mapper's writers refuse them.

Each such property is registered on its class, beside its fields, as ``NODE_STATE``
— a ``ClassVar`` frozenset, so it is no dataclass field. ``node_state`` reads a class's
own registration with every base's. The stored-value census names any stored property
that is neither a field nor registered state of the class its node is read as
(``StoredValueCensusBackend.read_undeclared``): stored, it is a property no read reads.

A registered key is not a field (a field needs no registration), and each names its
writer and reader where it is registered.

See: /docs/decisions/ADR-048-adaptive-learning-loop.md
"""

from __future__ import annotations

from typing import Final

#: The embedding writer's freshness stamps on every embedded node
#: (``EmbeddingsBackend.store_embedding_metadata``); ``verify_fresh_embeddings`` and the
#: stale audit read them. The vector, its model and its time are fields.
EMBEDDING_STAMPS: Final[frozenset[str]] = frozenset({"embedding_text_hash", "embedding_version"})

#: The knowledge-grounding pass's record on a grounded source, a Task or a UserEntry
#: (``KnowledgeGroundingBackend.stamp_grounded`` / ``remove_grounded_edge``, and the
#: UserEntry upsert's retraction). The pending read compares ``grounded_text_hash``; the
#: link writers read ``grounding_rejected_ku_uids``. ``grounding_version`` is stamped on
#: every pass and read by nothing yet: a later change to what grounding means can target
#: the passes stamped before it.
GROUNDING_STAMPS: Final[frozenset[str]] = frozenset(
    {"grounded_at", "grounded_text_hash", "grounding_version", "grounding_rejected_ku_uids"}
)


def node_state(entity_class: type) -> frozenset[str]:
    """Every property ``entity_class``'s nodes may carry beside its fields.

    The class's own ``NODE_STATE`` with every base's.
    """
    registered: set[str] = set()
    for cls in entity_class.__mro__:
        registered |= vars(cls).get("NODE_STATE", frozenset())
    return frozenset(registered)

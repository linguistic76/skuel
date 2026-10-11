"""
Link write contracts — what a guarded link write is handed, and what it answers.
==============================================================================

A link door admits each far end before it writes (``core/services/mixins/
link_edge_guard.py``). The write itself re-asserts that rule in the statement that
merges the edge, so a far end deleted, re-owned or unpublished between the admission
and the write is refused rather than linked. These two value types are that write's
input and output; the backend method is ``write_guarded_links``
(``RelationshipCrudOperations``).

See: /docs/decisions/ADR-085-ownership-read-enforcement-contract.md (G11)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.enums.neo_labels import NeoLabel
    from core.models.relationship_names import RelationshipName
    from core.models.type_hints import Neo4jProperties


@dataclass(frozen=True)
class GuardedLinkWrite:
    """One relationship key's links from an anchor, written under the guard's rule.

    Attributes:
        far_uids: the far ends, distinct. Each must be an entity carrying one of
            ``far_labels``, owned by one of the anchor's owners or by nobody and
            published — or the write writes nothing.
        relationship: the edge type.
        anchor_is_source: ``True`` writes ``(anchor)-[:T]->(far)``, ``False``
            ``(far)-[:T]->(anchor)``.
        far_labels: the kinds the far ends may be.
        properties: set on every edge written.
        replace: delete the anchor's other edges of this type in the same statement —
            the key's links become exactly ``far_uids`` (none, for an empty list).
        replace_label: with ``replace``, only edges to a node of this kind are
            deleted; ``None`` deletes every other edge of the type.
    """

    far_uids: tuple[str, ...]
    relationship: RelationshipName
    anchor_is_source: bool
    far_labels: frozenset[str]
    properties: Neo4jProperties | None = None
    replace: bool = False
    replace_label: NeoLabel | None = None


@dataclass(frozen=True)
class GuardedLinkOutcome:
    """What a guarded link write did.

    Attributes:
        refused_uid: ``None`` when every write landed. Otherwise the first uid the
            write refused — the anchor's own uid when it names no entity — and
            nothing was written: the writes share one transaction.
        anchor_owners: the anchor's owners as the write read them; empty for a
            refusal and for an anchor nobody owns.
    """

    refused_uid: str | None
    anchor_owners: frozenset[str]

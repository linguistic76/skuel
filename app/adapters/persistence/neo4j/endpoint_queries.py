"""
Endpoint Queries — what a node IS and who OWNS it, for many uids at once
========================================================================

The two batched reads the link-edge guard (``core/services/mixins/link_edge_guard.py``)
decides with. Two backends serve them — the domain backends
(``_RelationshipCrudMixin.get_node_labels_batch`` / ``get_owner_uids_batch``) and the
ingestion write backend, whose vault door admits frontmatter targets by the same
rule — so the Cypher lives here once: a second copy of "who owns this node" is how a
check that reads one spelling of ownership drifts from one that reads three.

Both exclude ``:Content`` — the chunk store's shadow node shares its entity's uid (G13).
"""

from __future__ import annotations

from typing import Final

# uid -> labels; a uid that names no node is absent from the result.
NODE_LABELS_BATCH_QUERY: Final = """
UNWIND $uids AS uid
MATCH (n {uid: uid}) WHERE NOT n:Content
RETURN uid, labels(n) AS labels
"""

# uid -> owning user uids, for owned nodes only. Ownership is spelled three ways in
# this graph — ``n.user_uid`` (UserOwnedEntity), ``n.owner_uid`` (Exercise, Group) and
# ``(:User)-[:OWNS]->(n)`` — and all three are read. A node with none of them (shared
# curriculum) is absent from the result, which is what lets a caller say "must match if
# owned, allowed if shared" without listing which types are user-owned.
OWNER_UIDS_BATCH_QUERY: Final = """
UNWIND $uids AS uid
MATCH (n {uid: uid}) WHERE NOT n:Content
OPTIONAL MATCH (owner:User)-[:OWNS]->(n)
WITH uid, n, collect(DISTINCT owner.uid) AS owns_uids
WITH uid, [o IN owns_uids + [n.user_uid, n.owner_uid] WHERE o IS NOT NULL] AS owners
WHERE size(owners) > 0
RETURN uid, owners
"""

__all__ = ["NODE_LABELS_BATCH_QUERY", "OWNER_UIDS_BATCH_QUERY"]

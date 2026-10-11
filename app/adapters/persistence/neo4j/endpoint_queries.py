"""
Endpoint Queries — what a node IS, who OWNS it, whether it is PUBLISHED, and the write
==================================================================================

The three batched reads the link-edge guard (``core/services/mixins/link_edge_guard.py``)
decides with, and the write that re-asserts its rule. Two backends serve the reads —
the domain backends (``_RelationshipCrudMixin.get_node_labels_batch`` /
``get_owner_uids_batch`` / ``get_published_uids_batch``) and the ingestion write
backend, whose vault door admits frontmatter targets by the same rule — so the Cypher
lives here once: a second copy of "who owns this node" is how a check that reads one
spelling of ownership drifts from one that reads three.

All of them exclude ``:Content`` — the chunk store's shadow node shares its entity's uid
(G13).

A uid is bound through ``build_uid_anchor``: one index seek per label a uid can name —
``:Entity``, ``:User``, ``:Group`` — instead of a label-less match, which scans every
node in the graph once per uid. The labels read still sees a User or a Group, so a
link door handed one refuses it as the wrong kind; a uid naming a node of any other
label (a session, a log row) reads as no node, which every caller refuses alike.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from adapters.persistence.neo4j.query.cypher import build_publication_clause
from adapters.persistence.neo4j.query.cypher._helpers import validate_identifier
from adapters.persistence.neo4j.query.cypher.crud_queries import build_owner_uids_expression
from core.models.enums.neo_labels import NeoLabel

if TYPE_CHECKING:
    from core.models.relationship_names import RelationshipName

# The labels a uid is looked up under. :Entity is every domain node; :User and :Group
# are the uid-bearing nodes outside it that an edge joins to an entity.
_UID_LABELS: Final = (NeoLabel.ENTITY, NeoLabel.USER, NeoLabel.GROUP)


def build_uid_anchor(alias: str, uid_expression: str, own_label: NeoLabel | None = None) -> str:
    """A ``CALL`` subquery binding ``alias`` to the node ``uid_expression`` names.

    One ``UNION`` branch per label in ``_UID_LABELS``, plus ``own_label`` when it is
    not one of them (a backend whose nodes live outside ``:Entity`` reads its own),
    so each branch is an index seek. Binds no row when the uid names none of them.

    Args:
        alias: the variable the node is bound to after the subquery.
        uid_expression: ``$uid`` for a parameter, or a variable already in scope —
            which the subquery imports.
        own_label: the calling backend's label.
    """
    validate_identifier(alias, context="anchor alias")
    labels = list(_UID_LABELS)
    if own_label is not None and own_label not in labels:
        labels.append(own_label)
    scope = "" if uid_expression.startswith("$") else uid_expression
    if scope:
        validate_identifier(scope, context="uid variable")
    branches = "\n    UNION\n".join(
        f"    MATCH ({alias}:{label.value} {{uid: {uid_expression}}}) "
        f"WHERE NOT {alias}:{NeoLabel.CONTENT.value} RETURN {alias}"
        for label in labels
    )
    return f"CALL ({scope}) {{\n{branches}\n}}"


# uid -> labels; a uid that names no node is absent from the result.
NODE_LABELS_BATCH_QUERY: Final = f"""
UNWIND $uids AS uid
{build_uid_anchor("n", "uid")}
RETURN uid, labels(n) AS labels
"""

# uid -> owning user uids, for owned nodes only. Ownership is spelled three ways in
# this graph — ``n.user_uid`` (UserOwnedEntity), ``n.owner_uid`` (Exercise, Group) and
# ``(:User)-[:OWNS]->(n)`` — and all three are read. A node with none of them (shared
# curriculum) is absent from the result, which is what lets a caller say "must match if
# owned, allowed if shared" without listing which types are user-owned.
OWNER_UIDS_BATCH_QUERY: Final = f"""
UNWIND $uids AS uid
{build_uid_anchor("n", "uid")}
OPTIONAL MATCH (owner:{NeoLabel.USER.value})-[:OWNS]->(n)
WITH uid, n, collect(DISTINCT owner.uid) AS owns_uids
WITH uid, [o IN owns_uids + [n.user_uid, n.owner_uid] WHERE o IS NOT NULL] AS owners
WHERE size(owners) > 0
RETURN uid, owners
"""

# uid -> present when the node passes THE publication predicate; a uid that names no
# node, or a node explicitly marked draft, is absent. Absence is the refusal, so a
# reader that answers nothing admits nothing. The guard asks it of unowned far ends
# only: publication is a property of shared content, not of a user's own entities.
# Bound to ``:Entity`` (the uid index): every label a link door admits is an Entity
# label, so a node outside it fails the kind check first — and reads unpublished if
# it ever did not, which refuses rather than admits. The guarded write below composes
# the same clause over its far node.
_PUBLISHED_CLAUSE, PUBLISHED_UIDS_BATCH_PARAMS = build_publication_clause("n")
PUBLISHED_UIDS_BATCH_QUERY: Final = f"""
UNWIND $uids AS uid
MATCH (n:Entity {{uid: uid}}) WHERE NOT n:Content AND {_PUBLISHED_CLAUSE}
RETURN DISTINCT uid
"""


def build_guarded_link_query(
    relationship: RelationshipName,
    *,
    anchor_is_source: bool,
    replace: bool,
    replace_label: NeoLabel | None,
) -> str:
    """The statement that writes an anchor's links and re-asserts the guard's rule.

    The link-edge guard admits a far end in reads taken before the write; this
    statement reads the same facts again under the write — after taking each node's
    write lock (``SET x.uid = x.uid`` writes nothing and is the pure-Cypher lock; reads
    are read-committed and lock-free, so without it a change committed between this
    statement's read and its ``MERGE`` would still be linked). A writer that re-owns,
    unpublishes or deletes the node waits for this transaction, or this one waits for
    it and reads what it committed. Every far uid must name an
    ``:Entity`` carrying one of ``$far_labels`` that is owned by one of the anchor's
    owners, or owned by nobody and published — the rule ``_refusal_reason`` states. A
    far end deleted, re-owned or unpublished since its admission fails it, and the
    statement then writes NOTHING: every far end passes, or no edge is merged and none
    is deleted.

    With ``replace`` the anchor's other edges of this type — to a node carrying
    ``replace_label`` when one is given — are deleted in the same statement, so a
    replacement never leaves the anchor without its old link and without the new one.

    Parameters: ``$anchor_uid``, ``$far_uids`` (distinct), ``$far_labels``,
    ``$properties`` and ``PUBLISHED_UIDS_BATCH_PARAMS``. Returns one row —
    ``admitted`` (the far uids that passed) and ``anchor_owners`` — or none when the
    anchor names no entity.
    """
    rel = relationship.value
    link = f"(a)-[r:{rel}]->(f)" if anchor_is_source else f"(f)-[r:{rel}]->(a)"
    kind = f":{replace_label.value}" if replace_label is not None else ""
    stale = f"(a)-[old:{rel}]->(x{kind})" if anchor_is_source else f"(x{kind})-[old:{rel}]->(a)"
    replace_line = (
        f"FOREACH (gone IN [{stale} WHERE NOT x IN fars | old] | DELETE gone)" if replace else ""
    )
    return f"""
MATCH (a:{NeoLabel.ENTITY.value} {{uid: $anchor_uid}}) WHERE NOT a:{NeoLabel.CONTENT.value}
SET a.uid = a.uid
WITH a, {build_owner_uids_expression("a")} AS anchor_owners
CALL (a, anchor_owners) {{
    UNWIND $far_uids AS far_uid
    MATCH (n:{NeoLabel.ENTITY.value} {{uid: far_uid}})
    WHERE NOT n:{NeoLabel.CONTENT.value} AND n <> a
      AND any(label IN labels(n) WHERE label IN $far_labels)
    SET n.uid = n.uid
    WITH n, {build_owner_uids_expression("n")} AS far_owners
    WHERE CASE WHEN size(far_owners) = 0 THEN {_PUBLISHED_CLAUSE}
               ELSE any(o IN far_owners WHERE o IN anchor_owners) END
    RETURN collect(n) AS fars
}}
CALL (a, fars) {{
    WITH a, fars WHERE size(fars) = size($far_uids)
    {replace_line}
    FOREACH (f IN fars | MERGE {link} SET r += $properties)
}}
RETURN [n IN fars | n.uid] AS admitted, anchor_owners
"""


__all__ = [
    "NODE_LABELS_BATCH_QUERY",
    "OWNER_UIDS_BATCH_QUERY",
    "PUBLISHED_UIDS_BATCH_PARAMS",
    "PUBLISHED_UIDS_BATCH_QUERY",
    "build_guarded_link_query",
    "build_uid_anchor",
]

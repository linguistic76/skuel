"""
Template Attachment Backend
===========================

PS↔Activity-Template edge operations (``HAS_*_TEMPLATE``), below the hexagonal
boundary. Parameterized Cypher run via ``Neo4jQueryExecutor``; ``edge_name`` is a
typed ``RelationshipName`` (one of the ``HAS_*_TEMPLATE`` members) and
``template_label`` a typed ``NeoLabel`` (the matching template label), both supplied
by the calling template service — the enums are the injection-safety guarantee, so
MyPy rejects raw strings at the interpolation seam.

Every statement binds both ends by kind: the source is a ``:PathStep`` and the far
end carries ``template_label``. A uid that names nothing and a node of the wrong kind
match alike — no row — so the write is its own admission and the read never returns a
node that is not this kind of template.

Implements ``TemplateAttachmentOperations`` (``core/ports/template_protocols.py``).
The 6 Activity Template services (``core/services/templates``) delegate their
attach/detach/list Cypher here and keep their guard + result-shaping logic.

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.enums.neo_labels import NeoLabel
    from core.models.relationship_names import RelationshipName


class TemplateAttachmentBackend:
    """Cypher backend for PS↔template edge attach/detach/list operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def attach(
        self,
        ps_uid: str,
        template_uid: str,
        edge_name: RelationshipName,
        template_label: NeoLabel,
    ) -> Result[list[dict[str, Any]]]:
        """MERGE the ``edge_name`` edge between PS and template (idempotent).

        No row when either end is missing or not its kind — nothing is written.
        """
        # :Entity — a PathStep's :Content shadow shares its uid; an unlabeled
        # MERGE would attach the template to both nodes (G13).
        query = (
            "MATCH (ps:Entity:PathStep {uid: $ps_uid}), "
            f"(t:Entity:{template_label} {{uid: $template_uid}}) "
            f"MERGE (ps)-[:{edge_name}]->(t) "
            "RETURN ps.uid AS ps_uid, t.uid AS t_uid"
        )
        return await self._executor.execute_write(
            query=query,
            params={"ps_uid": ps_uid, "template_uid": template_uid},
            operation="attach_template_to_pathstep",
        )

    async def detach(
        self,
        ps_uid: str,
        template_uid: str,
        edge_name: RelationshipName,
        template_label: NeoLabel,
    ) -> Result[list[dict[str, Any]]]:
        """DELETE the ``edge_name`` edge; returns one ``removed`` count row.

        No row when either end is missing or not its kind; ``removed: 0`` when both
        are and no edge joins them.
        """
        query = (
            "MATCH (ps:Entity:PathStep {uid: $ps_uid}), "
            f"(t:Entity:{template_label} {{uid: $template_uid}}) "
            f"OPTIONAL MATCH (ps)-[r:{edge_name}]->(t) "
            # Grouped by the matched pair, so no match returns no row — an ungrouped
            # count() returns one row even over nothing.
            "DELETE r RETURN ps.uid AS ps_uid, count(r) AS removed"
        )
        return await self._executor.execute_write(
            query=query,
            params={"ps_uid": ps_uid, "template_uid": template_uid},
            operation="detach_template_from_pathstep",
        )

    async def list_for_pathstep(
        self, ps_uid: str, edge_name: RelationshipName, template_label: NeoLabel
    ) -> Result[list[dict[str, Any]]]:
        """Return ``props`` rows for the ``template_label`` nodes ``ps_uid`` attaches."""
        query = (
            "MATCH (ps:Entity:PathStep {uid: $ps_uid})"
            f"-[:{edge_name}]->(t:Entity:{template_label}) "
            "RETURN properties(t) AS props "
            "ORDER BY datetime(t.created_at)"
        )
        return await self._executor.execute(
            query=query,
            params={"ps_uid": ps_uid},
            operation="list_templates_for_pathstep",
        )

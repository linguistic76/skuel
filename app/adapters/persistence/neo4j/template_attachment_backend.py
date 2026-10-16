"""
Template Attachment Backend
===========================

The PS→Activity-Template edge read (``HAS_*_TEMPLATE``), below the hexagonal
boundary. Parameterized Cypher run via ``Neo4jQueryExecutor``; ``edge_name`` is a
typed ``RelationshipName`` (one of the ``HAS_*_TEMPLATE`` members) and
``template_label`` a typed ``NeoLabel`` (the matching template label), both supplied
by the calling template service — the enums are the injection-safety guarantee, so
MyPy rejects raw strings at the interpolation seam.

The statement binds both ends by kind: the source is a ``:PathStep`` and the far end
carries ``template_label``, so the read never returns a node that is not this kind of
template, whatever an edge points at. The edges themselves are written only by the
content-vault sync (a PathStep's ``{domain}_template_uids:`` frontmatter).

Implements ``TemplateAttachmentOperations`` (``core/ports/template_protocols.py``).
The 6 Activity Template services (``core/services/templates``) delegate their read
here and keep the result shaping.

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
    """Cypher backend for the PS→template edge read."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

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

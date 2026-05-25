"""
Template Attachment Backend
===========================

PS↔Activity-Template edge operations (``HAS_*_TEMPLATE``), below the hexagonal
boundary. Parameterized Cypher run via ``Neo4jQueryExecutor``; ``edge_name`` is a
typed ``RelationshipName`` (one of the ``HAS_*_TEMPLATE`` members) supplied by the
calling template service — the enum is the injection-safety guarantee, so MyPy
rejects raw strings at the interpolation seam.

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
    from core.models.relationship_names import RelationshipName


class TemplateAttachmentBackend:
    """Cypher backend for PS↔template edge attach/detach/list operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def attach(
        self, ps_uid: str, template_uid: str, edge_name: RelationshipName
    ) -> Result[list[dict[str, Any]]]:
        """MERGE the ``edge_name`` edge between PS and template (idempotent)."""
        query = (
            "MATCH (ps {uid: $ps_uid}), (t {uid: $template_uid}) "
            f"MERGE (ps)-[:{edge_name}]->(t) "
            "RETURN ps.uid AS ps_uid, t.uid AS t_uid"
        )
        return await self._executor.execute_write(
            query=query,
            params={"ps_uid": ps_uid, "template_uid": template_uid},
            operation="attach_template_to_pathstep",
        )

    async def detach(
        self, ps_uid: str, template_uid: str, edge_name: RelationshipName
    ) -> Result[list[dict[str, Any]]]:
        """DELETE the ``edge_name`` edge; returns a ``removed`` count row."""
        query = (
            "MATCH (ps {uid: $ps_uid})-[r:"
            f"{edge_name}"
            "]->(t {uid: $template_uid}) "
            "DELETE r RETURN count(r) AS removed"
        )
        return await self._executor.execute_write(
            query=query,
            params={"ps_uid": ps_uid, "template_uid": template_uid},
            operation="detach_template_from_pathstep",
        )

    async def list_for_pathstep(
        self, ps_uid: str, edge_name: RelationshipName
    ) -> Result[list[dict[str, Any]]]:
        """Return ``props`` rows for templates attached to ``ps_uid`` via ``edge_name``."""
        query = (
            "MATCH (ps {uid: $ps_uid})-[:"
            f"{edge_name}"
            "]->(t) "
            "RETURN properties(t) AS props "
            "ORDER BY t.created_at"
        )
        return await self._executor.execute(
            query=query,
            params={"ps_uid": ps_uid},
            operation="list_templates_for_pathstep",
        )

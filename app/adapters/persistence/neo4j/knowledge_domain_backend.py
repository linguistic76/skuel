"""
Knowledge Domain Backend
========================

Neo4j adapter for KnowledgeDomain taxonomy queries.

Implements: KnowledgeDomainBackendOperations protocol
Consumer: KnowledgeDomainService
"""

from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger(__name__)


class KnowledgeDomainBackend:
    """Neo4j backend for KnowledgeDomain taxonomy queries."""

    def __init__(self, executor: "QueryExecutor") -> None:
        self.executor = executor

    async def get_all_domains(self) -> Result[list[dict[str, Any]]]:
        """List all KnowledgeDomain nodes with their Ku counts."""
        query = f"""
        MATCH (d:{NeoLabel.KNOWLEDGE_DOMAIN})
        OPTIONAL MATCH (ku:{NeoLabel.KU})-[:{RelationshipName.IN_DOMAIN}]->(d)
        RETURN d.uid AS uid, count(ku) AS ku_count
        ORDER BY d.uid
        """
        try:
            return await self.executor.execute_query(query)
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(Errors.database(operation="get_all_domains", message=str(e)))

    async def get_ku_uids_in_domain(self, domain_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all Ku UIDs belonging to a given domain."""
        query = f"""
        MATCH (ku:{NeoLabel.KU})-[:{RelationshipName.IN_DOMAIN}]->(d:{NeoLabel.KNOWLEDGE_DOMAIN} {{uid: $domain_uid}})
        RETURN ku.uid AS uid
        ORDER BY ku.uid
        """
        try:
            return await self.executor.execute_query(query, {"domain_uid": domain_uid})
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(
                    operation="get_ku_uids_in_domain",
                    message=f"Failed to get Kus in domain '{domain_uid}': {e}",
                )
            )

    async def get_domains_for_ku(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all domains a Ku belongs to."""
        query = f"""
        MATCH (ku:{NeoLabel.KU} {{uid: $ku_uid}})-[:{RelationshipName.IN_DOMAIN}]->(d:{NeoLabel.KNOWLEDGE_DOMAIN})
        RETURN d.uid AS uid
        ORDER BY d.uid
        """
        try:
            return await self.executor.execute_query(query, {"ku_uid": ku_uid})
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(
                    operation="get_domains_for_ku",
                    message=f"Failed to get domains for Ku '{ku_uid}': {e}",
                )
            )

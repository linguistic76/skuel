"""
KnowledgeDomainService — World-Layer Domain Taxonomy
=====================================================

Read-only service for KnowledgeDomain nodes — the stable taxonomy that
groups Kus into semantic domains (e.g., self_awareness, nervous_system).

KnowledgeDomain is a World Layer node (exists independently of any user).
Nodes are created at ingestion time via the `domains:` frontmatter field in
Ku YAML files. This service makes those nodes queryable from Python.

Architecture:
    KnowledgeDomain nodes live outside the Entity multi-label pattern.
    They are plain `:KnowledgeDomain` nodes with `uid` as their identity.
    Relationship: `(Ku)-[:IN_DOMAIN]->(KnowledgeDomain)` (RelationshipName.IN_DOMAIN)

See: /docs/architecture/ONTOLOGY_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.base_protocols import QueryExecutor

logger = get_logger("skuel.services.knowledge_domain")


@dataclass(frozen=True)
class KnowledgeDomain:
    """
    Domain taxonomy node — groups Kus into a stable semantic domain.

    Domains are stable identifiers for clusters of related knowledge
    (e.g., kd.self_awareness, kd.nervous_system, kd.relationships).
    They are taxonomy objects: they classify, they do not carry content.
    """

    uid: str
    title: str
    ku_count: int = 0


class KnowledgeDomainService:
    """
    Read-only service for KnowledgeDomain taxonomy nodes.

    Provides queryable access to KnowledgeDomain nodes that already
    exist in Neo4j (created by the Ku ingestion pipeline from the
    `domains:` frontmatter field in Ku YAML files).

    Usage:
        domains = await services.knowledge_domains.get_all_domains()
        kus = await services.knowledge_domains.get_ku_uids_in_domain("kd.self_awareness")
    """

    def __init__(self, executor: QueryExecutor) -> None:
        """
        Args:
            executor: QueryExecutor (Neo4jQueryExecutor or any LowLevelOperations impl)
        """
        self.executor = executor
        logger.info("KnowledgeDomainService initialized")

    async def get_all_domains(self) -> Result[list[KnowledgeDomain]]:
        """
        List all KnowledgeDomain nodes with their Ku counts.

        Returns domains sorted alphabetically by uid.
        """
        query = f"""
        MATCH (d:{NeoLabel.KNOWLEDGE_DOMAIN})
        OPTIONAL MATCH (ku:{NeoLabel.KU})-[:{RelationshipName.IN_DOMAIN}]->(d)
        RETURN d.uid AS uid, count(ku) AS ku_count
        ORDER BY d.uid
        """
        try:
            result = await self.executor.execute_query(query)
            if result.is_error:
                return Result.fail(result)
            rows: list[dict[str, Any]] = result.value
            domains = [
                KnowledgeDomain(
                    uid=row["uid"],
                    title=row["uid"],  # uid IS the title until domain metadata ingestion exists
                    ku_count=int(row["ku_count"]),
                )
                for row in rows
                if row.get("uid")
            ]
            return Result.ok(domains)
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(
                    operation="get_all_domains", message=f"Failed to list knowledge domains: {e}"
                )
            )

    async def get_ku_uids_in_domain(self, domain_uid: str) -> Result[list[str]]:
        """
        Get all Ku UIDs that belong to a given domain.

        Args:
            domain_uid: The KnowledgeDomain uid (e.g., "kd.self_awareness")

        Returns:
            List of Ku UIDs in this domain, sorted alphabetically.
        """
        query = f"""
        MATCH (ku:{NeoLabel.KU})-[:{RelationshipName.IN_DOMAIN}]->(d:{NeoLabel.KNOWLEDGE_DOMAIN} {{uid: $domain_uid}})
        RETURN ku.uid AS uid
        ORDER BY ku.uid
        """
        try:
            result = await self.executor.execute_query(query, {"domain_uid": domain_uid})
            if result.is_error:
                return Result.fail(result)
            rows: list[dict[str, Any]] = result.value
            return Result.ok([row["uid"] for row in rows if row.get("uid")])
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(
                    operation="get_ku_uids_in_domain",
                    message=f"Failed to get Kus in domain '{domain_uid}': {e}",
                )
            )

    async def get_domain_for_ku(self, ku_uid: str) -> Result[list[KnowledgeDomain]]:
        """
        Get all domains a Ku belongs to.

        Args:
            ku_uid: The Ku uid

        Returns:
            List of KnowledgeDomain nodes this Ku is classified under.
        """
        query = f"""
        MATCH (ku:{NeoLabel.KU} {{uid: $ku_uid}})-[:{RelationshipName.IN_DOMAIN}]->(d:{NeoLabel.KNOWLEDGE_DOMAIN})
        RETURN d.uid AS uid
        ORDER BY d.uid
        """
        try:
            result = await self.executor.execute_query(query, {"ku_uid": ku_uid})
            if result.is_error:
                return Result.fail(result)
            rows: list[dict[str, Any]] = result.value
            domains = [
                KnowledgeDomain(uid=row["uid"], title=row["uid"]) for row in rows if row.get("uid")
            ]
            return Result.ok(domains)
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database(
                    operation="get_domain_for_ku",
                    message=f"Failed to get domains for Ku '{ku_uid}': {e}",
                )
            )

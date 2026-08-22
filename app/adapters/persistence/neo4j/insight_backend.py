"""
Insight Backend
===============

Backend for insight graph node CRUD operations.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Migrates 10 execute_query calls from InsightStore.

Protocol: core/ports/insight_protocols.py (InsightBackendOperations) — InsightStore
types its handle against that port, never against this class (SKUEL023 / ADR-044).

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


class InsightBackend:
    """Backend for insight persistence operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ========================================================================
    # CRUD
    # ========================================================================

    async def create_insight(self, params: dict[str, Any]) -> Result[list[dict[str, Any]]]:
        """Create an Insight node with User and Entity relationships."""
        return await self._executor.execute_query(
            """
            // Create the Insight node — JSON fields serialized via json.dumps()
            // because this is custom Cypher (not routed through UniversalNeo4jBackend)
            CREATE (i:Insight {
                uid: $uid,
                user_uid: $user_uid,
                insight_type: $insight_type,
                domain: $domain,
                title: $title,
                description: $description,
                confidence: $confidence,
                impact: $impact,
                entity_uid: $entity_uid,
                related_entities: $related_entities,
                recommended_actions: $recommended_actions,
                supporting_data: $supporting_data,
                created_at: datetime($created_at),
                expires_at: $expires_at,
                dismissed: $dismissed,
                actioned: $actioned
            })

            // Create relationship to User
            WITH i
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:HAS_INSIGHT]->(i)

            // Create relationship to primary entity if it exists
            WITH i
            OPTIONAL MATCH (e:Entity {uid: $entity_uid})
            FOREACH (_ IN CASE WHEN e IS NOT NULL THEN [1] ELSE [] END |
                CREATE (i)-[:ABOUT_ENTITY]->(e)
            )

            RETURN i.uid as uid
            """,
            params,
        )

    async def get(self, uid: str, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get a single insight by UID, only when owned by the requesting user.

        Owner-scoped in the MATCH itself (ADR-085 G6 — the shape
        ``get_insights_for_entity`` already uses): a foreign UID matches zero
        rows, so not-found and not-yours are indistinguishable.
        """
        return await self._executor.execute_query(
            """
            MATCH (i:Insight {uid: $uid, user_uid: $user_uid})
            RETURN i
            """,
            {"uid": uid, "user_uid": user_uid},
        )

    async def get_active_insights(
        self,
        user_uid: str,
        domain: str | None,
        limit: int,
    ) -> Result[list[dict[str, Any]]]:
        """Get active (non-dismissed, non-actioned, non-expired) insights for a user."""
        domain_filter = "AND i.domain = $domain" if domain else ""

        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:HAS_INSIGHT]->(i:Insight)
        WHERE i.dismissed = false
          AND i.actioned = false
          AND (i.expires_at IS NULL OR datetime(i.expires_at) > datetime())
          {domain_filter}
        RETURN i
        ORDER BY
            CASE i.impact
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'medium' THEN 2
                ELSE 1
            END DESC,
            i.confidence DESC,
            i.created_at DESC
        LIMIT $limit
        """

        params: dict[str, Any] = {"user_uid": user_uid, "limit": limit}
        if domain:
            params["domain"] = domain

        return await self._executor.execute_query(query, params)

    async def get_insights_for_entity(
        self,
        entity_uid: str,
        user_uid: str,
        include_dismissed: bool,
    ) -> Result[list[dict[str, Any]]]:
        """Get insights related to a specific entity."""
        dismissed_filter = "" if include_dismissed else "AND i.dismissed = false"

        query = f"""
        MATCH (i:Insight {{entity_uid: $entity_uid, user_uid: $user_uid}})
        WHERE i.actioned = false
          AND (i.expires_at IS NULL OR datetime(i.expires_at) > datetime())
          {dismissed_filter}
        RETURN i
        ORDER BY i.created_at DESC
        """

        return await self._executor.execute_query(
            query, {"entity_uid": entity_uid, "user_uid": user_uid}
        )

    # ========================================================================
    # Status Updates
    # ========================================================================

    async def dismiss_insight(
        self, uid: str, user_uid: str, notes: str
    ) -> Result[list[dict[str, Any]]]:
        """Mark an insight as dismissed."""
        return await self._executor.execute_query(
            """
            MATCH (i:Insight {uid: $uid, user_uid: $user_uid})
            SET i.dismissed = true,
                i.dismissed_at = datetime(),
                i.dismissed_notes = $notes
            RETURN i.uid as uid
            """,
            {"uid": uid, "user_uid": user_uid, "notes": notes},
        )

    async def mark_actioned(
        self, uid: str, user_uid: str, notes: str
    ) -> Result[list[dict[str, Any]]]:
        """Mark an insight as actioned."""
        return await self._executor.execute_query(
            """
            MATCH (i:Insight {uid: $uid, user_uid: $user_uid})
            SET i.actioned = true,
                i.actioned_at = datetime(),
                i.actioned_notes = $notes
            RETURN i.uid as uid
            """,
            {"uid": uid, "user_uid": user_uid, "notes": notes},
        )

    # ========================================================================
    # Maintenance
    # ========================================================================

    async def cleanup_expired(self) -> Result[list[dict[str, Any]]]:
        """Delete expired insights from the database."""
        return await self._executor.execute_query(
            """
            MATCH (i:Insight)
            WHERE i.expires_at IS NOT NULL AND datetime(i.expires_at) < datetime()
            DETACH DELETE i
            RETURN count(i) as deleted_count
            """,
        )

    # ========================================================================
    # Query / Analytics
    # ========================================================================

    async def get_insight_history(
        self,
        user_uid: str,
        history_type: str,
        limit: int,
    ) -> Result[list[dict[str, Any]]]:
        """Get dismissed or actioned insights for history page."""
        if history_type == "dismissed":
            where_clause = "AND i.dismissed = true"
        elif history_type == "actioned":
            where_clause = "AND i.actioned = true"
        else:  # "all"
            where_clause = "AND (i.dismissed = true OR i.actioned = true)"

        query = f"""
        MATCH (i:Insight {{user_uid: $user_uid}})
        WHERE true {where_clause}
        RETURN i
        ORDER BY coalesce(i.dismissed_at, i.actioned_at) DESC
        LIMIT $limit
        """

        return await self._executor.execute_query(query, {"user_uid": user_uid, "limit": limit})

    async def get_insight_stats(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get statistics about a user's insights."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:HAS_INSIGHT]->(i:Insight)
            RETURN
                count(i) as total_insights,
                count(CASE WHEN i.dismissed = false AND i.actioned = false
                           AND (i.expires_at IS NULL OR datetime(i.expires_at) > datetime())
                      THEN 1 END) as active_insights,
                count(CASE WHEN i.dismissed = true THEN 1 END) as dismissed_insights,
                count(CASE WHEN i.actioned = true THEN 1 END) as actioned_insights,
                count(CASE WHEN i.impact = 'critical' THEN 1 END) as critical_insights,
                count(CASE WHEN i.impact = 'high' THEN 1 END) as high_insights,
                collect(DISTINCT i.domain) as domains
            """,
            {"user_uid": user_uid},
        )

    async def get_insight_counts_by_domain(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get count of active insights grouped by domain."""
        return await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:HAS_INSIGHT]->(i:Insight)
            WHERE i.dismissed = false
              AND i.actioned = false
              AND (i.expires_at IS NULL OR datetime(i.expires_at) > datetime())
            RETURN i.domain as domain, count(i) as count
            ORDER BY count DESC
            """,
            {"user_uid": user_uid},
        )

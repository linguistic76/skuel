"""
Insight Backend
===============

Backend for insight graph node CRUD operations.
Does NOT extend UniversalNeo4jBackend — takes a Neo4jQueryExecutor directly.

Every Cypher statement InsightStore runs lives here.

Protocol: core/ports/insight_protocols.py (InsightBackendOperations) — InsightStore
types its handle against that port, never against this class (SKUEL023 / ADR-044).

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.insight.persisted_insight import ActiveInsightFilter, InsightField
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


# An active insight: neither dismissed nor actioned, and not past its expiry.
# This backend's reads of a learner's active set — the page, its count, the stats and
# the chart counts — and the bulk dismiss over it use this one rule.
_ACTIVE_INSIGHT = """i.dismissed = false
          AND i.actioned = false
          AND (i.expires_at IS NULL OR datetime(i.expires_at) > datetime())"""

# A learner's active insights that an ActiveInsightFilter selects. Each filter is a
# parameter, off when null, so the page and its count share one statement shape.
_ACTIVE_INSIGHT_MATCHING = f"""MATCH (u:User {{uid: $user_uid}})-[:HAS_INSIGHT]->(i:Insight)
        WHERE {_ACTIVE_INSIGHT}
          AND ($domain IS NULL OR i.domain = $domain)
          AND ($impact IS NULL OR i.impact = $impact)
          AND ($insight_type IS NULL OR i.insight_type = $insight_type)
          AND ($search IS NULL
               OR toLower(i.title) CONTAINS toLower($search)
               OR toLower(coalesce(i.description, '')) CONTAINS toLower($search))"""


def _matching_params(user_uid: str, match: ActiveInsightFilter) -> dict[str, str | None]:
    """The parameters of ``_ACTIVE_INSIGHT_MATCHING`` — a blank search is no filter."""
    return {
        "user_uid": user_uid,
        "domain": match.domain.value if match.domain else None,
        "impact": match.impact.value if match.impact else None,
        "insight_type": match.insight_type.value if match.insight_type else None,
        "search": match.search or None,
    }


# The stored property behind each field — the whitelist that keeps a caller's
# value out of the query text.
_FIELD_PROPERTY: dict[InsightField, str] = {
    InsightField.IMPACT: "impact",
    InsightField.DOMAIN: "domain",
    InsightField.INSIGHT_TYPE: "insight_type",
}


class InsightBackend:
    """Backend for insight persistence operations."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    # ========================================================================
    # CRUD
    # ========================================================================

    async def create_insight(self, params: dict[str, Any]) -> Result[list[dict[str, Any]]]:
        """Create an Insight node with User and Entity relationships.

        ``created_at`` and ``expires_at`` arrive as ISO strings and are stored as
        natives through ``datetime()``; a null ``expires_at`` stays null, so the
        property is absent and the insight never expires.
        """
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
                expires_at: datetime($expires_at),
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
        match: ActiveInsightFilter,
        limit: int,
        offset: int,
    ) -> Result[list[dict[str, Any]]]:
        """One page of a user's active insights that ``match`` selects.

        Ordered by impact, then confidence, then newest first; the uid breaks the
        last tie, so consecutive pages neither repeat nor skip an insight.
        """
        query = f"""
        {_ACTIVE_INSIGHT_MATCHING}
        RETURN i
        ORDER BY
            CASE i.impact
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'medium' THEN 2
                ELSE 1
            END DESC,
            i.confidence DESC,
            datetime(i.created_at) DESC,
            i.uid
        SKIP $offset
        LIMIT $limit
        """
        params: dict[str, str | int | None] = {
            **_matching_params(user_uid, match),
            "offset": offset,
            "limit": limit,
        }
        return await self._executor.execute_query(query, params)

    async def count_active_insights(
        self, user_uid: str, match: ActiveInsightFilter
    ) -> Result[list[dict[str, Any]]]:
        """Count every active insight of a user that ``match`` selects — no row cap.

        One row always: an ungrouped count answers zero when nothing matches.
        """
        return await self._executor.execute_query(
            f"""
            {_ACTIVE_INSIGHT_MATCHING}
            RETURN count(i) AS total
            """,
            _matching_params(user_uid, match),
        )

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
        ORDER BY datetime(i.created_at) DESC
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
        ORDER BY datetime(coalesce(i.dismissed_at, i.actioned_at)) DESC
        LIMIT $limit
        """

        return await self._executor.execute_query(query, {"user_uid": user_uid, "limit": limit})

    async def get_insight_stats(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        """Get statistics about a user's insights.

        The total, dismissed and actioned counts and the domains are all-time; the
        active, critical and high counts are of the active set.
        """
        return await self._executor.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:HAS_INSIGHT]->(i:Insight)
            RETURN
                count(i) as total_insights,
                count(CASE WHEN {_ACTIVE_INSIGHT}
                      THEN 1 END) as active_insights,
                count(CASE WHEN i.dismissed = true THEN 1 END) as dismissed_insights,
                count(CASE WHEN i.actioned = true THEN 1 END) as actioned_insights,
                count(CASE WHEN {_ACTIVE_INSIGHT} AND i.impact = 'critical'
                      THEN 1 END) as critical_insights,
                count(CASE WHEN {_ACTIVE_INSIGHT} AND i.impact = 'high'
                      THEN 1 END) as high_insights,
                collect(DISTINCT i.domain) as domains
            """,
            {"user_uid": user_uid},
        )

    async def count_active_insights_by(
        self, user_uid: str, field: InsightField
    ) -> Result[list[dict[str, Any]]]:
        """Count a user's whole active set, one row per value of ``field``.

        A grouped count has no row cap, so a learner's figures are never cut
        short by a page.
        """
        prop = _FIELD_PROPERTY[field]
        return await self._executor.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:HAS_INSIGHT]->(i:Insight)
            WHERE {_ACTIVE_INSIGHT}
            RETURN i.{prop} AS value, count(i) AS count
            """,
            {"user_uid": user_uid},
        )

    async def dismiss_active_insights_matching(
        self, user_uid: str, field: InsightField, value: str
    ) -> Result[list[dict[str, Any]]]:
        """Dismiss every active insight of a user whose ``field`` equals ``value``.

        One statement: every match is dismissed or none is, and the count
        returned is the number dismissed (one row, zero when nothing matched).
        """
        prop = _FIELD_PROPERTY[field]
        return await self._executor.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:HAS_INSIGHT]->(i:Insight)
            WHERE {_ACTIVE_INSIGHT}
              AND i.{prop} = $value
            SET i.dismissed = true,
                i.dismissed_at = datetime(),
                i.dismissed_notes = ''
            RETURN count(i) AS dismissed_count
            """,
            {"user_uid": user_uid, "value": value},
        )

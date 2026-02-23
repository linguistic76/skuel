"""
Ku Relationship Service
========================

Creates graph relationships for Ku nodes.

Relationships Created:
1. FOLLOWS -> Previous Ku of same type (temporal continuity)
2. RELATED_TO -> Ku with shared topics (thematic connections)
3. SUPPORTS_GOAL -> Goals mentioned in content (goal progress tracking)
"""

from typing import TYPE_CHECKING, Any

from core.models.entity_types import Ku
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import BackendOperations


class ReportsRelationshipService:
    """Service for creating graph relationships on Ku nodes."""

    def __init__(self, backend: "BackendOperations[Any]") -> None:
        """
        Initialize Ku relationship service.

        Args:
            backend: BackendOperations for database access (REQUIRED)
        """
        self.backend = backend
        self.logger = get_logger("skuel.services.ku_relationship")

    # ========================================================================
    # RELATIONSHIP CREATION
    # ========================================================================

    async def create_report_relationships(
        self,
        ku: Ku,
        themes: list[str] | None = None,
        active_goals: list[dict[str, str]] | None = None,
    ) -> Result[dict[str, int]]:
        """
        Create graph relationships for a Ku.

        Args:
            ku: The newly created/updated Ku
            themes: Optional list of themes for thematic relationships
            active_goals: Optional list of active goals for goal-support relationships

        Returns:
            Result containing counts of relationships created
        """
        relationships_created = {"temporal": 0, "thematic": 0, "goal_support": 0}

        try:
            # 1. Temporal Relationship: FOLLOWS (previous Ku of same type)
            temporal_result = await self._create_temporal_relationship(
                report.uid,
                report.user_uid,
                report.ku_type.value,
            )
            relationships_created["temporal"] = temporal_result

            # 2. Thematic Relationships: RELATED_TO (shared topics)
            if themes:
                thematic_result = await self._create_thematic_relationships(
                    report.uid,
                    report.user_uid,
                    themes,
                )
                relationships_created["thematic"] = thematic_result

            # 3. Goal Support Relationships: SUPPORTS_GOAL
            processed_content = getattr(report, "processed_content", None)
            if active_goals and processed_content:
                goal_result = await self._create_goal_relationships(
                    report.uid, processed_content, active_goals
                )
                relationships_created["goal_support"] = goal_result

            self.logger.info(
                f"Created Ku relationships: {relationships_created['temporal']} temporal, "
                f"{relationships_created['thematic']} thematic, {relationships_created['goal_support']} goal_support"
            )

            return Result.ok(relationships_created)

        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="create_report_relationships",
                    message=f"Failed to create relationships: {e!s}",
                )
            )

    # ========================================================================
    # TEMPORAL RELATIONSHIPS
    # ========================================================================

    async def _create_temporal_relationship(
        self, ku_uid: str, user_uid: str | None, ku_type: str
    ) -> int:
        """
        Create FOLLOWS relationship to most recent previous Ku of same type.

        Args:
            ku_uid: UID of the new Ku
            user_uid: User identifier (None for curriculum)
            ku_type: Type of Ku for filtering

        Returns:
            Count of relationships created (0 or 1)
        """
        if not user_uid:
            return 0  # CURRICULUM Ku don't have temporal chains per user

        cypher = """
        MATCH (new:Entity {uid: $ku_uid})
        MATCH (prev:Entity {user_uid: $user_uid, ku_type: $ku_type})
        WHERE prev.uid <> $ku_uid
          AND prev.created_at <= new.created_at
        WITH new, prev
        ORDER BY prev.created_at DESC
        LIMIT 1
        MERGE (new)-[r:FOLLOWS]->(prev)
        RETURN count(r) as count
        """

        result = await self.backend.execute_query(
            cypher,
            {
                "ku_uid": ku_uid,
                "user_uid": user_uid,
                "ku_type": ku_type,
            },
        )
        if result.is_error:
            return 0
        records = result.value or []
        return records[0]["count"] if records else 0

    # ========================================================================
    # THEMATIC RELATIONSHIPS
    # ========================================================================

    async def _create_thematic_relationships(
        self,
        ku_uid: str,
        user_uid: str | None,
        themes: list[str],
    ) -> int:
        """
        Create RELATED_TO relationships for Ku sharing topics.

        Args:
            ku_uid: UID of the new Ku
            user_uid: User identifier
            themes: List of themes to match

        Returns:
            Count of relationships created
        """
        if not themes or not user_uid:
            return 0

        cypher = """
        MATCH (new:Entity {uid: $ku_uid})
        MATCH (other:Entity {user_uid: $user_uid})
        WHERE other.uid <> $ku_uid
          AND other.metadata IS NOT NULL
        WITH new, other, other.metadata.themes as other_themes
        WHERE other_themes IS NOT NULL
          AND any(topic IN $themes WHERE topic IN other_themes)
        WITH new, other
        LIMIT 5
        MERGE (new)-[r:RELATED_TO {shared_topics: $shared_topics_str}]->(other)
        RETURN count(r) as count
        """

        result = await self.backend.execute_query(
            cypher,
            {
                "ku_uid": ku_uid,
                "user_uid": user_uid,
                "themes": themes,
                "shared_topics_str": ", ".join(themes[:3]),
            },
        )
        if result.is_error:
            return 0
        records = result.value or []
        return records[0]["count"] if records else 0

    # ========================================================================
    # GOAL RELATIONSHIPS
    # ========================================================================

    async def _create_goal_relationships(
        self,
        ku_uid: str,
        processed_content: str,
        active_goals: list[dict[str, str]],
    ) -> int:
        """
        Create SUPPORTS_GOAL relationships for mentioned goals.

        Args:
            ku_uid: UID of the Ku
            processed_content: Processed Ku content
            active_goals: List of active goals from context

        Returns:
            Count of relationships created
        """
        from core.infrastructure.batch import BatchOperationHelper

        content_lower = processed_content.lower()
        mentioned_goal_uids = []

        for goal in active_goals:
            goal_title_lower = goal["title"].lower()
            if goal_title_lower in content_lower:
                mentioned_goal_uids.append(goal["uid"])

        if not mentioned_goal_uids:
            return 0

        relationships = [
            (ku_uid, goal_uid, RelationshipName.SUPPORTS_GOAL.value, None)
            for goal_uid in mentioned_goal_uids
        ]

        queries = BatchOperationHelper.build_relationship_create_queries(relationships)

        total_created = 0
        for query, rels_data in queries:
            result = await self.backend.execute_query(query, {"rels": rels_data})
            if result.is_error:
                continue
            records = result.value or []
            total_created += records[0]["created_count"] if records else 0

        return total_created

    # ========================================================================
    # RELATIONSHIP QUERIES
    # ========================================================================

    async def get_related_reports(self, ku_uid: str) -> Result[list[str]]:
        """
        Get UIDs of related Ku.

        Graph relationship: (ku)-[:RELATED_TO]->(ku)

        Args:
            ku_uid: UID of the Ku

        Returns:
            Result containing list of related Ku UIDs
        """
        cypher = """
        MATCH (a:Entity {uid: $ku_uid})-[:RELATED_TO]->(related:Entity)
        RETURN related.uid as uid
        ORDER BY related.uid
        """

        result = await self.backend.execute_query(cypher, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok([r["uid"] for r in (result.value or []) if r["uid"]])

    async def get_supported_goals(self, ku_uid: str) -> Result[list[str]]:
        """
        Get UIDs of goals supported by this Ku.

        Graph relationship: (ku)-[:SUPPORTS_GOAL]->(goal)

        Args:
            ku_uid: UID of the Ku

        Returns:
            Result containing list of supported goal UIDs
        """
        cypher = """
        MATCH (a:Entity {uid: $ku_uid})-[:SUPPORTS_GOAL]->(goal:Goal)
        RETURN goal.uid as uid
        ORDER BY goal.uid
        """

        result = await self.backend.execute_query(cypher, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok([r["uid"] for r in (result.value or []) if r["uid"]])

    async def get_report_summary(self, ku_uid: str) -> Result[dict[str, int]]:
        """
        Get comprehensive relationship summary for a Ku.

        Returns counts for all relationship types.

        Args:
            ku_uid: UID of the Ku

        Returns:
            Result containing dict with relationship counts
        """
        cypher = """
        MATCH (a:Entity {uid: $ku_uid})
        OPTIONAL MATCH (a)-[:RELATED_TO]->(related)
        OPTIONAL MATCH (a)-[:SUPPORTS_GOAL]->(goal)
        OPTIONAL MATCH (a)-[:FOLLOWS]->(prev)
        RETURN count(DISTINCT related) as related_count,
               count(DISTINCT goal) as goal_count,
               count(DISTINCT prev) as follows_count
        """

        result = await self.backend.execute_query(cypher, {"ku_uid": ku_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        if not records:
            return Result.ok(
                {
                    "related_ku_count": 0,
                    "supported_goal_count": 0,
                    "follows_count": 0,
                }
            )

        record = records[0]
        return Result.ok(
            {
                "related_ku_count": record["related_count"],
                "supported_goal_count": record["goal_count"],
                "follows_count": record["follows_count"],
            }
        )

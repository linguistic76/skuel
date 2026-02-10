"""
Ku Relationship Service
========================

Creates graph relationships for Ku nodes.

Relationships Created:
1. FOLLOWS -> Previous Ku of same type (temporal continuity)
2. RELATED_TO -> Ku with shared topics (thematic connections)
3. SUPPORTS_GOAL -> Goals mentioned in content (goal progress tracking)
"""

from core.models.ku import Ku
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class KuRelationshipService:
    """Service for creating graph relationships on Ku nodes."""

    def __init__(self, driver) -> None:
        """
        Initialize Ku relationship service.

        Args:
            driver: Neo4j driver for database access
        """
        self.driver = driver
        self.logger = get_logger("skuel.services.ku_relationship")

    # ========================================================================
    # RELATIONSHIP CREATION
    # ========================================================================

    async def create_ku_relationships(
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
            async with self.driver.session() as session:
                # 1. Temporal Relationship: FOLLOWS (previous Ku of same type)
                temporal_result = await self._create_temporal_relationship(
                    session,
                    ku.uid,
                    ku.user_uid,
                    ku.ku_type.value,
                )
                relationships_created["temporal"] = temporal_result

                # 2. Thematic Relationships: RELATED_TO (shared topics)
                if themes:
                    thematic_result = await self._create_thematic_relationships(
                        session,
                        ku.uid,
                        ku.user_uid,
                        themes,
                    )
                    relationships_created["thematic"] = thematic_result

                # 3. Goal Support Relationships: SUPPORTS_GOAL
                if active_goals and ku.processed_content:
                    goal_result = await self._create_goal_relationships(
                        session, ku.uid, ku.processed_content, active_goals
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
                    operation="create_ku_relationships",
                    message=f"Failed to create relationships: {e!s}",
                )
            )

    # ========================================================================
    # TEMPORAL RELATIONSHIPS
    # ========================================================================

    async def _create_temporal_relationship(
        self, session, ku_uid: str, user_uid: str | None, ku_type: str
    ) -> int:
        """
        Create FOLLOWS relationship to most recent previous Ku of same type.

        Args:
            session: Neo4j session
            ku_uid: UID of the new Ku
            user_uid: User identifier (None for curriculum)
            ku_type: Type of Ku for filtering

        Returns:
            Count of relationships created (0 or 1)
        """
        if not user_uid:
            return 0  # CURRICULUM Ku don't have temporal chains per user

        cypher = """
        MATCH (new:Ku {uid: $ku_uid})
        MATCH (prev:Ku {user_uid: $user_uid, ku_type: $ku_type})
        WHERE prev.uid <> $ku_uid
          AND prev.created_at <= new.created_at
        WITH new, prev
        ORDER BY prev.created_at DESC
        LIMIT 1
        MERGE (new)-[r:FOLLOWS]->(prev)
        RETURN count(r) as count
        """

        result = await session.run(
            cypher,
            {
                "ku_uid": ku_uid,
                "user_uid": user_uid,
                "ku_type": ku_type,
            },
        )
        record = await result.single()
        return record["count"] if record else 0

    # ========================================================================
    # THEMATIC RELATIONSHIPS
    # ========================================================================

    async def _create_thematic_relationships(
        self,
        session,
        ku_uid: str,
        user_uid: str | None,
        themes: list[str],
    ) -> int:
        """
        Create RELATED_TO relationships for Ku sharing topics.

        Args:
            session: Neo4j session
            ku_uid: UID of the new Ku
            user_uid: User identifier
            themes: List of themes to match

        Returns:
            Count of relationships created
        """
        if not themes or not user_uid:
            return 0

        cypher = """
        MATCH (new:Ku {uid: $ku_uid})
        MATCH (other:Ku {user_uid: $user_uid})
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

        result = await session.run(
            cypher,
            {
                "ku_uid": ku_uid,
                "user_uid": user_uid,
                "themes": themes,
                "shared_topics_str": ", ".join(themes[:3]),
            },
        )
        record = await result.single()
        return record["count"] if record else 0

    # ========================================================================
    # GOAL RELATIONSHIPS
    # ========================================================================

    async def _create_goal_relationships(
        self,
        session,
        ku_uid: str,
        processed_content: str,
        active_goals: list[dict[str, str]],
    ) -> int:
        """
        Create SUPPORTS_GOAL relationships for mentioned goals.

        Args:
            session: Neo4j session
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
            result = await session.run(query, {"rels": rels_data})
            record = await result.single()
            total_created += record["created_count"] if record else 0

        return total_created

    # ========================================================================
    # RELATIONSHIP QUERIES
    # ========================================================================

    async def get_related_kus(self, ku_uid: str) -> Result[list[str]]:
        """
        Get UIDs of related Ku.

        Graph relationship: (ku)-[:RELATED_TO]->(ku)

        Args:
            ku_uid: UID of the Ku

        Returns:
            Result containing list of related Ku UIDs
        """
        cypher = """
        MATCH (a:Ku {uid: $ku_uid})-[:RELATED_TO]->(related:Ku)
        RETURN related.uid as uid
        ORDER BY related.uid
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"ku_uid": ku_uid})
                records = [r async for r in result]
                return Result.ok([r["uid"] for r in records if r["uid"]])
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_related_kus",
                    message=f"Failed to get related Ku: {e!s}",
                )
            )

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
        MATCH (a:Ku {uid: $ku_uid})-[:SUPPORTS_GOAL]->(goal:Goal)
        RETURN goal.uid as uid
        ORDER BY goal.uid
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"ku_uid": ku_uid})
                records = [r async for r in result]
                return Result.ok([r["uid"] for r in records if r["uid"]])
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_supported_goals",
                    message=f"Failed to get supported goals: {e!s}",
                )
            )

    async def get_ku_summary(self, ku_uid: str) -> Result[dict[str, int]]:
        """
        Get comprehensive relationship summary for a Ku.

        Returns counts for all relationship types.

        Args:
            ku_uid: UID of the Ku

        Returns:
            Result containing dict with relationship counts
        """
        cypher = """
        MATCH (a:Ku {uid: $ku_uid})
        OPTIONAL MATCH (a)-[:RELATED_TO]->(related)
        OPTIONAL MATCH (a)-[:SUPPORTS_GOAL]->(goal)
        OPTIONAL MATCH (a)-[:FOLLOWS]->(prev)
        RETURN count(DISTINCT related) as related_count,
               count(DISTINCT goal) as goal_count,
               count(DISTINCT prev) as follows_count
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"ku_uid": ku_uid})
                record = await result.single()

                if not record:
                    return Result.ok(
                        {
                            "related_ku_count": 0,
                            "supported_goal_count": 0,
                            "follows_count": 0,
                        }
                    )

                return Result.ok(
                    {
                        "related_ku_count": record["related_count"],
                        "supported_goal_count": record["goal_count"],
                        "follows_count": record["follows_count"],
                    }
                )
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_ku_summary",
                    message=f"Failed to get Ku summary: {e!s}",
                )
            )

"""
Reports Relationship Service
=================================

Creates graph relationships for Report nodes.

Unified service for all report types including journals (February 2026 merge).

Relationships Created:
1. FOLLOWS -> Previous report of same type (temporal continuity)
2. RELATED_TO -> Reports with shared topics (thematic connections)
3. SUPPORTS_GOAL -> Goals mentioned in content (goal progress tracking)
"""

from core.models.relationship_names import RelationshipName
from core.models.report.report import Report
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class ReportsRelationshipService:
    """
    Service for creating graph relationships on Report nodes.

    Handles all report relationships including journals (merged February 2026).
    """

    def __init__(self, driver) -> None:
        """
        Initialize reports relationship service.

        Args:
            driver: Neo4j driver for database access
        """
        self.driver = driver
        self.logger = get_logger("skuel.services.reports_relationship")

    # ========================================================================
    # RELATIONSHIP CREATION
    # ========================================================================

    async def create_report_relationships(
        self,
        report: Report,
        themes: list[str] | None = None,
        active_goals: list[dict[str, str]] | None = None,
    ) -> Result[dict[str, int]]:
        """
        Create graph relationships for a report.

        Args:
            report: The newly created/updated report
            themes: Optional list of themes for thematic relationships
            active_goals: Optional list of active goals for goal-support relationships

        Returns:
            Result containing counts of relationships created
        """
        relationships_created = {"temporal": 0, "thematic": 0, "goal_support": 0}

        try:
            async with self.driver.session() as session:
                # 1. Temporal Relationship: FOLLOWS (previous report of same type)
                temporal_result = await self._create_temporal_relationship(
                    session,
                    report.uid,
                    report.user_uid,
                    report.report_type.value,
                )
                relationships_created["temporal"] = temporal_result

                # 2. Thematic Relationships: RELATED_TO (shared topics)
                if themes:
                    thematic_result = await self._create_thematic_relationships(
                        session,
                        report.uid,
                        report.user_uid,
                        themes,
                    )
                    relationships_created["thematic"] = thematic_result

                # 3. Goal Support Relationships: SUPPORTS_GOAL
                if active_goals and report.processed_content:
                    goal_result = await self._create_goal_relationships(
                        session, report.uid, report.processed_content, active_goals
                    )
                    relationships_created["goal_support"] = goal_result

            self.logger.info(
                f"Created report relationships: {relationships_created['temporal']} temporal, "
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
        self, session, report_uid: str, user_uid: str, report_type: str
    ) -> int:
        """
        Create FOLLOWS relationship to most recent previous report of same type.

        Links reports in temporal order for continuity.

        Args:
            session: Neo4j session
            report_uid: UID of the new report
            user_uid: User identifier
            report_type: Type of report for filtering

        Returns:
            Count of relationships created (0 or 1)
        """
        cypher = """
        MATCH (new:Report {uid: $report_uid})
        MATCH (prev:Report {user_uid: $user_uid, report_type: $report_type})
        WHERE prev.uid <> $report_uid
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
                "report_uid": report_uid,
                "user_uid": user_uid,
                "report_type": report_type,
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
        report_uid: str,
        user_uid: str,
        themes: list[str],
    ) -> int:
        """
        Create RELATED_TO relationships for reports sharing topics.

        Connects reports with similar themes for discovery.

        Args:
            session: Neo4j session
            report_uid: UID of the new report
            user_uid: User identifier
            themes: List of themes to match

        Returns:
            Count of relationships created
        """
        if not themes:
            return 0

        cypher = """
        MATCH (new:Report {uid: $report_uid})
        MATCH (other:Report {user_uid: $user_uid})
        WHERE other.uid <> $report_uid
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
                "report_uid": report_uid,
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
        report_uid: str,
        processed_content: str,
        active_goals: list[dict[str, str]],
    ) -> int:
        """
        Create SUPPORTS_GOAL relationships for mentioned goals.

        Connects reports to goals mentioned in content.

        Args:
            session: Neo4j session
            report_uid: UID of the report
            processed_content: Processed report content
            active_goals: List of active goals from context

        Returns:
            Count of relationships created
        """
        from core.infrastructure.batch import BatchOperationHelper

        # Extract goal mentions from content
        content_lower = processed_content.lower()
        mentioned_goal_uids = []

        for goal in active_goals:
            goal_title_lower = goal["title"].lower()
            # Check if goal title appears in content
            if goal_title_lower in content_lower:
                mentioned_goal_uids.append(goal["uid"])

        if not mentioned_goal_uids:
            return 0

        # Build relationship tuples for batch creation
        relationships = [
            (report_uid, goal_uid, RelationshipName.SUPPORTS_GOAL.value, None)
            for goal_uid in mentioned_goal_uids
        ]

        # Use BatchOperationHelper for pure Cypher query generation
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

    async def get_related_reports(self, report_uid: str) -> Result[list[str]]:
        """
        Get UIDs of related reports.

        Graph relationship: (report)-[:RELATED_TO]->(report)

        Args:
            report_uid: UID of the report

        Returns:
            Result containing list of related report UIDs
        """
        cypher = """
        MATCH (a:Report {uid: $report_uid})-[:RELATED_TO]->(related:Report)
        RETURN related.uid as uid
        ORDER BY related.uid
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"report_uid": report_uid})
                records = [r async for r in result]
                return Result.ok([r["uid"] for r in records if r["uid"]])
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_related_reports",
                    message=f"Failed to get related reports: {e!s}",
                )
            )

    async def get_supported_goals(self, report_uid: str) -> Result[list[str]]:
        """
        Get UIDs of goals supported by this report.

        Graph relationship: (report)-[:SUPPORTS_GOAL]->(goal)

        Args:
            report_uid: UID of the report

        Returns:
            Result containing list of supported goal UIDs
        """
        cypher = """
        MATCH (a:Report {uid: $report_uid})-[:SUPPORTS_GOAL]->(goal:Goal)
        RETURN goal.uid as uid
        ORDER BY goal.uid
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"report_uid": report_uid})
                records = [r async for r in result]
                return Result.ok([r["uid"] for r in records if r["uid"]])
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_supported_goals",
                    message=f"Failed to get supported goals: {e!s}",
                )
            )

    async def get_report_summary(self, report_uid: str) -> Result[dict[str, int]]:
        """
        Get comprehensive relationship summary for a report.

        Returns counts for all relationship types.

        Args:
            report_uid: UID of the report

        Returns:
            Result containing dict with relationship counts
        """
        cypher = """
        MATCH (a:Report {uid: $report_uid})
        OPTIONAL MATCH (a)-[:RELATED_TO]->(related)
        OPTIONAL MATCH (a)-[:SUPPORTS_GOAL]->(goal)
        OPTIONAL MATCH (a)-[:FOLLOWS]->(prev)
        RETURN count(DISTINCT related) as related_count,
               count(DISTINCT goal) as goal_count,
               count(DISTINCT prev) as follows_count
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"report_uid": report_uid})
                record = await result.single()

                if not record:
                    return Result.ok(
                        {
                            "related_report_count": 0,
                            "supported_goal_count": 0,
                            "follows_count": 0,
                        }
                    )

                return Result.ok(
                    {
                        "related_report_count": record["related_count"],
                        "supported_goal_count": record["goal_count"],
                        "follows_count": record["follows_count"],
                    }
                )
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_report_summary",
                    message=f"Failed to get report summary: {e!s}",
                )
            )

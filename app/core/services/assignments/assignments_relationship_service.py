"""
Assignment Relationship Service
=================================

Creates graph relationships for Assignment nodes (file submissions).

Domain Separation (January 2026):
- Assignments: File submission, teacher review, gradebook
- Journals: Personal reflections - use JournalRelationshipService for :Journal nodes

This service handles relationships for :Assignment nodes only.

Relationships Created:
1. FOLLOWS → Previous assignment of same type (temporal continuity)
2. RELATED_TO → Assignments with shared topics (thematic connections)
3. SUPPORTS_GOAL → Goals mentioned in content (goal progress tracking)
"""

from core.models.assignment.assignment import Assignment
from core.models.relationship_names import RelationshipName
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class AssignmentRelationshipService:
    """
    Service for creating graph relationships on Assignment nodes.

    Handles file submission relationships (transcripts, reports, etc.).
    For Journal relationships, use JournalRelationshipService.
    """

    def __init__(self, driver) -> None:
        """
        Initialize assignment relationship service.

        Args:
            driver: Neo4j driver for database access
        """
        self.driver = driver
        self.logger = get_logger("skuel.services.assignment_relationship")

    # ========================================================================
    # RELATIONSHIP CREATION
    # ========================================================================

    async def create_assignment_relationships(
        self,
        assignment: Assignment,
        themes: list[str] | None = None,
        active_goals: list[dict[str, str]] | None = None,
    ) -> Result[dict[str, int]]:
        """
        Create graph relationships for an assignment.

        Args:
            assignment: The newly created/updated assignment
            themes: Optional list of themes for thematic relationships
            active_goals: Optional list of active goals for goal-support relationships

        Returns:
            Result containing counts of relationships created
        """
        relationships_created = {"temporal": 0, "thematic": 0, "goal_support": 0}

        try:
            async with self.driver.session() as session:
                # 1. Temporal Relationship: FOLLOWS (previous assignment of same type)
                temporal_result = await self._create_temporal_relationship(
                    session,
                    assignment.uid,
                    assignment.user_uid,
                    assignment.assignment_type.value,
                )
                relationships_created["temporal"] = temporal_result

                # 2. Thematic Relationships: RELATED_TO (shared topics)
                if themes:
                    thematic_result = await self._create_thematic_relationships(
                        session,
                        assignment.uid,
                        assignment.user_uid,
                        themes,
                    )
                    relationships_created["thematic"] = thematic_result

                # 3. Goal Support Relationships: SUPPORTS_GOAL
                if active_goals and assignment.processed_content:
                    goal_result = await self._create_goal_relationships(
                        session, assignment.uid, assignment.processed_content, active_goals
                    )
                    relationships_created["goal_support"] = goal_result

            self.logger.info(
                f"Created assignment relationships: {relationships_created['temporal']} temporal, "
                f"{relationships_created['thematic']} thematic, {relationships_created['goal_support']} goal_support"
            )

            return Result.ok(relationships_created)

        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="create_assignment_relationships",
                    message=f"Failed to create relationships: {e!s}",
                )
            )

    # ========================================================================
    # TEMPORAL RELATIONSHIPS
    # ========================================================================

    async def _create_temporal_relationship(
        self, session, assignment_uid: str, user_uid: str, assignment_type: str
    ) -> int:
        """
        Create FOLLOWS relationship to most recent previous assignment of same type.

        Links assignments in temporal order for continuity.

        Args:
            session: Neo4j session
            assignment_uid: UID of the new assignment
            user_uid: User identifier
            assignment_type: Type of assignment for filtering

        Returns:
            Count of relationships created (0 or 1)
        """
        cypher = """
        MATCH (new:Assignment {uid: $assignment_uid})
        MATCH (prev:Assignment {user_uid: $user_uid, assignment_type: $assignment_type})
        WHERE prev.uid <> $assignment_uid
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
                "assignment_uid": assignment_uid,
                "user_uid": user_uid,
                "assignment_type": assignment_type,
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
        assignment_uid: str,
        user_uid: str,
        themes: list[str],
    ) -> int:
        """
        Create RELATED_TO relationships for assignments sharing topics.

        Connects assignments with similar themes for discovery.

        Args:
            session: Neo4j session
            assignment_uid: UID of the new assignment
            user_uid: User identifier
            themes: List of themes to match

        Returns:
            Count of relationships created
        """
        if not themes:
            return 0

        cypher = """
        MATCH (new:Assignment {uid: $assignment_uid})
        MATCH (other:Assignment {user_uid: $user_uid})
        WHERE other.uid <> $assignment_uid
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
                "assignment_uid": assignment_uid,
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
        assignment_uid: str,
        processed_content: str,
        active_goals: list[dict[str, str]],
    ) -> int:
        """
        Create SUPPORTS_GOAL relationships for mentioned goals.

        Connects assignments to goals mentioned in content.

        Args:
            session: Neo4j session
            assignment_uid: UID of the assignment
            processed_content: Processed assignment content
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
            (assignment_uid, goal_uid, RelationshipName.SUPPORTS_GOAL.value, None)
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

    async def get_related_assignments(self, assignment_uid: str) -> Result[list[str]]:
        """
        Get UIDs of related assignments.

        Graph relationship: (assignment)-[:RELATED_TO]->(assignment)

        Args:
            assignment_uid: UID of the assignment

        Returns:
            Result containing list of related assignment UIDs
        """
        cypher = """
        MATCH (a:Assignment {uid: $assignment_uid})-[:RELATED_TO]->(related:Assignment)
        RETURN related.uid as uid
        ORDER BY related.uid
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"assignment_uid": assignment_uid})
                records = [r async for r in result]
                return Result.ok([r["uid"] for r in records if r["uid"]])
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_related_assignments",
                    message=f"Failed to get related assignments: {e!s}",
                )
            )

    async def get_supported_goals(self, assignment_uid: str) -> Result[list[str]]:
        """
        Get UIDs of goals supported by this assignment.

        Graph relationship: (assignment)-[:SUPPORTS_GOAL]->(goal)

        Args:
            assignment_uid: UID of the assignment

        Returns:
            Result containing list of supported goal UIDs
        """
        cypher = """
        MATCH (a:Assignment {uid: $assignment_uid})-[:SUPPORTS_GOAL]->(goal:Goal)
        RETURN goal.uid as uid
        ORDER BY goal.uid
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"assignment_uid": assignment_uid})
                records = [r async for r in result]
                return Result.ok([r["uid"] for r in records if r["uid"]])
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_supported_goals",
                    message=f"Failed to get supported goals: {e!s}",
                )
            )

    async def get_assignment_summary(self, assignment_uid: str) -> Result[dict[str, int]]:
        """
        Get comprehensive relationship summary for an assignment.

        Returns counts for all relationship types.

        Args:
            assignment_uid: UID of the assignment

        Returns:
            Result containing dict with relationship counts
        """
        cypher = """
        MATCH (a:Assignment {uid: $assignment_uid})
        OPTIONAL MATCH (a)-[:RELATED_TO]->(related)
        OPTIONAL MATCH (a)-[:SUPPORTS_GOAL]->(goal)
        OPTIONAL MATCH (a)-[:FOLLOWS]->(prev)
        RETURN count(DISTINCT related) as related_count,
               count(DISTINCT goal) as goal_count,
               count(DISTINCT prev) as follows_count
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"assignment_uid": assignment_uid})
                record = await result.single()

                if not record:
                    return Result.ok(
                        {
                            "related_assignment_count": 0,
                            "supported_goal_count": 0,
                            "follows_count": 0,
                        }
                    )

                return Result.ok(
                    {
                        "related_assignment_count": record["related_count"],
                        "supported_goal_count": record["goal_count"],
                        "follows_count": record["follows_count"],
                    }
                )
        except Exception as e:
            return Result.fail(
                Errors.database(
                    operation="get_assignment_summary",
                    message=f"Failed to get assignment summary: {e!s}",
                )
            )

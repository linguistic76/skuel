"""
Analytics Relationship Service
================================

Cross-domain relationship management for Analytics entities.

**ARCHITECTURAL PATTERN: Direct Driver (Graph-Native)**
--------------------------------------------------------
This service uses the DIRECT DRIVER pattern, matching JournalRelationshipService.

**Key Characteristics:**
- Does NOT inherit from BaseService
- Takes AsyncDriver directly (not a protocol-based backend)
- Does NOT use RelationshipCreationHelper or SemanticRelationshipHelper
- Writes raw Cypher queries directly via driver.session()
- Simpler, more direct graph operations

**Why This Pattern:**
- Analytics relationships are simple (aggregation and coverage)
- Direct Cypher provides maximum clarity for graph traversal
- Analytics are meta-entities that summarize other domains

**Note:** This service is NOT compatible with GenericRelationshipService base class.
See: /docs/patterns/GENERIC_RELATIONSHIP_SERVICE_HONEST_ASSESSMENT.md

Graph Relationships Managed:
----------------------------
- (report)-[:AGGREGATES_DOMAIN]->(domain) - Which domain this analytics covers
- (report)-[:INCLUDES_ENTITY]->(entity) - Specific entities included in analytics
- (report)-[:REPORTS_ON_GOAL]->(goal) - Goals covered by this analytics

Date: November 26, 2025
"""

from __future__ import annotations

from typing import Any

from core.infrastructure.batch import BatchOperationHelper
from core.utils.processor_functions import (
    extract_dict_from_first_record,
    extract_uids_list,
)
from core.utils.result_simplified import Result


class AnalyticsRelationshipService:
    """
    Cross-domain relationship service for Analytics entities.

    Provides graph traversal and relationship management for analytics relationships.
    Analytics aggregate data from activity domains (tasks, habits, goals, etc.)
    into statistical summaries ("report cards").

    Semantic Types Used:
    - AGGREGATES_DOMAIN: Which domain the analytics covers (TASKS, HABITS, etc.)
    - INCLUDES_ENTITY: Specific entities included in the analytics metrics
    - REPORTS_ON_GOAL: Goals this analytics tracks progress on
    """

    def __init__(self, executor: Any = None) -> None:
        """
        Initialize Analytics relationship service.

        Args:
            executor: Query executor for graph queries
        """
        self.executor = executor

    # ========================================================================
    # User Reports (2 methods)
    # ========================================================================

    async def get_user_reports(self, user_uid: str, limit: int = 50) -> Result[list[str]]:
        """
        Get UIDs of reports for a user.

        Args:
            user_uid: UID of the user
            limit: Maximum number of reports to return

        Returns:
            Result containing list of report UIDs
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report {user_uid: $user_uid})
                RETURN report.uid as uid
                ORDER BY report.generated_at DESC
                LIMIT $limit
            """,
            params={"user_uid": user_uid, "limit": limit},
            processor=extract_uids_list,
            operation="get_user_reports",
        )

    async def get_user_reports_by_type(
        self, user_uid: str, report_type: str, limit: int = 20
    ) -> Result[list[str]]:
        """
        Get UIDs of reports for a user filtered by type.

        Args:
            user_uid: UID of the user
            report_type: Report type (e.g., "TASKS", "HABITS", "GOALS")
            limit: Maximum number of reports to return

        Returns:
            Result containing list of report UIDs
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report {user_uid: $user_uid, report_type: $report_type})
                RETURN report.uid as uid
                ORDER BY report.generated_at DESC
                LIMIT $limit
            """,
            params={"user_uid": user_uid, "report_type": report_type, "limit": limit},
            processor=extract_uids_list,
            operation="get_user_reports_by_type",
        )

    # ========================================================================
    # Entity Inclusion (2 methods)
    # ========================================================================

    async def get_included_entities(self, report_uid: str) -> Result[list[str]]:
        """
        Get UIDs of entities included in this report.

        Graph relationship: (report)-[:INCLUDES_ENTITY]->(entity)

        Args:
            report_uid: UID of the report

        Returns:
            Result containing list of entity UIDs included in report
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report {uid: $report_uid})-[:INCLUDES_ENTITY]->(entity)
                RETURN entity.uid as uid
                ORDER BY entity.uid
            """,
            params={"report_uid": report_uid},
            processor=extract_uids_list,
            operation="get_included_entities",
        )

    async def get_reports_including_entity(self, entity_uid: str) -> Result[list[str]]:
        """
        Get UIDs of reports that include a specific entity.

        Inverse query: Find all reports referencing this entity.

        Args:
            entity_uid: UID of the entity (task, habit, goal, etc.)

        Returns:
            Result containing list of report UIDs that include this entity
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report)-[:INCLUDES_ENTITY]->(entity {uid: $entity_uid})
                RETURN report.uid as uid
                ORDER BY report.generated_at DESC
            """,
            params={"entity_uid": entity_uid},
            processor=extract_uids_list,
            operation="get_reports_including_entity",
        )

    # ========================================================================
    # Goal Coverage (2 methods)
    # ========================================================================

    async def get_reported_goals(self, report_uid: str) -> Result[list[str]]:
        """
        Get UIDs of goals covered by this report.

        Graph relationship: (report)-[:REPORTS_ON_GOAL]->(goal)

        Args:
            report_uid: UID of the report

        Returns:
            Result containing list of goal UIDs
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report {uid: $report_uid})-[:REPORTS_ON_GOAL]->(goal:Goal)
                RETURN goal.uid as uid
                ORDER BY goal.uid
            """,
            params={"report_uid": report_uid},
            processor=extract_uids_list,
            operation="get_reported_goals",
        )

    async def get_goal_reports(self, goal_uid: str) -> Result[list[str]]:
        """
        Get UIDs of reports that cover a specific goal.

        Inverse query: Find all reports tracking this goal.

        Args:
            goal_uid: UID of the goal

        Returns:
            Result containing list of report UIDs covering this goal
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report)-[:REPORTS_ON_GOAL]->(goal:Goal {uid: $goal_uid})
                RETURN report.uid as uid
                ORDER BY report.generated_at DESC
            """,
            params={"goal_uid": goal_uid},
            processor=extract_uids_list,
            operation="get_goal_reports",
        )

    # ========================================================================
    # Existence Checks (2 methods)
    # ========================================================================

    async def has_included_entities(self, report_uid: str) -> Result[bool]:
        """
        Check if report has any included entities.

        Args:
            report_uid: UID of the report

        Returns:
            Result containing True if report includes entities
        """
        return await self.executor.execute_exists(
            query="MATCH (report:Report {uid: $report_uid})-[:INCLUDES_ENTITY]->() RETURN report",
            params={"report_uid": report_uid},
            operation="has_included_entities",
        )

    async def covers_goals(self, report_uid: str) -> Result[bool]:
        """
        Check if report covers any goals.

        Args:
            report_uid: UID of the report

        Returns:
            Result containing True if report covers goals
        """
        return await self.executor.execute_exists(
            query="MATCH (report:Report {uid: $report_uid})-[:REPORTS_ON_GOAL]->() RETURN report",
            params={"report_uid": report_uid},
            operation="covers_goals",
        )

    # ========================================================================
    # Analytics Methods (3 methods)
    # ========================================================================

    async def count_included_entities(self, report_uid: str) -> Result[int]:
        """
        Count number of entities included in this report.

        Args:
            report_uid: UID of the report

        Returns:
            Result containing count of included entities
        """
        return await self.executor.execute_count(
            query="""
                MATCH (report:Report {uid: $report_uid})-[:INCLUDES_ENTITY]->()
                RETURN count(*) as count
            """,
            params={"report_uid": report_uid},
            operation="count_included_entities",
        )

    async def count_covered_goals(self, report_uid: str) -> Result[int]:
        """
        Count number of goals covered by this report.

        Args:
            report_uid: UID of the report

        Returns:
            Result containing count of covered goals
        """
        return await self.executor.execute_count(
            query="""
                MATCH (report:Report {uid: $report_uid})-[:REPORTS_ON_GOAL]->()
                RETURN count(*) as count
            """,
            params={"report_uid": report_uid},
            operation="count_covered_goals",
        )

    async def get_report_summary(self, report_uid: str) -> Result[dict[str, Any]]:
        """
        Get comprehensive relationship summary for report.

        Returns counts for all relationship types.

        Args:
            report_uid: UID of the report

        Returns:
            Result containing dict with relationship counts
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report {uid: $report_uid})
                OPTIONAL MATCH (report)-[:INCLUDES_ENTITY]->(entity)
                OPTIONAL MATCH (report)-[:REPORTS_ON_GOAL]->(goal)
                RETURN count(DISTINCT entity) as entity_count,
                       count(DISTINCT goal) as goal_count
            """,
            params={"report_uid": report_uid},
            processor=extract_dict_from_first_record(
                {
                    "included_entity_count": "entity_count",
                    "covered_goal_count": "goal_count",
                }
            ),
            operation="get_report_summary",
        )

    # ========================================================================
    # Period-Based Queries (2 methods)
    # ========================================================================

    async def get_reports_in_period(
        self, user_uid: str, start_date: str, end_date: str
    ) -> Result[list[str]]:
        """
        Get UIDs of reports for a user within a date range.

        Args:
            user_uid: UID of the user
            start_date: Start date in ISO format (YYYY-MM-DD)
            end_date: End date in ISO format (YYYY-MM-DD)

        Returns:
            Result containing list of report UIDs
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report {user_uid: $user_uid})
                WHERE report.period_start >= date($start_date)
                  AND report.period_end <= date($end_date)
                RETURN report.uid as uid
                ORDER BY report.generated_at DESC
            """,
            params={
                "user_uid": user_uid,
                "start_date": start_date,
                "end_date": end_date,
            },
            processor=extract_uids_list,
            operation="get_reports_in_period",
        )

    async def get_latest_report_by_type(self, user_uid: str, report_type: str) -> Result[list[str]]:
        """
        Get the most recent report of a specific type for a user.

        Args:
            user_uid: UID of the user
            report_type: Report type (e.g., "TASKS", "HABITS", "GOALS")

        Returns:
            Result containing list with single report UID (or empty)
        """
        return await self.executor.execute(
            query="""
                MATCH (report:Report {user_uid: $user_uid, report_type: $report_type})
                RETURN report.uid as uid
                ORDER BY report.generated_at DESC
                LIMIT 1
            """,
            params={"user_uid": user_uid, "report_type": report_type},
            processor=extract_uids_list,
            operation="get_latest_report_by_type",
        )

    # ========================================================================
    # Batch Relationship Creation (1 method)
    # ========================================================================

    async def create_report_relationships(
        self,
        report_uid: str,
        included_entity_uids: list[str] | None = None,
        goal_uids: list[str] | None = None,
    ) -> Result[int]:
        """
        Create all relationships for a report in batch.

        Efficient batch operation for report creation workflows.
        Uses UNWIND for optimal Neo4j performance.

        Args:
            report_uid: UID of the report
            included_entity_uids: Entity UIDs to link as included
            goal_uids: Goal UIDs to link as covered

        Returns:
            Result containing count of relationships created
        """
        # Build relationship tuples using BatchOperationHelper
        relationships = BatchOperationHelper.build_relationships_list(
            source_uid=report_uid,
            relationship_specs=[
                (included_entity_uids, "INCLUDES_ENTITY", None),
                (goal_uids, "REPORTS_ON_GOAL", None),
            ],
        )

        # Use consistent batch creation pattern
        return await self.executor.create_relationships_batch(
            relationships=relationships,
            operation="create_report_relationships",
        )

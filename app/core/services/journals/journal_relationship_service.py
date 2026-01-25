"""
Journal Relationship Service
=============================

Cross-domain relationship management for Journal entities.

**ARCHITECTURAL PATTERN: Direct Driver (Graph-Native)**
--------------------------------------------------------
This service uses the DIRECT DRIVER pattern, distinct from the helper-based
pattern used by other relationship services (tasks, goals, habits, etc.).

**Key Characteristics:**
- Does NOT inherit from BaseService
- Takes AsyncDriver directly (not a protocol-based backend)
- Does NOT use RelationshipCreationHelper or SemanticRelationshipHelper
- Writes raw Cypher queries directly via driver.session()
- Simpler, more direct graph operations

**Why This Pattern:**
- Journal relationships are simpler (only 2 relationship types)
- Direct Cypher provides maximum clarity for graph traversal
- No need for helper abstraction layer

**Note:** This service is NOT compatible with GenericRelationshipService base class.
See: /docs/patterns/GENERIC_RELATIONSHIP_SERVICE_HONEST_ASSESSMENT.md

Graph Relationships Managed:
----------------------------
- (journal)-[:RELATED_TO]->(journal) - Related journal entries
- (journal)-[:SUPPORTS_GOAL]->(goal) - Goals supported by this journal entry

Date: October 26, 2025
"""

from typing import Any

from neo4j import AsyncDriver

from core.infrastructure.batch import BatchOperationHelper
from core.models.relationship_names import RelationshipName
from core.services.graph_query_executor import GraphQueryExecutor
from core.utils.processor_functions import (
    extract_dict_from_first_record,
    extract_uids_list,
)
from core.utils.result_simplified import Result


class JournalRelationshipService:
    """
    Cross-domain relationship service for Journal entities.

    Provides graph traversal and relationship management for journal relationships.
    Replaces denormalized UID list fields with pure Neo4j graph queries.

    Semantic Types Used:
    - RELATED_TO: Journal connections (reflective relationships)
    - SUPPORTS_GOAL: Journals supporting goal achievement

    Source Tag: "journal_service_explicit"
    - All relationships are user-created (explicit journaling)

    Confidence Scoring:
    - 1.0: All journal relationships are explicit user actions
    """

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        """
        Initialize Journal relationship service.

        Args:
            driver: Neo4j async driver for graph queries (REQUIRED)

        Raises:
            ValueError: If driver is None (fail-fast philosophy)
        """
        if driver is None:
            raise ValueError("driver is REQUIRED for JournalRelationshipService (fail-fast)")
        self.driver = driver
        self.executor = GraphQueryExecutor(driver)  # Generic query executor

    # ========================================================================
    # Related Journals (1 method)
    # ========================================================================

    async def get_related_journals(self, journal_uid: str) -> Result[list[str]]:
        """
        Get UIDs of related journal entries.

        Replaces: journal.related_journal_uids (removed from JournalPure model)
        Graph relationship: (journal)-[:RELATED_TO]->(journal)

        Args:
            journal_uid: UID of the journal entry

        Returns:
            Result containing list of related journal UIDs
        """
        return await self.executor.execute(
            query="""
                MATCH (journal:Journal {uid: $journal_uid})-[:RELATED_TO]->(related:Journal)
                RETURN related.uid as uid
                ORDER BY related.uid
            """,
            params={"journal_uid": journal_uid},
            processor=extract_uids_list,
            operation="get_related_journals",
        )

    # ========================================================================
    # Goal Support (1 method)
    # ========================================================================

    async def get_supported_goals(self, journal_uid: str) -> Result[list[str]]:
        """
        Get UIDs of goals supported by this journal entry.

        Replaces: journal.goal_uids (removed from JournalPure model)
        Graph relationship: (journal)-[:SUPPORTS_GOAL]->(goal)

        Args:
            journal_uid: UID of the journal entry

        Returns:
            Result containing list of supported goal UIDs
        """
        return await self.executor.execute(
            query="""
                MATCH (journal:Journal {uid: $journal_uid})-[:SUPPORTS_GOAL]->(goal:Goal)
                RETURN goal.uid as uid
                ORDER BY goal.uid
            """,
            params={"journal_uid": journal_uid},
            processor=extract_uids_list,
            operation="get_supported_goals",
        )

    # ========================================================================
    # Existence Checks (2 methods)
    # ========================================================================

    async def has_related_journals(self, journal_uid: str) -> Result[bool]:
        """
        Check if journal has related journal entries.

        Args:
            journal_uid: UID of the journal entry

        Returns:
            Result containing True if journal has related entries
        """
        return await self.executor.execute_exists(
            query="MATCH (journal:Journal {uid: $journal_uid})-[:RELATED_TO]->() RETURN journal",
            params={"journal_uid": journal_uid},
            operation="has_related_journals",
        )

    async def supports_goals(self, journal_uid: str) -> Result[bool]:
        """
        Check if journal supports any goals.

        Args:
            journal_uid: UID of the journal entry

        Returns:
            Result containing True if journal supports goals
        """
        return await self.executor.execute_exists(
            query="MATCH (journal:Journal {uid: $journal_uid})-[:SUPPORTS_GOAL]->() RETURN journal",
            params={"journal_uid": journal_uid},
            operation="supports_goals",
        )

    # ========================================================================
    # Analytics Methods (3 methods)
    # ========================================================================

    async def count_related_journals(self, journal_uid: str) -> Result[int]:
        """
        Count number of related journal entries.

        Args:
            journal_uid: UID of the journal entry

        Returns:
            Result containing count of related journals
        """
        return await self.executor.execute_count(
            query="""
                MATCH (journal:Journal {uid: $journal_uid})-[:RELATED_TO]->()
                RETURN count(*) as count
            """,
            params={"journal_uid": journal_uid},
            operation="count_related_journals",
        )

    async def count_supported_goals(self, journal_uid: str) -> Result[int]:
        """
        Count number of goals supported by this journal.

        Args:
            journal_uid: UID of the journal entry

        Returns:
            Result containing count of supported goals
        """
        return await self.executor.execute_count(
            query="""
                MATCH (journal:Journal {uid: $journal_uid})-[:SUPPORTS_GOAL]->()
                RETURN count(*) as count
            """,
            params={"journal_uid": journal_uid},
            operation="count_supported_goals",
        )

    async def get_journal_summary(self, journal_uid: str) -> Result[dict[str, Any]]:
        """
        Get comprehensive relationship summary for journal entry.

        Returns counts for all relationship types.

        Args:
            journal_uid: UID of the journal entry

        Returns:
            Result containing dict with relationship counts
        """
        return await self.executor.execute(
            query="""
                MATCH (journal:Journal {uid: $journal_uid})
                OPTIONAL MATCH (journal)-[:RELATED_TO]->(related)
                OPTIONAL MATCH (journal)-[:SUPPORTS_GOAL]->(goal)
                RETURN count(DISTINCT related) as related_count,
                       count(DISTINCT goal) as goal_count
            """,
            params={"journal_uid": journal_uid},
            processor=extract_dict_from_first_record(
                {
                    "related_journal_count": "related_count",
                    "supported_goal_count": "goal_count",
                }
            ),
            operation="get_journal_summary",
        )

    # ========================================================================
    # Inverse Queries (2 methods)
    # ========================================================================

    async def get_journals_related_to(self, journal_uid: str) -> Result[list[str]]:
        """
        Get UIDs of journals that link TO this journal (inverse of RELATED_TO).

        Finds journals that have this journal as a related entry.

        Args:
            journal_uid: UID of the journal entry

        Returns:
            Result containing list of journal UIDs that link to this one
        """
        return await self.executor.execute(
            query="""
                MATCH (other:Journal)-[:RELATED_TO]->(journal:Journal {uid: $journal_uid})
                RETURN other.uid as uid
                ORDER BY other.uid
            """,
            params={"journal_uid": journal_uid},
            processor=extract_uids_list,
            operation="get_journals_related_to",
        )

    async def get_journals_supporting_goal(self, goal_uid: str) -> Result[list[str]]:
        """
        Get UIDs of journals that support a specific goal (inverse query).

        Finds all journal entries that reference this goal.

        Args:
            goal_uid: UID of the goal

        Returns:
            Result containing list of journal UIDs supporting this goal
        """
        return await self.executor.execute(
            query="""
                MATCH (journal:Journal)-[:SUPPORTS_GOAL]->(goal:Goal {uid: $goal_uid})
                RETURN journal.uid as uid
                ORDER BY journal.created_at DESC
            """,
            params={"goal_uid": goal_uid},
            processor=extract_uids_list,
            operation="get_journals_supporting_goal",
        )

    # ========================================================================
    # Batch Relationship Creation (1 method)
    # ========================================================================

    async def create_journal_relationships(
        self,
        journal_uid: str,
        related_journal_uids: list[str] | None = None,
        goal_uids: list[str] | None = None,
    ) -> Result[int]:
        """
        Create all relationships for a journal entry in batch.

        Efficient batch operation for journal creation/update workflows.
        Uses UNWIND for optimal Neo4j performance.

        Args:
            journal_uid: UID of the journal entry
            related_journal_uids: Journal UIDs to link as related
            goal_uids: Goal UIDs to link as supported

        Returns:
            Result containing count of relationships created
        """
        # Build relationship tuples using BatchOperationHelper
        relationships = BatchOperationHelper.build_relationships_list(
            source_uid=journal_uid,
            relationship_specs=[
                (related_journal_uids, RelationshipName.RELATED_TO.value, None),
                (goal_uids, RelationshipName.SUPPORTS_GOAL.value, None),
            ],
        )

        # Use consistent batch creation pattern
        return await self.executor.create_relationships_batch(
            relationships=relationships,
            operation="create_journal_relationships",
        )

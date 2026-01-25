"""
User-Knowledge Graph Schema
============================

Defines the schema for User-Knowledge relationships in Neo4j.
This enables personalized learning intelligence by tracking user progress,
mastery, and learning state as graph relationships.

Following SKUEL principles:
- No backwards compatibility - this is THE way
- Fail-fast - requires full Neo4j with APOC
- RDF-inspired semantic relationships
"""

from typing import Any

from neo4j import AsyncDriver

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


# ============================================================================
# RELATIONSHIP SCHEMA DEFINITIONS
# ============================================================================

USER_KNOWLEDGE_RELATIONSHIPS = {
    "MASTERED": {
        "description": "User has achieved mastery of knowledge unit",
        "properties": {
            "mastery_score": "Float (0.0-1.0) indicating level of mastery",
            "achieved_at": "DateTime when mastery was achieved",
            "practice_count": "Integer count of practice sessions",
            "last_practiced": "DateTime of most recent practice",
            "confidence_level": "Float (0.0-1.0) user's confidence in knowledge",
            "retention_score": "Float (0.0-1.0) estimated retention over time",
        },
        "constraints": ["mastery_score >= 0.8"],
        "example_cypher": """
            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $knowledge_uid})
            CREATE (u)-[:MASTERED {
                mastery_score: 0.95,
                achieved_at: datetime(),
                practice_count: 15,
                last_practiced: datetime(),
                confidence_level: 0.9,
                retention_score: 0.85
            }]->(k)
        """,
    },
    "IN_PROGRESS": {
        "description": "User is currently learning knowledge unit",
        "properties": {
            "progress": "Float (0.0-1.0) completion percentage",
            "started_at": "DateTime when learning started",
            "estimated_completion": "Date estimated completion",
            "time_invested_minutes": "Integer minutes invested",
            "difficulty_rating": "Float (0.0-1.0) perceived difficulty",
            "last_accessed": "DateTime of last access",
        },
        "example_cypher": """
            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $knowledge_uid})
            CREATE (u)-[:IN_PROGRESS {
                progress: 0.4,
                started_at: datetime(),
                estimated_completion: date() + duration('P7D'),
                time_invested_minutes: 120,
                difficulty_rating: 0.6,
                last_accessed: datetime()
            }]->(k)
        """,
    },
    "NEEDS_REVIEW": {
        "description": "User needs to review knowledge unit (spaced repetition)",
        "properties": {
            "last_reviewed": "DateTime of last review",
            "next_review_due": "DateTime when next review is due",
            "review_count": "Integer count of reviews",
            "retention_estimate": "Float (0.0-1.0) estimated retention",
            "review_interval_days": "Integer days between reviews",
            "urgency_score": "Float (0.0-1.0) urgency of review",
        },
        "example_cypher": """
            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $knowledge_uid})
            CREATE (u)-[:NEEDS_REVIEW {
                last_reviewed: datetime() - duration('P30D'),
                next_review_due: datetime(),
                review_count: 3,
                retention_estimate: 0.4,
                review_interval_days: 30,
                urgency_score: 0.8
            }]->(k)
        """,
    },
    "STRUGGLING_WITH": {
        "description": "User is having difficulty with knowledge unit",
        "properties": {
            "struggle_score": "Float (0.0-1.0) intensity of struggle",
            "identified_at": "DateTime when struggle was identified",
            "attempt_count": "Integer number of attempts",
            "error_patterns": "List[String] common errors/misunderstandings",
            "help_requests": "Integer count of help requests",
            "suggested_actions": "List[String] recommended actions",
        },
        "example_cypher": """
            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $knowledge_uid})
            CREATE (u)-[:STRUGGLING_WITH {
                struggle_score: 0.7,
                identified_at: datetime(),
                attempt_count: 5,
                error_patterns: ['prerequisite_gap', 'complex_syntax'],
                help_requests: 2,
                suggested_actions: ['review_prerequisites', 'practice_examples']
            }]->(k)
        """,
    },
    "INTERESTED_IN": {
        "description": "User expressed interest in knowledge unit",
        "properties": {
            "interest_score": "Float (0.0-1.0) level of interest",
            "expressed_at": "DateTime when interest was expressed",
            "interest_source": "String source of interest (query, recommendation, goal)",
            "priority": "String priority level (high, medium, low)",
            "notes": "String optional user notes",
        },
        "example_cypher": """
            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $knowledge_uid})
            CREATE (u)-[:INTERESTED_IN {
                interest_score: 0.8,
                expressed_at: datetime(),
                interest_source: 'goal_alignment',
                priority: 'high',
                notes: 'Needed for project X'
            }]->(k)
        """,
    },
    "BOOKMARKED": {
        "description": "User bookmarked knowledge unit for later",
        "properties": {
            "bookmarked_at": "DateTime when bookmarked",
            "bookmark_reason": "String reason for bookmark",
            "tags": "List[String] user-defined tags",
            "reminder_date": "Date optional reminder",
            "accessed_count": "Integer times accessed since bookmark",
        },
        "example_cypher": """
            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $knowledge_uid})
            CREATE (u)-[:BOOKMARKED {
                bookmarked_at: datetime(),
                bookmark_reason: 'reference_material',
                tags: ['important', 'review_later'],
                reminder_date: date() + duration('P14D'),
                accessed_count: 0
            }]->(k)
        """,
    },
    "COMPLETED": {
        "description": "User completed learning path or course",
        "properties": {
            "completed_at": "DateTime when completed",
            "duration_days": "Integer days taken to complete",
            "completion_score": "Float (0.0-1.0) final score/grade",
            "certificate_issued": "Boolean whether certificate was issued",
            "feedback_rating": "Integer (1-5) user's rating",
        },
        "example_cypher": """
            MATCH (u:User {uid: $user_uid}), (p:Lp {uid: $path_uid})
            CREATE (u)-[:COMPLETED {
                completed_at: datetime(),
                duration_days: 45,
                completion_score: 0.92,
                certificate_issued: true,
                feedback_rating: 5
            }]->(p)
        """,
    },
    "ENROLLED": {
        "description": "User enrolled in learning path or course",
        "properties": {
            "enrolled_at": "DateTime when enrolled",
            "target_completion": "Date target completion date",
            "enrollment_status": "String status (active, paused, cancelled)",
            "motivation_note": "String user's motivation for enrollment",
            "weekly_time_commitment": "Integer minutes per week committed",
        },
        "example_cypher": """
            MATCH (u:User {uid: $user_uid}), (p:Lp {uid: $path_uid})
            CREATE (u)-[:ENROLLED {
                enrolled_at: datetime(),
                target_completion: date() + duration('P60D'),
                enrollment_status: 'active',
                motivation_note: 'Career advancement',
                weekly_time_commitment: 300
            }]->(p)
        """,
    },
}


# ============================================================================
# SCHEMA INITIALIZATION & MIGRATION
# ============================================================================


class UserKnowledgeSchemaManager:
    """
    Manager for User-Knowledge relationship schema in Neo4j.

    Handles:
    - Schema initialization
    - Constraint creation
    - Index creation
    - Migration utilities
    """

    def __init__(self, driver: AsyncDriver) -> None:
        """
        Initialize schema manager.

        Args:
            driver: Neo4j async driver (required)

        Raises:
            ValueError: If driver is not provided
        """
        if not driver:
            raise ValueError("Neo4j driver is required - no fallback")

        self.driver = driver
        self.logger = logger

    async def initialize_schema(self) -> Result[dict[str, Any]]:
        """
        Initialize complete User-Knowledge relationship schema.

        Creates:
        - Constraints on User and Knowledge nodes
        - Indexes for relationship properties
        - Relationship type documentation

        Returns:
            Result with initialization summary
        """
        try:
            self.logger.info("🔧 Initializing User-Knowledge graph schema")

            summary = {
                "constraints_created": 0,
                "indexes_created": 0,
                "relationship_types_documented": len(USER_KNOWLEDGE_RELATIONSHIPS),
            }

            # Step 1: Ensure User node constraints
            user_constraints = await self._create_user_constraints()
            summary["constraints_created"] += user_constraints

            # Step 2: Create indexes on relationship properties
            relationship_indexes = await self._create_relationship_indexes()
            summary["indexes_created"] += relationship_indexes

            # Step 3: Validate schema
            validation = await self._validate_schema()
            summary["validation"] = validation

            self.logger.info(f"✅ Schema initialized: {summary}")

            return Result.ok(summary)

        except Exception as e:
            self.logger.error(f"❌ Schema initialization failed: {e}")
            return Result.fail(Errors.database(operation="initialize_schema", message=str(e)))

    async def _create_user_constraints(self) -> int:
        """Create constraints for User nodes."""
        constraints_created = 0

        async with self.driver.session() as session:
            # Unique constraint on User.uid
            try:
                await session.run("""
                    CREATE CONSTRAINT user_uid_unique IF NOT EXISTS
                    FOR (u:User) REQUIRE u.uid IS UNIQUE
                """)
                constraints_created += 1
                self.logger.debug("Created User.uid unique constraint")
            except Exception as e:
                self.logger.warning(f"User.uid constraint may already exist: {e}")

            # Ensure User.uid exists
            try:
                await session.run("""
                    CREATE CONSTRAINT user_uid_exists IF NOT EXISTS
                    FOR (u:User) REQUIRE u.uid IS NOT NULL
                """)
                constraints_created += 1
                self.logger.debug("Created User.uid NOT NULL constraint")
            except Exception as e:
                self.logger.warning(f"User.uid NOT NULL constraint may already exist: {e}")

        return constraints_created

    async def _create_relationship_indexes(self) -> int:
        """Create indexes on relationship properties for efficient queries."""
        indexes_created = 0

        async with self.driver.session() as session:
            # Index on MASTERED.mastery_score for filtering high-mastery knowledge
            try:
                await session.run("""
                    CREATE INDEX mastered_score IF NOT EXISTS
                    FOR ()-[r:MASTERED]-() ON (r.mastery_score)
                """)
                indexes_created += 1
            except Exception as e:
                self.logger.warning(f"MASTERED.mastery_score index issue: {e}")

            # Index on IN_PROGRESS.progress for tracking completion
            try:
                await session.run("""
                    CREATE INDEX in_progress_progress IF NOT EXISTS
                    FOR ()-[r:IN_PROGRESS]-() ON (r.progress)
                """)
                indexes_created += 1
            except Exception as e:
                self.logger.warning(f"IN_PROGRESS.progress index issue: {e}")

            # Index on NEEDS_REVIEW.next_review_due for spaced repetition queries
            try:
                await session.run("""
                    CREATE INDEX needs_review_due IF NOT EXISTS
                    FOR ()-[r:NEEDS_REVIEW]-() ON (r.next_review_due)
                """)
                indexes_created += 1
            except Exception as e:
                self.logger.warning(f"NEEDS_REVIEW.next_review_due index issue: {e}")

        return indexes_created

    async def _validate_schema(self) -> dict[str, Any]:
        """Validate schema is properly set up."""
        async with self.driver.session() as session:
            # Check constraints
            result = await session.run("SHOW CONSTRAINTS")
            constraints = [record async for record in result]

            # Check indexes
            result = await session.run("SHOW INDEXES")
            indexes = [record async for record in result]

            return {
                "constraint_count": len(constraints),
                "index_count": len(indexes),
                "ready": len(constraints) >= 2,  # At least User.uid constraints
            }

    async def create_sample_user_knowledge_graph(
        self, user_uid: str, knowledge_uids: list[str]
    ) -> Result[dict[str, Any]]:
        """
        Create sample User-Knowledge relationships for testing/demo.

        Args:
            user_uid: UID of user,
            knowledge_uids: List of knowledge UIDs to create relationships for

        Returns:
            Result with creation summary
        """
        try:
            self.logger.info(f"Creating sample User-Knowledge graph for {user_uid}")

            async with self.driver.session() as session:
                # Ensure user exists
                await session.run(
                    """
                    MERGE (u:User {uid: $user_uid})
                    ON CREATE SET u.username = 'sample_user', u.created_at = datetime()
                """,
                    {"user_uid": user_uid},
                )

                relationships_created = 0

                # Create varied relationships across knowledge units
                for i, ku_uid in enumerate(knowledge_uids):
                    # Verify knowledge exists
                    result = await session.run(
                        """
                        MATCH (k:Ku {uid: $ku_uid})
                        RETURN k.uid as uid
                    """,
                        {"ku_uid": ku_uid},
                    )

                    record = await result.single()
                    if not record:
                        self.logger.warning(f"Knowledge {ku_uid} not found, skipping")
                        continue

                    # Create different relationship types based on index
                    if i % 3 == 0:
                        # Mastered
                        await session.run(
                            """
                            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $ku_uid})
                            MERGE (u)-[r:MASTERED]->(k)
                            ON CREATE SET
                                r.mastery_score = 0.85 + (rand() * 0.15),
                                r.achieved_at = datetime() - duration('P' + toString(toInteger(rand() * 30)) + 'D'),
                                r.practice_count = toInteger(rand() * 20) + 5,
                                r.last_practiced = datetime() - duration('P' + toString(toInteger(rand() * 7)) + 'D'),
                                r.confidence_level = 0.8 + (rand() * 0.2),
                                r.retention_score = 0.7 + (rand() * 0.3)
                        """,
                            {"user_uid": user_uid, "ku_uid": ku_uid},
                        )
                        relationships_created += 1

                    elif i % 3 == 1:
                        # In Progress
                        await session.run(
                            """
                            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $ku_uid})
                            MERGE (u)-[r:IN_PROGRESS]->(k)
                            ON CREATE SET
                                r.progress = 0.2 + (rand() * 0.6),
                                r.started_at = datetime() - duration('P' + toString(toInteger(rand() * 14)) + 'D'),
                                r.estimated_completion = date() + duration('P' + toString(toInteger(rand() * 30)) + 'D'),
                                r.time_invested_minutes = toInteger(rand() * 180) + 30,
                                r.difficulty_rating = 0.3 + (rand() * 0.6),
                                r.last_accessed = datetime() - duration('P' + toString(toInteger(rand() * 3)) + 'D')
                        """,
                            {"user_uid": user_uid, "ku_uid": ku_uid},
                        )
                        relationships_created += 1

                    else:
                        # Interested In
                        await session.run(
                            """
                            MATCH (u:User {uid: $user_uid}), (k:Ku {uid: $ku_uid})
                            MERGE (u)-[r:INTERESTED_IN]->(k)
                            ON CREATE SET
                                r.interest_score = 0.6 + (rand() * 0.4),
                                r.expressed_at = datetime() - duration('P' + toString(toInteger(rand() * 5)) + 'D'),
                                r.interest_source = ['discovery', 'goal_alignment', 'recommendation'][toInteger(rand() * 3)],
                                r.priority = ['high', 'medium', 'low'][toInteger(rand() * 3)]
                        """,
                            {"user_uid": user_uid, "ku_uid": ku_uid},
                        )
                        relationships_created += 1

                self.logger.info(f"✅ Created {relationships_created} User-Knowledge relationships")

                return Result.ok(
                    {
                        "user_uid": user_uid,
                        "relationships_created": relationships_created,
                        "knowledge_count": len(knowledge_uids),
                    }
                )

        except Exception as e:
            self.logger.error(f"❌ Failed to create sample graph: {e}")
            return Result.fail(
                Errors.database(operation="create_sample_user_knowledge_graph", message=str(e))
            )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def initialize_user_knowledge_schema(driver: AsyncDriver) -> Result[dict[str, Any]]:
    """
    Initialize User-Knowledge schema (convenience function).

    Args:
        driver: Neo4j async driver

    Returns:
        Result with initialization summary
    """
    manager = UserKnowledgeSchemaManager(driver)
    return await manager.initialize_schema()


def get_relationship_documentation() -> dict[str, dict[str, Any]]:
    """
    Get complete documentation for User-Knowledge relationships.

    Returns:
        Dictionary mapping relationship types to their documentation
    """
    return USER_KNOWLEDGE_RELATIONSHIPS.copy()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "USER_KNOWLEDGE_RELATIONSHIPS",
    "UserKnowledgeSchemaManager",
    "get_relationship_documentation",
    "initialize_user_knowledge_schema",
]

"""
User Backend - Dedicated Identity Management
============================================

Specialized backend for User entity persistence and retrieval.

**Architectural Rationale (November 4, 2025):**

User is NOT an activity domain - it's the foundation/identity layer that all domains reference.

Unlike activity domains (Task, Goal, Habit), User:
- Has no DTO conversion lifecycle (from_dto/to_dto)
- Is created via factory functions (create_user), not rebuilt from DTOs
- Delegates rich state to UserContext (not stored in User itself)
- Focuses on identity persistence, not activity CRUD

Therefore, User uses a dedicated backend instead of UniversalNeo4jBackend:
- UniversalNeo4jBackend → Activity domains (requires DomainModelProtocol)
- UserBackend → Identity/foundation (User-specific operations)

This is similar to how Reports uses a specialized approach (meta-service, not domain).

See Also:
- CLAUDE.md §2.11 Domain Architecture Categories
- /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
- /docs/USER_MODEL_ARCHITECTURE.md
"""

from typing import Any

from core.models.user import User
from core.utils.logging import get_logger
from core.utils.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class UserBackend:
    """
    Dedicated backend for User identity management.

    Focuses on identity operations:
    - User creation (identity establishment)
    - User retrieval (by UID, username, email)
    - User updates (profile changes, preferences)
    - User deletion (account removal)

    Does NOT handle:
    - Activity domain CRUD (handled by domain-specific backends)
    - Rich context building (handled by UserService → UserContext)
    - Statistical aggregation (handled by ProfileHubData)
    """

    def __init__(self, driver: Any) -> None:
        """
        Initialize User backend.

        Args:
            driver: Neo4j driver for database operations
        """
        self.driver = driver
        self.label = "User"
        self.logger = logger

    # ========================================================================
    # IDENTITY OPERATIONS - UserOperations Protocol
    # ========================================================================

    async def create_user(self, user: User) -> Result[User]:
        """
        Create a new user identity.

        Args:
            user: User domain model (frozen dataclass)

        Returns:
            Result[User]: Created user or error
        """
        try:
            # Convert User to Neo4j properties
            user_dict = to_neo4j_node(user)

            query = f"""
            CREATE (u:{self.label})
            SET u = $properties
            RETURN u
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"properties": user_dict})
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="create_user", message="Failed to create user node"
                        )
                    )

                # Convert back to User domain model
                created_user = from_neo4j_node(dict(record["u"]), User)
                self.logger.info(f"Created user identity: {created_user.uid}")
                return Result.ok(created_user)

        except Exception as e:
            self.logger.error(f"Failed to create user: {e}")
            return Result.fail(Errors.database(operation="create_user", message=str(e)))

    async def get_user_by_uid(self, user_uid: str) -> Result[User | None]:
        """
        Get user by UID.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[User | None]: User if found, None otherwise
        """
        try:
            query = f"""
            MATCH (u:{self.label} {{uid: $uid}})
            RETURN u
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"uid": user_uid})
                record = await result.single()

                if not record:
                    return Result.ok(None)

                user = from_neo4j_node(dict(record["u"]), User)
                return Result.ok(user)

        except Exception as e:
            self.logger.error(f"Failed to get user by UID: {e}")
            return Result.fail(Errors.database(operation="get_user_by_uid", message=str(e)))

    async def get_user_by_username(self, username: str) -> Result[User | None]:
        """
        Get user by username.

        Args:
            username: Username to search for

        Returns:
            Result[User | None]: User if found, None otherwise
        """
        try:
            query = f"""
            MATCH (u:{self.label} {{username: $username}})
            RETURN u
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"username": username})
                record = await result.single()

                if not record:
                    return Result.ok(None)

                user = from_neo4j_node(dict(record["u"]), User)
                return Result.ok(user)

        except Exception as e:
            self.logger.error(f"Failed to get user by username: {e}")
            return Result.fail(Errors.database(operation="get_user_by_username", message=str(e)))

    async def get_user_by_email(self, email: str) -> Result[User | None]:
        """
        Get user by email address.

        Used by graph-native authentication for login.

        Args:
            email: Email address to search for

        Returns:
            Result[User | None]: User if found, None otherwise
        """
        try:
            query = f"""
            MATCH (u:{self.label} {{email: $email}})
            RETURN u
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"email": email})
                record = await result.single()

                if not record:
                    return Result.ok(None)

                user = from_neo4j_node(dict(record["u"]), User)
                return Result.ok(user)

        except Exception as e:
            self.logger.error(f"Failed to get user by email: {e}")
            return Result.fail(Errors.database(operation="get_user_by_email", message=str(e)))

    async def update_user(self, user: User) -> Result[User]:
        """
        Update user identity.

        Args:
            user: Updated User domain model

        Returns:
            Result[User]: Updated user or error
        """
        try:
            # Convert User to Neo4j properties
            user_dict = to_neo4j_node(user)
            uid = user_dict.get("uid")

            if not uid:
                return Result.fail(
                    Errors.validation(message="User must have uid", field="uid", value=None)
                )

            # Remove uid from updates (it's the match key)
            updates = {k: v for k, v in user_dict.items() if k != "uid"}

            query = f"""
            MATCH (u:{self.label} {{uid: $uid}})
            SET u += $updates
            RETURN u
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"uid": uid, "updates": updates})
                record = await result.single()

                if not record:
                    return Result.fail(Errors.not_found(resource="User", identifier=uid))

                updated_user = from_neo4j_node(dict(record["u"]), User)
                self.logger.info(f"Updated user identity: {uid}")
                return Result.ok(updated_user)

        except Exception as e:
            self.logger.error(f"Failed to update user: {e}")
            return Result.fail(Errors.database(operation="update_user", message=str(e)))

    async def delete_user(self, user_uid: str) -> Result[bool]:
        """
        DETACH DELETE user identity and all relationships.

        Args:
            user_uid: UID of user to DETACH DELETE

        Returns:
            Result[bool]: True if deleted, False if not found
        """
        try:
            query = f"""
            MATCH (u:{self.label} {{uid: $uid}})
            DETACH DELETE u
            RETURN count(u) as deleted_count
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"uid": user_uid})
                record = await result.single()

                deleted = record["deleted_count"] > 0 if record else False

                if deleted:
                    self.logger.info(f"Deleted user identity: {user_uid}")
                else:
                    self.logger.warning(f"User not found for deletion: {user_uid}")

                return Result.ok(deleted)

        except Exception as e:
            self.logger.error(f"Failed to delete user: {e}")
            return Result.fail(Errors.database(operation="delete_user", message=str(e)))

    # ========================================================================
    # ALIAS METHODS - UserOperations Protocol
    # ========================================================================

    async def get(self, user_uid: str) -> Result[User | None]:
        """
        Get user by UID (alias for get_user_by_uid).

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[User | None]: User if found, None otherwise
        """
        return await self.get_user_by_uid(user_uid)

    # ========================================================================
    # LEARNING & PROGRESS TRACKING
    # ========================================================================
    # These methods manage User-Knowledge relationships in the graph

    async def update_user_progress(
        self, user_uid: str, progress_updates: dict[str, Any]
    ) -> Result[bool]:
        """
        Update user's learning progress.

        This updates metadata on the User node itself, not relationships.
        For relationship-based progress tracking, use record_knowledge_mastery.

        Args:
            user_uid: User UID
            progress_updates: Progress metadata to update

        Returns:
            Result[bool]: Success status
        """
        try:
            query = f"""
            MATCH (u:{self.label} {{uid: $uid}})
            SET u += $updates
            RETURN u
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"uid": user_uid, "updates": progress_updates})
                record = await result.single()

                if not record:
                    return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

                self.logger.info(f"Updated user progress: {user_uid}")
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to update user progress: {e}")
            return Result.fail(Errors.database(operation="update_user_progress", message=str(e)))

    async def record_knowledge_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
    ) -> Result[bool]:
        """
        Record user's mastery of a knowledge unit.

        Creates/updates (User)-[:MASTERED]->(Knowledge) relationship.

        Args:
            user_uid: User UID
            knowledge_uid: Knowledge unit UID
            mastery_score: Mastery level (0.0-1.0)
            practice_count: Number of practice sessions
            confidence_level: Confidence in mastery assessment

        Returns:
            Result[bool]: Success status
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:MASTERED]->(k)
            SET r.mastery_score = $mastery_score,
                r.practice_count = $practice_count,
                r.confidence_level = $confidence_level,
                r.last_practiced = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "mastery_score": mastery_score,
                        "practice_count": practice_count,
                        "confidence_level": confidence_level,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="record_knowledge_mastery",
                            message="Failed to create mastery relationship",
                        )
                    )

                self.logger.info(
                    f"Recorded mastery: {user_uid} → {knowledge_uid} ({mastery_score:.2f})"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to record knowledge mastery: {e}")
            return Result.fail(
                Errors.database(operation="record_knowledge_mastery", message=str(e))
            )

    async def record_knowledge_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """
        Record user's progress on a knowledge unit.

        Creates/updates (User)-[:LEARNING]->(Knowledge) relationship.

        Args:
            user_uid: User UID
            knowledge_uid: Knowledge unit UID
            progress: Progress value (0.0-1.0)
            time_invested_minutes: Time spent learning (minutes)
            difficulty_rating: User's perceived difficulty (0.0-1.0)

        Returns:
            Result[bool]: Success status
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:LEARNING]->(k)
            SET r.progress = $progress,
                r.time_invested_minutes = coalesce(r.time_invested_minutes, 0) + $time_invested_minutes,
                r.difficulty_rating = $difficulty_rating,
                r.last_updated = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "progress": progress,
                        "time_invested_minutes": time_invested_minutes,
                        "difficulty_rating": difficulty_rating,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="record_knowledge_progress",
                            message="Failed to create learning relationship",
                        )
                    )

                self.logger.info(f"Recorded progress: {user_uid} → {knowledge_uid} ({progress})")
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to record knowledge progress: {e}")
            return Result.fail(
                Errors.database(operation="record_knowledge_progress", message=str(e))
            )

    async def get_user_mastery(
        self,
        user_uid: str,
        concept_uid: str,
    ) -> Result[float]:
        """
        Get user's mastery level for a knowledge concept.

        Args:
            user_uid: User UID
            concept_uid: Knowledge unit UID

        Returns:
            Result[float]: Mastery score (0.0-1.0), or 0.0 if not found
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[r:MASTERED]->(k:Entity {uid: $concept_uid})
            RETURN r.mastery_score as mastery_score
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {"user_uid": user_uid, "concept_uid": concept_uid},
                )
                record = await result.single()

                if not record:
                    # No mastery recorded means 0.0 mastery
                    return Result.ok(0.0)

                mastery_score: float = record["mastery_score"]
                return Result.ok(mastery_score)

        except Exception as e:
            self.logger.error(f"Failed to get user mastery: {e}")
            return Result.fail(Errors.database(operation="get_user_mastery", message=str(e)))

    async def enroll_in_learning_path(
        self,
        user_uid: str,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """
        Enroll user in a learning path.

        Creates (User)-[:ENROLLED_IN]->(LearningPath) relationship.

        Args:
            user_uid: User UID
            learning_path_uid: Learning path UID
            target_completion: Target completion date (ISO format)
            weekly_time_commitment: Minutes per week committed
            motivation_note: User's motivation for enrolling

        Returns:
            Result[bool]: Success status
        """
        try:
            from datetime import datetime

            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (lp:Lp {uid: $learning_path_uid})
            MERGE (u)-[r:ENROLLED_IN]->(lp)
            SET r.enrolled_at = coalesce(r.enrolled_at, datetime()),
                r.target_completion = $target_completion,
                r.weekly_time_commitment = $weekly_time_commitment,
                r.motivation_note = $motivation_note,
                r.status = 'active'
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "learning_path_uid": learning_path_uid,
                        "target_completion": target_completion or datetime.now().isoformat(),
                        "weekly_time_commitment": weekly_time_commitment,
                        "motivation_note": motivation_note,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="enroll_in_learning_path",
                            message="Failed to create enrollment",
                        )
                    )

                self.logger.info(f"Enrolled user in path: {user_uid} → {learning_path_uid}")
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to enroll in learning path: {e}")
            return Result.fail(Errors.database(operation="enroll_in_learning_path", message=str(e)))

    async def complete_learning_path_graph(
        self,
        user_uid: str,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """
        Mark learning path as completed.

        Updates (User)-[:ENROLLED_IN]->(LearningPath) relationship.

        Args:
            user_uid: User UID
            learning_path_uid: Learning path UID
            completion_score: Final completion score (0.0-1.0)
            feedback_rating: User's rating of the path (1-5)

        Returns:
            Result[bool]: Success status
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[r:ENROLLED_IN]->(lp:Lp {uid: $learning_path_uid})
            SET r.status = 'completed',
                r.completed_at = datetime(),
                r.completion_score = $completion_score,
                r.feedback_rating = $feedback_rating
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "learning_path_uid": learning_path_uid,
                        "completion_score": completion_score,
                        "feedback_rating": feedback_rating,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            resource="Enrollment",
                            identifier=f"{user_uid} → {learning_path_uid}",
                        )
                    )

                self.logger.info(f"Completed learning path: {user_uid} → {learning_path_uid}")
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to complete learning path: {e}")
            return Result.fail(
                Errors.database(operation="complete_learning_path_graph", message=str(e))
            )

    async def express_interest_in_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        interest_score: float = 0.8,
        interest_source: str = "discovery",
        priority: str = "medium",
        notes: str = "",
    ) -> Result[bool]:
        """
        Record user's interest in a knowledge unit.

        Creates (User)-[:INTERESTED_IN]->(Knowledge) relationship.

        Args:
            user_uid: User UID
            knowledge_uid: Knowledge unit UID
            interest_score: Interest level (0.0-1.0)
            interest_source: Source of interest (discovery, goal, recommendation, manual)
            priority: Priority level (high, medium, low)
            notes: Optional notes about the interest

        Returns:
            Result[bool]: Success status
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:INTERESTED_IN]->(k)
            SET r.interest_score = $interest_score,
                r.interest_source = $interest_source,
                r.priority = $priority,
                r.notes = $notes,
                r.expressed_at = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "interest_score": interest_score,
                        "interest_source": interest_source,
                        "priority": priority,
                        "notes": notes,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="express_interest_in_knowledge",
                            message="Failed to create interest relationship",
                        )
                    )

                self.logger.info(
                    f"Expressed interest: {user_uid} → {knowledge_uid} ({interest_score})"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to express interest: {e}")
            return Result.fail(
                Errors.database(operation="express_interest_in_knowledge", message=str(e))
            )

    async def bookmark_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: list | None = None,
        reminder_date: str | None = None,
    ) -> Result[bool]:
        """
        Bookmark a knowledge unit for later review.

        Creates (User)-[:BOOKMARKED]->(Knowledge) relationship.

        Args:
            user_uid: User UID
            knowledge_uid: Knowledge unit UID
            bookmark_reason: Reason for bookmarking (reference, review_later, important)
            tags: Optional list of tags for categorization
            reminder_date: Optional reminder date (ISO format)

        Returns:
            Result[bool]: Success status
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:BOOKMARKED]->(k)
            SET r.bookmarked_at = datetime(),
                r.bookmark_reason = $bookmark_reason,
                r.tags = $tags,
                r.reminder_date = $reminder_date
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "bookmark_reason": bookmark_reason,
                        "tags": tags or [],
                        "reminder_date": reminder_date,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="bookmark_knowledge",
                            message="Failed to create bookmark",
                        )
                    )

                self.logger.info(f"Bookmarked: {user_uid} → {knowledge_uid}")
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to bookmark knowledge: {e}")
            return Result.fail(Errors.database(operation="bookmark_knowledge", message=str(e)))

    # ========================================================================
    # ACTIVITY & CONVERSATION TRACKING
    # ========================================================================

    async def update_user_activity(
        self, user_uid: str, activity_updates: dict[str, Any]
    ) -> Result[bool]:
        """
        Update user activity metadata.

        Args:
            user_uid: User UID
            activity_updates: Activity data to update

        Returns:
            Result[bool]: Success status
        """
        try:
            from datetime import datetime

            # Add last_active timestamp
            activity_updates["last_active_at"] = datetime.now().isoformat()

            query = f"""
            MATCH (u:{self.label} {{uid: $uid}})
            SET u += $updates
            RETURN u
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"uid": user_uid, "updates": activity_updates})
                record = await result.single()

                if not record:
                    return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to update user activity: {e}")
            return Result.fail(Errors.database(operation="update_user_activity", message=str(e)))

    async def add_conversation_message(
        self,
        user_uid: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Add a message to user's conversation history.

        Creates a ConversationMessage node linked to User.

        Args:
            user_uid: User UID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata

        Returns:
            Result[bool]: Success status
        """
        try:
            from uuid import uuid4

            message_uid = f"msg_{uuid4().hex[:12]}"

            query = """
            MATCH (u:User {uid: $user_uid})
            CREATE (m:ConversationMessage {
                uid: $message_uid,
                role: $role,
                content: $content,
                timestamp: datetime(),
                metadata: $metadata
            })
            CREATE (u)-[:HAS_MESSAGE]->(m)
            RETURN m
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "message_uid": message_uid,
                        "role": role,
                        "content": content,
                        "metadata": metadata or {},
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="add_conversation_message",
                            message="Failed to create message",
                        )
                    )

                self.logger.info(f"Added conversation message: {user_uid} ({role})")
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to add conversation message: {e}")
            return Result.fail(
                Errors.database(operation="add_conversation_message", message=str(e))
            )

    # ========================================================================
    # QUERY HELPERS - Additional lookups
    # ========================================================================

    async def find_by(self, **filters: Any) -> Result[list[User]]:
        """
        Find users by arbitrary filters.

        Args:
            **filters: Field filters (e.g., email="test@example.com")

        Returns:
            Result[list[User]]: Matching users
        """
        try:
            # Build WHERE clause from filters
            where_clauses = [f"u.{key} = ${key}" for key in filters]
            where_str = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
            MATCH (u:{self.label})
            WHERE {where_str}
            RETURN u
            """

            async with self.driver.session() as session:
                result = await session.run(query, filters)
                records = [record async for record in result]

                users = [from_neo4j_node(dict(record["u"]), User) for record in records]
                return Result.ok(users)

        except Exception as e:
            self.logger.error(f"Failed to find users: {e}")
            return Result.fail(Errors.database(operation="find_by", message=str(e)))

    async def get_active_learners(
        self, since_hours: int = 24, limit: int = 100
    ) -> Result[list[User]]:
        """
        Get users active in learning within time window.

        Args:
            since_hours: Hours to look back
            limit: Maximum users to return

        Returns:
            Result[list[User]]: Active learners
        """
        try:
            query = """
            MATCH (u:User)-[r:LEARNING|MASTERED]->(k:Entity)
            WHERE r.last_updated >= datetime() - duration({hours: $hours})
               OR r.last_practiced >= datetime() - duration({hours: $hours})
            WITH DISTINCT u
            RETURN u
            ORDER BY u.last_active_at DESC
            LIMIT $limit
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"hours": since_hours, "limit": limit})
                records = [record async for record in result]

                users = [from_neo4j_node(dict(record["u"]), User) for record in records]
                return Result.ok(users)

        except Exception as e:
            self.logger.error(f"Failed to get active learners: {e}")
            return Result.fail(Errors.database(operation="get_active_learners", message=str(e)))

    async def get_user_context(self, _user_uid: str) -> Result[Any]:
        """Get user context — delegated to UserService at runtime, not a backend operation."""
        return Result.fail(
            Errors.business(
                "not_supported",
                "get_user_context is a UserService operation, not a backend operation. "
                "Use services.user_service.get_user_context() instead.",
            )
        )

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

from datetime import UTC, datetime
from typing import Any

from neo4j import AsyncDriver

from adapters.persistence.neo4j._dual_track_checkin_store import atomic_append_checkin
from core.models.enums.user_enums import UserStatus
from core.models.type_hints import UserUID
from core.models.user import User
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)

# Append-only User properties that are managed EXCLUSIVELY via the atomic
# `atomic_append_dual_track_checkin` path and must never be written by a whole-model
# write. A full `update_user`/`create_user` serializes every field, so without this
# guard a stale whole-model write (e.g. a preferences/session update that read the
# user before a dual-track check-in but commits after it) would clobber the
# just-persisted log. Excluding them here makes the race impossible in BOTH
# directions (ADR-030). See `update_user` / `atomic_append_dual_track_checkin` below.
_APPEND_ONLY_FIELDS: frozenset[str] = frozenset({"dual_track_checkins"})


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

    def __init__(self, driver: AsyncDriver) -> None:
        """
        Initialize User backend.

        Args:
            driver: Neo4j async driver
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
            # Convert User to Neo4j properties. Append-only fields are managed solely
            # via atomic_append_dual_track_checkin, never seeded by a whole-model write.
            user_dict = {
                k: v for k, v in to_neo4j_node(user).items() if k not in _APPEND_ONLY_FIELDS
            }

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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to create user: {e}")
            return Result.fail(Errors.database(operation="create_user", message=str(e)))

    async def get_user_by_uid(self, user_uid: UserUID) -> Result[User | None]:
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

        except NEO4J_EXCEPTIONS as e:
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

        except NEO4J_EXCEPTIONS as e:
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

        except NEO4J_EXCEPTIONS as e:
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

            # Remove uid (match key) and append-only fields (managed solely via
            # update_user_fields — a whole-model write must never clobber them).
            updates = {
                k: v for k, v in user_dict.items() if k != "uid" and k not in _APPEND_ONLY_FIELDS
            }

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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to update user: {e}")
            return Result.fail(Errors.database(operation="update_user", message=str(e)))

    async def atomic_append_dual_track_checkin(
        self,
        user_uid: UserUID,
        snapshot: dict[str, Any],
        history_limit: int,
        dimension: str,
    ) -> Result[bool]:
        """Atomically append a user-level dual-track check-in snapshot (ADR-030).

        Node-lock-serialized so two near-simultaneous check-ins for the SAME user
        can't lose a snapshot (the read-modify-write of the JSON ``dual_track_checkins``
        log runs under a Neo4j node write-lock). User-level dims are keyed by
        ``dimension`` (productivity/engagement/decision_quality) within the
        ``dict[str, list[dict]]`` log on the ``:User`` node — concurrent appends to
        different dimensions are still serialized on the same node, both retained.

        Backend: ``_dual_track_checkin_store.atomic_append_checkin`` (dimension-keyed).

        Args:
            user_uid: User UID.
            snapshot: ``DualTrackResult.to_checkin_snapshot`` dict.
            history_limit: Max snapshots retained per dimension (oldest dropped).
            dimension: ``DualTrackDimension`` value the snapshot belongs to.

        Returns:
            Result[bool]: True if appended, NotFound if the user does not exist.
        """
        try:
            appended = await atomic_append_checkin(
                self.driver,
                label=self.label,
                uid=user_uid,
                snapshot=snapshot,
                history_limit=history_limit,
                dimension=dimension,
            )
            if not appended:
                return Result.fail(Errors.not_found(resource="User", identifier=user_uid))
            return Result.ok(True)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to append dual-track check-in: {e}")
            return Result.fail(
                Errors.database(operation="atomic_append_dual_track_checkin", message=str(e))
            )

    async def delete_user(self, user_uid: UserUID) -> Result[bool]:
        """
        Soft-delete the User node: mark status=DELETED, scrub PII, preserve graph.

        The node + every OWNS-linked entity (UserEntry, Task, Goal, Habit, ...)
        are kept so teachers can still render historical submissions and
        analytics stay intact. Login is blocked via ``is_active=false`` which
        ``UserCoreService.authenticate`` already rejects.

        For GDPR right-to-erasure (wipe the node + cascade over OWNS), use
        ``hard_delete_user`` instead — admin-gated separate path.

        Args:
            user_uid: UID of user to soft-delete

        Returns:
            Result[bool]: True if the user was marked deleted, False if the
            UID did not match an existing user.
        """
        try:
            now_iso = datetime.now(UTC).isoformat()
            query = f"""
            MATCH (u:{self.label} {{uid: $uid}})
            SET u.status = $deleted_status,
                u.is_active = false,
                u.deleted_at = datetime($now),
                u.email = null,
                u.display_name = 'Deleted User',
                u.password_hash = ''
            RETURN count(u) as deleted_count
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "uid": user_uid,
                        "deleted_status": UserStatus.DELETED.value,
                        "now": now_iso,
                    },
                )
                record = await result.single()

                deleted = record["deleted_count"] > 0 if record else False

                if deleted:
                    self.logger.info(f"Soft-deleted user identity: {user_uid}")
                else:
                    self.logger.warning(f"User not found for soft-delete: {user_uid}")

                return Result.ok(deleted)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to soft-delete user: {e}")
            return Result.fail(Errors.database(operation="delete_user", message=str(e)))

    async def hard_delete_user(self, user_uid: UserUID) -> Result[int]:
        """
        GDPR right-to-erasure: DETACH DELETE the user + every OWNS-linked entity.

        Destroys the User node and cascades through every :OWNS edge, removing
        the user's UserEntry / Task / Goal / Habit / ... nodes as well. Use
        only when compliance requires full erasure — the default account
        closure path is ``delete_user`` (soft-delete, keeps history).

        The service layer MUST gate this on ``UserRole.ADMIN`` before calling;
        the backend does not re-check role (it has no user context).

        Args:
            user_uid: UID of user to erase

        Returns:
            Result[int]: Total nodes deleted (user + every OWNS-linked entity).
            0 when the UID does not match an existing user.
        """
        try:
            query = f"""
            MATCH (u:{self.label} {{uid: $uid}})
            OPTIONAL MATCH (u)-[:OWNS]->(owned)
            WITH u, collect(owned) AS owned_nodes
            WITH u, owned_nodes, size(owned_nodes) AS owned_count
            DETACH DELETE u
            FOREACH (n IN owned_nodes | DETACH DELETE n)
            RETURN owned_count + 1 AS deleted_count
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"uid": user_uid})
                record = await result.single()

                deleted_count: int = record["deleted_count"] if record else 0

                if deleted_count > 0:
                    self.logger.warning(
                        f"Hard-deleted user {user_uid}: {deleted_count} nodes erased "
                        f"(user + {deleted_count - 1} owned entities)"
                    )
                else:
                    self.logger.warning(f"User not found for hard-delete: {user_uid}")

                return Result.ok(deleted_count)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to hard-delete user: {e}")
            return Result.fail(Errors.database(operation="hard_delete_user", message=str(e)))

    # ========================================================================
    # LEARNING & PROGRESS TRACKING
    # ========================================================================
    # These methods manage User-Knowledge relationships in the graph

    async def update_user_progress(
        self, user_uid: UserUID, progress_updates: dict[str, Any]
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to update user progress: {e}")
            return Result.fail(Errors.database(operation="update_user_progress", message=str(e)))

    async def record_knowledge_mastery(
        self,
        user_uid: UserUID,
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to record knowledge mastery: {e}")
            return Result.fail(
                Errors.database(operation="record_knowledge_mastery", message=str(e))
            )

    async def record_knowledge_progress(
        self,
        user_uid: UserUID,
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to record knowledge progress: {e}")
            return Result.fail(
                Errors.database(operation="record_knowledge_progress", message=str(e))
            )

    async def get_user_mastery(
        self,
        user_uid: UserUID,
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to get user mastery: {e}")
            return Result.fail(Errors.database(operation="get_user_mastery", message=str(e)))

    async def enroll_in_learning_path(
        self,
        user_uid: UserUID,
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to enroll in learning path: {e}")
            return Result.fail(Errors.database(operation="enroll_in_learning_path", message=str(e)))

    async def complete_learning_path(
        self,
        user_uid: UserUID,
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to complete learning path: {e}")
            return Result.fail(Errors.database(operation="complete_learning_path", message=str(e)))

    async def express_interest_in_knowledge(
        self,
        user_uid: UserUID,
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to express interest: {e}")
            return Result.fail(
                Errors.database(operation="express_interest_in_knowledge", message=str(e))
            )

    async def bookmark_knowledge(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: list[str] | None = None,
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to bookmark knowledge: {e}")
            return Result.fail(Errors.database(operation="bookmark_knowledge", message=str(e)))

    # ========================================================================
    # ACTIVITY & CONVERSATION TRACKING
    # ========================================================================

    async def update_user_activity(
        self, user_uid: UserUID, activity_updates: dict[str, Any]
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to update user activity: {e}")
            return Result.fail(Errors.database(operation="update_user_activity", message=str(e)))

    async def add_conversation_message(
        self,
        user_uid: UserUID,
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

        except NEO4J_EXCEPTIONS as e:
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

        except NEO4J_EXCEPTIONS as e:
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

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Failed to get active learners: {e}")
            return Result.fail(Errors.database(operation="get_active_learners", message=str(e)))

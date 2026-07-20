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
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from adapters.persistence.neo4j.session_runner import Neo4jSessionRunner
from core.models.enums.user_enums import UserStatus
from core.models.type_hints import UserUID
from core.models.user import User
from core.utils.error_boundary import safe_backend_operation
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)

# Append-only User properties that are managed EXCLUSIVELY via the atomic
# `atomic_append_dual_track_checkin` path and must never be written by a whole-model
# write. A full `update_user`/`create_user` serializes every field, so without this
# guard a stale whole-model write (e.g. a preferences/session update that read the
# user before a dual-track check-in but commits after it) would clobber the
# just-persisted log. Excluding them here makes the race impossible in BOTH
# directions (ADR-030). See `update_user` / `atomic_append_dual_track_checkin` below.
_APPEND_ONLY_FIELDS: frozenset[str] = frozenset({"dual_track_checkins", "knowledge_checkins"})


class UserBackend(Neo4jSessionRunner):
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

    Error boundary: every public method is wrapped in @safe_backend_operation,
    which converts Neo4j exceptions to Result.fail(Errors.database(...)).
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
    # PRIVATE HELPERS
    # ========================================================================

    async def _get_user_by(self, prop: str, value: str) -> Result[User | None]:
        """
        Fetch a single user matching one node property.

        THE shared body of the get_user_by_{uid,username,email} triple.
        ``prop`` is a backend-internal literal ("uid" / "title" / "email"),
        never caller input — injection-safe. Exceptions propagate to the
        caller's @safe_backend_operation decorator.
        """
        query = f"""
        MATCH (u:{self.label} {{{prop}: $value}})
        RETURN u
        """

        record = await self._run_single(query, {"value": value})

        if not record:
            return Result.ok(None)
        return Result.ok(from_neo4j_node(dict(record["u"]), User))

    async def _merge_user_edge(
        self,
        user_uid: UserUID,
        target_uid: str,
        rel_type: str,
        set_clause: str,
        params: dict[str, Any],
        target_label: str = "Entity",
    ) -> bool:
        """
        MERGE a ``(User)-[rel_type]->(target)`` edge and apply a SET clause.

        THE shared body of the five user-edge writers (MASTERED / IN_PROGRESS /
        ENROLLED_IN / INTERESTED_IN / BOOKMARKED). ``rel_type``,
        ``set_clause`` and ``target_label`` are backend-internal literals
        (injection-safe); every value inside ``set_clause`` is parameterized.

        Returns True when the edge was merged, False when a MATCH found no
        user/target node — callers translate False into their own error
        surface. Exceptions propagate to the caller's @safe_backend_operation
        decorator.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (t:{target_label} {{uid: $target_uid}})
        MERGE (u)-[r:{rel_type}]->(t)
        SET {set_clause}
        RETURN r
        """

        record = await self._run_single(
            query, {"user_uid": user_uid, "target_uid": target_uid, **params}
        )

        return record is not None

    # ========================================================================
    # IDENTITY OPERATIONS - UserOperations Protocol
    # ========================================================================

    @safe_backend_operation("create_user")
    async def create_user(self, user: User) -> Result[User]:
        """
        Create a new user identity.

        Args:
            user: User domain model (frozen dataclass)

        Returns:
            Result[User]: Created user or error
        """
        # Convert User to Neo4j properties. Append-only fields are managed solely
        # via atomic_append_dual_track_checkin, never seeded by a whole-model write.
        user_dict = {k: v for k, v in to_neo4j_node(user).items() if k not in _APPEND_ONLY_FIELDS}

        query = f"""
        CREATE (u:{self.label})
        SET u = $properties
        RETURN u
        """

        record = await self._run_single(query, {"properties": user_dict})

        if not record:
            return Result.fail(
                Errors.database(operation="create_user", message="Failed to create user node")
            )

        # Convert back to User domain model
        created_user = from_neo4j_node(dict(record["u"]), User)
        self.logger.info(f"Created user identity: {created_user.uid}")
        return Result.ok(created_user)

    @safe_backend_operation("get_user_by_uid")
    async def get_user_by_uid(self, user_uid: UserUID) -> Result[User | None]:
        """
        Get user by UID.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[User | None]: User if found, None otherwise
        """
        return await self._get_user_by("uid", user_uid)

    @safe_backend_operation("get_user_by_username")
    async def get_user_by_username(self, username: str) -> Result[User | None]:
        """
        Get user by username.

        The User model stores the username in ``title`` (``create_user``:
        ``uid=f"user_{username}", title=username``; the profile DTO maps
        ``username=user.title``). Matching a ``username`` node property here
        found nothing for any sign-up-created account — that property never
        existed outside one legacy admin node (migrated 2026-06-12).

        Args:
            username: Username to search for

        Returns:
            Result[User | None]: User if found, None otherwise
        """
        return await self._get_user_by("title", username)

    @safe_backend_operation("get_user_by_email")
    async def get_user_by_email(self, email: str) -> Result[User | None]:
        """
        Get user by email address.

        Used by graph-native authentication for login.

        Args:
            email: Email address to search for

        Returns:
            Result[User | None]: User if found, None otherwise
        """
        return await self._get_user_by("email", email)

    @safe_backend_operation("update_user")
    async def update_user(self, user: User) -> Result[User]:
        """
        Update user identity.

        Args:
            user: Updated User domain model

        Returns:
            Result[User]: Updated user or error
        """
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

        record = await self._run_single(query, {"uid": uid, "updates": updates})

        if not record:
            return Result.fail(Errors.not_found(resource="User", identifier=uid))

        updated_user = from_neo4j_node(dict(record["u"]), User)
        self.logger.info(f"Updated user identity: {uid}")
        return Result.ok(updated_user)

    @safe_backend_operation("atomic_append_dual_track_checkin")
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

    @safe_backend_operation("atomic_append_knowledge_checkin")
    async def atomic_append_knowledge_checkin(
        self,
        user_uid: UserUID,
        snapshot: dict[str, Any],
        history_limit: int,
        ku_uid: str,
    ) -> Result[bool]:
        """Atomically append a Knowledge dual-track check-in snapshot (ADR-030).

        The Knowledge dimension is per-(user, Ku). A Ku is SHARED/public curriculum,
        so its mastery check-ins live on the ``:User`` node keyed by ``ku_uid`` within
        the ``knowledge_checkins`` ``dict[str, list[dict]]`` log — a separate property
        from ``dual_track_checkins`` so the open-ended per-Ku keys never collide with
        the three fixed user-level dimensions.

        Node-lock-serialized so two near-simultaneous mastery check-ins for the SAME
        (user, Ku) can't lose a snapshot (the read-modify-write of the JSON log runs
        under a Neo4j node write-lock).

        Backend: ``_dual_track_checkin_store.atomic_append_checkin`` (key=``ku_uid``,
        property=``knowledge_checkins``).

        Args:
            user_uid: User UID.
            snapshot: ``DualTrackResult.to_checkin_snapshot`` dict.
            history_limit: Max snapshots retained per Ku (oldest dropped).
            ku_uid: The Ku the mastery self-rating belongs to.

        Returns:
            Result[bool]: True if appended, NotFound if the user does not exist.
        """
        appended = await atomic_append_checkin(
            self.driver,
            label=self.label,
            uid=user_uid,
            snapshot=snapshot,
            history_limit=history_limit,
            dimension=ku_uid,
            property_name="knowledge_checkins",
        )
        if not appended:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))
        return Result.ok(True)

    @safe_backend_operation("delete_user")
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

        record = await self._run_single(
            query,
            {
                "uid": user_uid,
                "deleted_status": UserStatus.DELETED.value,
                "now": now_iso,
            },
        )

        deleted = record["deleted_count"] > 0 if record else False

        if deleted:
            self.logger.info(f"Soft-deleted user identity: {user_uid}")
        else:
            self.logger.warning(f"User not found for soft-delete: {user_uid}")

        return Result.ok(deleted)

    @safe_backend_operation("hard_delete_user")
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
        query = f"""
        MATCH (u:{self.label} {{uid: $uid}})
        OPTIONAL MATCH (u)-[:OWNS]->(owned)
        WITH u, collect(owned) AS owned_nodes
        WITH u, owned_nodes, size(owned_nodes) AS owned_count
        DETACH DELETE u
        FOREACH (n IN owned_nodes | DETACH DELETE n)
        RETURN owned_count + 1 AS deleted_count
        """

        record = await self._run_single(query, {"uid": user_uid})

        deleted_count: int = record["deleted_count"] if record else 0

        if deleted_count > 0:
            self.logger.warning(
                f"Hard-deleted user {user_uid}: {deleted_count} nodes erased "
                f"(user + {deleted_count - 1} owned entities)"
            )
        else:
            self.logger.warning(f"User not found for hard-delete: {user_uid}")

        return Result.ok(deleted_count)

    # ========================================================================
    # LEARNING & PROGRESS TRACKING
    # ========================================================================
    # These methods manage User-Knowledge relationships in the graph

    @safe_backend_operation("update_user_progress")
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
        query = f"""
        MATCH (u:{self.label} {{uid: $uid}})
        SET u += $updates
        RETURN u
        """

        record = await self._run_single(query, {"uid": user_uid, "updates": progress_updates})

        if not record:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        self.logger.info(f"Updated user progress: {user_uid}")
        return Result.ok(True)

    @safe_backend_operation("record_knowledge_mastery")
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
        merged = await self._merge_user_edge(
            user_uid,
            knowledge_uid,
            "MASTERED",
            """r.mastery_score = $mastery_score,
            r.practice_count = $practice_count,
            r.confidence_level = $confidence_level,
            r.last_practiced = datetime()""",
            {
                "mastery_score": mastery_score,
                "practice_count": practice_count,
                "confidence_level": confidence_level,
            },
        )
        if not merged:
            return Result.fail(
                Errors.database(
                    operation="record_knowledge_mastery",
                    message="Failed to create mastery relationship",
                )
            )

        self.logger.info(f"Recorded mastery: {user_uid} → {knowledge_uid} ({mastery_score:.2f})")
        return Result.ok(True)

    @safe_backend_operation("record_knowledge_progress")
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

        Creates/updates (User)-[:IN_PROGRESS]->(Knowledge) relationship.

        Args:
            user_uid: User UID
            knowledge_uid: Knowledge unit UID
            progress: Progress value (0.0-1.0)
            time_invested_minutes: Time spent learning (minutes)
            difficulty_rating: User's perceived difficulty (0.0-1.0)

        Returns:
            Result[bool]: Success status
        """
        merged = await self._merge_user_edge(
            user_uid,
            knowledge_uid,
            "IN_PROGRESS",
            # Property shape matches UserProgressBackend.record_progress (the other
            # IN_PROGRESS writer): started_at is create-only, so coalesce preserves
            # the first one; last_accessed is what every IN_PROGRESS reader sorts on.
            # difficulty_rating coalesces the other way — the param is optional (the
            # pathways progress route omits it), and a bare SET of NULL would REMOVE
            # a rating the other writer stored on the same shared edge.
            """r.progress = $progress,
            r.started_at = coalesce(r.started_at, datetime()),
            r.time_invested_minutes = coalesce(r.time_invested_minutes, 0) + $time_invested_minutes,
            r.difficulty_rating = coalesce($difficulty_rating, r.difficulty_rating),
            r.last_accessed = datetime()""",
            {
                "progress": progress,
                "time_invested_minutes": time_invested_minutes,
                "difficulty_rating": difficulty_rating,
            },
        )
        if not merged:
            return Result.fail(
                Errors.database(
                    operation="record_knowledge_progress",
                    message="Failed to create learning relationship",
                )
            )

        self.logger.info(f"Recorded progress: {user_uid} → {knowledge_uid} ({progress})")
        return Result.ok(True)

    @safe_backend_operation("get_user_mastery")
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
        query = """
        MATCH (u:User {uid: $user_uid})-[r:MASTERED]->(k:Entity {uid: $concept_uid})
        RETURN r.mastery_score as mastery_score
        """

        record = await self._run_single(
            query,
            {"user_uid": user_uid, "concept_uid": concept_uid},
        )

        if not record:
            # No mastery recorded means 0.0 mastery
            return Result.ok(0.0)

        mastery_score: float = record["mastery_score"]
        return Result.ok(mastery_score)

    @safe_backend_operation("enroll_in_learning_path")
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
        merged = await self._merge_user_edge(
            user_uid,
            learning_path_uid,
            "ENROLLED_IN",
            """r.enrolled_at = coalesce(r.enrolled_at, datetime()),
            r.target_completion = $target_completion,
            r.weekly_time_commitment = $weekly_time_commitment,
            r.motivation_note = $motivation_note,
            r.status = 'active'""",
            {
                "target_completion": target_completion or datetime.now().isoformat(),
                "weekly_time_commitment": weekly_time_commitment,
                "motivation_note": motivation_note,
            },
            target_label="LearningPath",
        )
        if not merged:
            # MERGE only fails to produce a row when a MATCH found nothing —
            # the LP (or user) doesn't exist, not a database outage.
            return Result.fail(
                Errors.not_found(resource="LearningPath", identifier=learning_path_uid)
            )

        self.logger.info(f"Enrolled user in path: {user_uid} → {learning_path_uid}")
        return Result.ok(True)

    @safe_backend_operation("complete_learning_path")
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
        query = """
        MATCH (u:User {uid: $user_uid})-[r:ENROLLED_IN]->(lp:LearningPath {uid: $learning_path_uid})
        SET r.status = 'completed',
            r.completed_at = datetime(),
            r.completion_score = $completion_score,
            r.feedback_rating = $feedback_rating
        RETURN r
        """

        record = await self._run_single(
            query,
            {
                "user_uid": user_uid,
                "learning_path_uid": learning_path_uid,
                "completion_score": completion_score,
                "feedback_rating": feedback_rating,
            },
        )

        if not record:
            return Result.fail(
                Errors.not_found(
                    resource="Enrollment",
                    identifier=f"{user_uid} → {learning_path_uid}",
                )
            )

        self.logger.info(f"Completed learning path: {user_uid} → {learning_path_uid}")
        return Result.ok(True)

    @safe_backend_operation("express_interest_in_knowledge")
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
        merged = await self._merge_user_edge(
            user_uid,
            knowledge_uid,
            "INTERESTED_IN",
            """r.interest_score = $interest_score,
            r.interest_source = $interest_source,
            r.priority = $priority,
            r.notes = $notes,
            r.expressed_at = datetime()""",
            {
                "interest_score": interest_score,
                "interest_source": interest_source,
                "priority": priority,
                "notes": notes,
            },
        )
        if not merged:
            return Result.fail(
                Errors.database(
                    operation="express_interest_in_knowledge",
                    message="Failed to create interest relationship",
                )
            )

        self.logger.info(f"Expressed interest: {user_uid} → {knowledge_uid} ({interest_score})")
        return Result.ok(True)

    @safe_backend_operation("bookmark_knowledge")
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
        merged = await self._merge_user_edge(
            user_uid,
            knowledge_uid,
            "BOOKMARKED",
            """r.bookmarked_at = datetime(),
            r.bookmark_reason = $bookmark_reason,
            r.tags = $tags,
            r.reminder_date = $reminder_date""",
            {
                "bookmark_reason": bookmark_reason,
                "tags": tags or [],
                "reminder_date": reminder_date,
            },
        )
        if not merged:
            return Result.fail(
                Errors.database(
                    operation="bookmark_knowledge",
                    message="Failed to create bookmark",
                )
            )

        self.logger.info(f"Bookmarked: {user_uid} → {knowledge_uid}")
        return Result.ok(True)

    # ========================================================================
    # ACTIVITY & CONVERSATION TRACKING
    # ========================================================================

    @safe_backend_operation("update_user_activity")
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
        # Add last_active timestamp
        activity_updates["last_active_at"] = datetime.now().isoformat()

        query = f"""
        MATCH (u:{self.label} {{uid: $uid}})
        SET u += $updates
        RETURN u
        """

        record = await self._run_single(query, {"uid": user_uid, "updates": activity_updates})

        if not record:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        return Result.ok(True)

    @safe_backend_operation("add_conversation_message")
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
        import json
        from uuid import uuid4

        message_uid = f"msg_{uuid4().hex[:12]}"
        # Neo4j node properties cannot be maps; serialize metadata as a JSON string.
        metadata_json: str | None = json.dumps(metadata) if metadata else None

        query = """
        MATCH (u:User {uid: $user_uid})
        CREATE (m:ConversationMessage {
            uid: $message_uid,
            role: $role,
            content: $content,
            timestamp: datetime(),
            metadata: $metadata_json
        })
        CREATE (u)-[:HAS_MESSAGE]->(m)
        RETURN m
        """

        record = await self._run_single(
            query,
            {
                "user_uid": user_uid,
                "message_uid": message_uid,
                "role": role,
                "content": content,
                "metadata_json": metadata_json,
            },
        )

        if not record:
            return Result.fail(
                Errors.database(
                    operation="add_conversation_message",
                    message="Failed to create message",
                )
            )

        self.logger.info(f"Added conversation message: {user_uid} ({role})")
        return Result.ok(True)

    # ========================================================================
    # QUERY HELPERS - Additional lookups
    # ========================================================================

    @safe_backend_operation("find_by")
    async def find_by(self, **filters: Any) -> Result[list[User]]:
        """
        Find users by arbitrary filters.

        Args:
            **filters: Field filters (e.g., email="test@example.com")

        Returns:
            Result[list[User]]: Matching users
        """
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

    @safe_backend_operation("get_active_learners")
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
        query = """
        WITH datetime() - duration({hours: $hours}) AS cutoff
        MATCH (u:User)-[r:IN_PROGRESS|MASTERED]->(k:Entity)
        // One IN_PROGRESS edge can carry BOTH stamps — last_accessed
        // (record_knowledge_progress, UserProgressBackend) and last_activity_at
        // (_learning_state_mixin) — and MASTERED carries last_practiced. Each is
        // tested separately: a coalesce would pick the first non-null and hide a
        // newer stamp behind a stale one. NULL comparisons are simply not true.
        WHERE r.last_accessed >= cutoff
           OR r.last_activity_at >= cutoff
           OR r.last_practiced >= cutoff
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

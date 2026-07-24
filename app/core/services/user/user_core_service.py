"""
User Core Service - CRUD and Authentication
============================================

Focused service handling user lifecycle and authentication operations.

Responsibilities:
- User creation, retrieval, update, deletion
- Username lookups
- Password-based authentication
- Last login timestamp management

This service is part of the refactored UserService architecture:
- UserCoreService: CRUD + Auth (THIS FILE)
- UserProgressService: Learning progress tracking
- UserActivityService: Activity tracking
- UserContextBuilder: Context building
- UserStatsAggregator: Stats aggregation
- UserService: Facade coordinating all sub-services
"""

import dataclasses
from datetime import UTC, date, datetime
from typing import Any

from core.constants import SYSTEM_USER_UID, DualTrackCheckin
from core.events import publish_event
from core.events.user_events import UserDeleted
from core.models.enums import DualTrackDimension
from core.models.enums.user_enums import UserRole
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import UserUID
from core.models.user import User, create_user
from core.ports.infrastructure_protocols import EventBusOperations, UserCrudOperations
from core.utils.decorators import with_error_handling
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class UserCoreService:
    """
    Core user operations: CRUD and authentication.

    This service handles the fundamental user lifecycle operations:
    - Creating new users with default preferences
    - Retrieving users by UID or username
    - Updating user information
    - Deleting users
    - Authenticating users with password verification
    - Tracking last login timestamps

    Architecture:
    - Protocol-based repository dependency (UserOperations)
    - Uses frozen dataclass User model with immutable updates
    - Graph-native authentication with bcrypt password hashing
    """

    def __init__(
        self,
        user_repo: UserCrudOperations,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        """
        Initialize user core service.

        Args:
            user_repo: Repository implementation for user persistence (protocol-based)
            event_bus: Optional event bus for publishing UserDeleted events.
                Passed through by ``UserService``; ``None`` during isolated
                unit tests means deletion still happens but no event fires.

        Raises:
            ValueError: If user_repo is None
        """
        if not user_repo:
            raise ValueError("User repository is required")
        self.repo = user_repo
        self.event_bus = event_bus

    # ========================================================================
    # USER CRUD OPERATIONS
    # ========================================================================

    @with_error_handling("create_user", error_type="database")
    async def create_user(
        self,
        username: str,
        email: str | None = None,
        display_name: str | None = None,
        **kwargs: Any,
    ) -> Result[User]:
        """
        Create a new user with default preferences.

        Args:
            username: Unique username
            email: Optional email address
            display_name: Display name (defaults to username)
            **kwargs: Additional user properties (e.g., password_hash, role, preferences)

        Returns:
            Result[User]: Created user or error

        Error cases:
            - Username already exists → VALIDATION
            - Database operation fails → DATABASE
        """
        # Check if username already exists
        existing_result = await self.repo.get_user_by_username(username)
        if existing_result.is_ok and existing_result.value:
            return Result.fail(Errors.validation(f"Username '{username}' already exists"))

        # Create user with factory function
        user = create_user(
            username=username,
            email=email or f"{username}@example.com",
            display_name=display_name,
            **kwargs,  # Pass through additional properties (password_hash, role, preferences, etc.)
        )

        # Save to repository
        result = await self.repo.create_user(user)

        if result.is_ok:
            logger.info(f"Created user: {username} ({user.uid})")
        else:
            logger.error(f"Failed to create user {username}: {result.error}")

        return result

    @with_error_handling("ensure_system_user", error_type="database")
    async def ensure_system_user(self) -> Result[User]:
        """
        Ensure system user exists for infrastructure operations.

        Creates a system user with UID "user_system" if it doesn't exist.
        This user is used for system-owned entities like default journal projects.

        Returns:
            Result[User]: System user or error

        Error cases:
            - Database operation fails → DATABASE
        """
        # create_user() generates UID as "user_{username}", so "system" becomes "user_system".
        # SYSTEM_USER_UID is the single source of truth for this owner (see core.constants).
        system_uid = SYSTEM_USER_UID

        # Check if system user exists
        result = await self.get_user(system_uid)
        if result.is_ok and result.value:
            logger.debug(f"System user already exists: {system_uid}")
            return Result.ok(result.value)

        # Create system user
        logger.info(f"Creating system user: {system_uid}")
        from core.models.enums import UserRole

        return await self.create_user(
            username="system",
            email="system@skuel.local",
            display_name="System User",
            role=UserRole.ADMIN,  # System user needs admin privileges
            is_verified=True,  # System user is always verified
        )

    @with_error_handling("get_user", error_type="database", uid_param="user_uid")
    async def get_user(self, user_uid: UserUID) -> Result[User | None]:
        """
        Get user by UID.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[Optional[User]]: User if found, None otherwise

        Error cases:
            - Database query fails → DATABASE
        """
        return await self.repo.get_user_by_uid(user_uid)

    @with_error_handling("get_user_by_username", error_type="database")
    async def get_user_by_username(self, username: str) -> Result[User | None]:
        """
        Get user by username.

        Args:
            username: Username to search for

        Returns:
            Result[Optional[User]]: User if found, None otherwise

        Error cases:
            - Database query fails → DATABASE
        """
        return await self.repo.get_user_by_username(username)

    @with_error_handling("update_user", error_type="database")
    async def update_user(self, user: User) -> Result[User]:
        """
        Update user information.

        Args:
            user: Updated user model

        Returns:
            Result[User]: Updated user or error

        Error cases:
            - Database operation fails → DATABASE
        """
        # Update last_active_at since User is frozen dataclass
        user_with_activity = dataclasses.replace(user, last_active_at=datetime.now(UTC))
        result = await self.repo.update_user(user_with_activity)

        if result.is_ok:
            logger.info(f"Updated user: {user.uid}")
        else:
            logger.error(f"Failed to update user {user.uid}: {result.error}")

        return result

    @with_error_handling("update_preferences", error_type="database", uid_param="user_uid")
    async def update_preferences(
        self, user_uid: UserUID, preferences_update: dict[str, Any]
    ) -> Result[User]:
        """
        Update user preferences.

        Convenience method for updating only preferences without needing to
        fetch and reconstruct the entire User object.

        Args:
            user_uid: User's unique identifier
            preferences_update: Dict of preference fields to update
                               (e.g., {"weekly_task_goal": 15, "daily_habit_goal": 5})

        Returns:
            Result[User]: Updated user or error

        Error cases:
            - User not found → NOT_FOUND
            - Database operation fails → DATABASE

        Example:
            result = await service.update_preferences(
                "user123",
                {"weekly_task_goal": 15, "daily_habit_goal": 5}
            )
        """
        # Get current user
        user_result = await self.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result)

        if not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        # Create new preferences with updates
        updated_preferences = dataclasses.replace(user.preferences, **preferences_update)

        # Create new user with updated preferences
        updated_user = dataclasses.replace(user, preferences=updated_preferences)

        # Update user in database
        result = await self.update_user(updated_user)

        if result.is_ok:
            logger.info(f"Updated preferences for user {user_uid}: {preferences_update}")
        else:
            logger.error(f"Failed to update preferences for {user_uid}: {result.error}")

        return result

    async def append_dual_track_checkin(  # skuel-lint: disable=SKUEL005 -- safe-by-design store_callback (ADR-030): check-in persistence must not fail the assessment
        self,
        user_uid: UserUID,
        result: DualTrackResult[Any],
        *,
        dimension: DualTrackDimension,
    ) -> None:
        """
        Append a user-level dual-track check-in snapshot to the User node (ADR-030).

        The user-level analog of ``BaseAnalyticsService._store_dual_track_checkin``:
        that callback persists per-entity check-ins to an entity's
        ``dual_track_checkins`` field, but the user-level dimensions (Productivity /
        Engagement / Decision Quality) assess the user across *all* their entities of
        a kind and have no ``:Entity`` row — so they persist on the ``:User`` node,
        keyed by ``dimension``.

        The append is **atomic** — serialized via a Neo4j node write-lock
        (Backend: ``UserBackend.atomic_append_dual_track_checkin``), capped at
        ``DualTrackCheckin.HISTORY_LIMIT`` per dimension — so two near-simultaneous
        check-ins for the same user can't lose a snapshot.

        Safe-by-design (returns ``None``, never raises) so it can be used directly
        as a ``store_callback`` — a persistence hiccup must never fail the
        assessment itself. ``dimension`` is keyword-only so the method can be bound
        with ``functools.partial(..., dimension=...)`` into the
        ``store_callback(uid, result)`` shape the dual-track template expects.

        Args:
            user_uid: User whose check-in is being recorded.
            result: The computed dual-track result (carries the system level/score
                and the perception gap — not just the user's self-rating).
            dimension: Which user-level dimension this check-in belongs to.
        """
        snapshot = result.to_checkin_snapshot(date.today())
        store_result = await self.repo.atomic_append_dual_track_checkin(
            user_uid, snapshot, DualTrackCheckin.HISTORY_LIMIT, dimension.value
        )
        if store_result.is_error:
            logger.warning(
                "Failed to persist dual-track check-in for %s (%s): %s",
                user_uid,
                dimension.value,
                store_result.expect_error().message,
            )

    async def append_knowledge_checkin(  # skuel-lint: disable=SKUEL005 -- safe-by-design store_callback (ADR-030): check-in persistence must not fail the assessment
        self,
        ku_uid: str,
        result: DualTrackResult[Any],
        *,
        user_uid: UserUID,
    ) -> None:
        """
        Append a Knowledge dual-track check-in snapshot to the User node (ADR-030).

        The Knowledge-dimension analog of ``append_dual_track_checkin``: that callback
        persists the three fixed user-level dimensions keyed by ``DualTrackDimension``;
        this persists per-Ku mastery self-ratings keyed by ``ku_uid`` in a *separate*
        ``knowledge_checkins`` log on the ``:User`` node. A Ku is SHARED/public
        curriculum, so a mastery check-in can't live on the ``:Ku`` node (it would
        collide across users) — it lives per-user, keyed by the Ku.

        The append is **atomic** — serialized via a Neo4j node write-lock
        (Backend: ``UserBackend.atomic_append_knowledge_checkin``), capped at
        ``DualTrackCheckin.HISTORY_LIMIT`` per Ku — so two near-simultaneous mastery
        check-ins for the same (user, Ku) can't lose a snapshot.

        Safe-by-design (returns ``None``, never raises) so it can be used directly as a
        ``store_callback``. The signature mirrors the dual-track template's
        ``store_callback(uid, result)`` contract — the template passes the assessed
        ``ku_uid`` as the positional ``uid``; ``user_uid`` is keyword-bound by the
        Ku-detail route (via a small store closure).

        Args:
            ku_uid: The Ku the mastery self-rating belongs to (the template's ``uid``).
            result: The computed dual-track result (carries the system level/score and
                the perception gap — not just the user's self-rating).
            user_uid: User whose check-in is being recorded.
        """
        snapshot = result.to_checkin_snapshot(date.today())
        store_result = await self.repo.atomic_append_knowledge_checkin(
            user_uid, snapshot, DualTrackCheckin.HISTORY_LIMIT, ku_uid
        )
        if store_result.is_error:
            logger.warning(
                "Failed to persist knowledge check-in for %s (ku=%s): %s",
                user_uid,
                ku_uid,
                store_result.expect_error().message,
            )

    @with_error_handling("delete_user", error_type="database", uid_param="user_uid")
    async def delete_user(
        self,
        user_uid: UserUID,
        reason: str = "",
        deleted_by: UserUID | None = None,
    ) -> Result[bool]:
        """
        Soft-delete a user (default account closure path).

        Marks ``status=DELETED``, scrubs PII (email, display_name,
        password_hash), and preserves the User node plus every OWNS-linked
        entity so teachers can still render historical submissions. Login is
        blocked because ``authenticate()`` already rejects ``is_active=false``.

        For GDPR right-to-erasure (wipe everything), use
        ``hard_delete_user`` — admin-gated separate method.

        Args:
            user_uid: User to soft-delete
            reason: Free-form note saved to the ``UserDeleted`` event payload
            deleted_by: Admin UID when an admin initiates; None for self-delete

        Returns:
            Result[bool]: True if the user existed and was marked deleted.

        Error cases:
            - Database operation fails → DATABASE
        """
        result = await self.repo.delete_user(user_uid)

        if result.is_ok:
            logger.info(f"Soft-deleted user: {user_uid} (by={deleted_by or 'self'})")
            if result.value:
                await publish_event(
                    self.event_bus,
                    UserDeleted(
                        user_uid=user_uid,
                        hard_delete=False,
                        deleted_by=deleted_by,
                        reason=reason,
                    ),
                    logger,
                )
        else:
            logger.error(f"Failed to soft-delete user {user_uid}: {result.error}")

        return result

    @with_error_handling("hard_delete_user", error_type="database", uid_param="user_uid")
    async def hard_delete_user(
        self,
        user_uid: UserUID,
        requester_role: UserRole,
        deleted_by: UserUID,
        reason: str,
    ) -> Result[int]:
        """
        GDPR right-to-erasure: wipe user + every OWNS-linked entity.

        Admin-only. Destroys the User node and cascades through every :OWNS
        edge, removing UserEntry / Task / Goal / Habit / ... nodes owned by
        the user. Unlike soft-delete this is irreversible and erases teacher-
        visible history — reserve for explicit erasure requests.

        Args:
            user_uid: User to erase
            requester_role: Role of the admin initiating the erasure. Gate is
                ``requester_role.has_permission(UserRole.ADMIN)`` — non-admin
                callers receive an authorization error.
            deleted_by: Admin UID (for audit trail on the emitted event)
            reason: Admin-supplied justification (required by the admin UI)

        Returns:
            Result[int]: Total nodes deleted (user + owned entities).
            0 when the UID did not match.

        Error cases:
            - Non-admin requester → AUTHORIZATION
            - Database operation fails → DATABASE
        """
        if not requester_role.has_permission(UserRole.ADMIN):
            logger.warning(
                f"Hard-delete denied for {user_uid} — requester {deleted_by} "
                f"has role {requester_role.value}, not admin"
            )
            return Result.fail(
                Errors.forbidden(
                    action="hard_delete_user",
                    reason="Hard-delete requires ADMIN role",
                    required_role=UserRole.ADMIN.value,
                )
            )

        result = await self.repo.hard_delete_user(user_uid)

        if result.is_ok:
            count = result.value or 0
            logger.warning(
                f"Hard-deleted user {user_uid}: {count} nodes erased "
                f"(by={deleted_by}, reason={reason!r})"
            )
            if count > 0:
                await publish_event(
                    self.event_bus,
                    UserDeleted(
                        user_uid=user_uid,
                        hard_delete=True,
                        deleted_by=deleted_by,
                        reason=reason,
                    ),
                    logger,
                )
        else:
            logger.error(f"Failed to hard-delete user {user_uid}: {result.error}")

        return result

    # ========================================================================
    # ROLE MANAGEMENT (December 2025)
    # ========================================================================

    @with_error_handling("update_user_role", error_type="database", uid_param="user_uid")
    async def update_user_role(self, user_uid: UserUID, new_role: "UserRole") -> Result[User]:
        """
        Update a user's role.

        Args:
            user_uid: User to update
            new_role: New role to assign

        Returns:
            Result[User]: Updated user or error

        Note:
            This is an internal method. Role authorization checks
            should be performed by the caller (UserService.update_role).
        """

        # Get current user
        user_result = await self.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result)

        if not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        # Update role using dataclass replace (frozen dataclass)
        updated_user = dataclasses.replace(user, role=new_role)

        # Save to database
        result = await self.update_user(updated_user)

        if result.is_ok:
            logger.info(f"Updated role for {user_uid}: {user.role.value} → {new_role.value}")
        else:
            logger.error(f"Failed to update role for {user_uid}: {result.error}")

        return result

    @with_error_handling("list_users", error_type="database")
    async def list_users(
        self,
        limit: int = 100,
        offset: int = 0,
        role_filter: "UserRole | None" = None,
        active_only: bool = True,
    ) -> Result[list[User]]:
        """
        List users with optional filtering.

        Args:
            limit: Maximum number of users to return
            offset: Pagination offset
            role_filter: Optional filter by role
            active_only: Only return active users (default True)

        Returns:
            Result[list[User]]: List of users or error

        Note:
            This is an internal method. Authorization checks
            should be performed by the caller (UserService.list_users).
        """
        # Build filter criteria
        filters: dict[str, Any] = {}

        if role_filter:
            filters["role"] = role_filter.value

        if active_only:
            filters["is_active"] = True

        # Query users
        result = await self.repo.find_by(**filters)

        if result.is_error:
            return Result.fail(result)

        users = result.value or []

        # Apply pagination (if not handled by backend)
        # Note: Backend may already handle pagination, but we apply safety limits
        paginated = users[offset : offset + limit]

        logger.debug(
            f"Listed {len(paginated)} users (offset={offset}, limit={limit}, "
            f"role_filter={role_filter.value if role_filter else 'all'})"
        )

        return Result.ok(paginated)

    # deactivate_user lived here until 2026-07-24: deactivation now commits
    # the is_active flip and the session revocation in ONE transaction via
    # SessionBackend.deactivate_user_and_revoke_sessions (One Path Forward —
    # the two-step load/replace/save path could half-apply).

    @with_error_handling("activate_user", error_type="database", uid_param="user_uid")
    async def activate_user(self, user_uid: UserUID) -> Result[User]:
        """
        Reactivate a user account.

        Args:
            user_uid: User to reactivate

        Returns:
            Result[User]: Updated user or error

        Note:
            This is an internal method. Authorization checks
            should be performed by the caller.
        """
        # Get current user
        user_result = await self.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result)

        if not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        if user.is_active:
            # Already active - return current state
            return Result.ok(user)

        # Activate using dataclass replace
        updated_user = dataclasses.replace(user, is_active=True)

        # Save to database
        result = await self.update_user(updated_user)

        if result.is_ok:
            logger.info(f"Reactivated user {user_uid}")
        else:
            logger.error(f"Failed to reactivate user {user_uid}: {result.error}")

        return result

    # ========================================================================
    # AUTHENTICATION
    # ========================================================================

    @with_error_handling("authenticate", error_type="system")
    async def authenticate(self, username: str, password: str) -> Result[User]:
        """
        Authenticate user with username and password.

        Args:
            username: Username to authenticate
            password: Plain text password to verify

        Returns:
            Result[User]: Authenticated user or error

        Error cases:
            - User not found → NOT_FOUND
            - Invalid password → VALIDATION
            - Account inactive → BUSINESS
            - Database error → DATABASE
            - Unexpected error → SYSTEM
        """
        # Get user by username
        user_result = await self.get_user_by_username(username)

        if user_result.is_error:
            logger.warning(f"Authentication failed - error getting user: {username}")
            return Result.fail(user_result)

        if not user_result.value:
            logger.warning(f"Authentication failed - user not found: {username}")
            return Result.fail(Errors.not_found(resource="User", identifier=username))

        user = user_result.value

        # Check if account is active
        if not user.is_active:
            logger.warning(f"Authentication failed - account inactive: {username}")
            return Result.fail(
                Errors.business(
                    rule="account_active",
                    message="Account is inactive. Please contact support.",
                )
            )

        # Verify password
        from core.auth.password import verify_password

        if not verify_password(password, user.password_hash):
            logger.warning(f"Authentication failed - invalid password: {username}")
            return Result.fail(
                Errors.validation(message="Invalid username or password", field="password")
            )

        # Update last login timestamp
        await self._update_last_login(user)

        logger.info(f"✅ User authenticated successfully: {username}")
        return Result.ok(user)

    async def _update_last_login(self, user: User) -> None:
        """
        Update user's last_login_at timestamp.

        Args:
            user: User to update

        Note:
            - Uses dataclass replace since User is frozen
            - Logs warning if update fails (does not fail authentication)
        """
        try:
            from dataclasses import replace

            # Create updated user with new last_login_at
            updated_user = replace(user, last_login_at=datetime.now(UTC))

            # Save to database
            update_result = await self.repo.update_user(updated_user)

            if update_result.is_error:
                logger.warning(f"Failed to update last_login for {user.uid}: {update_result.error}")
            else:
                logger.debug(f"Updated last_login for {user.uid}")

        except NEO4J_EXCEPTIONS as e:
            # Don't fail authentication if timestamp update fails
            logger.warning(f"Error updating last_login for {user.uid}: {e}")
        except Exception as e:  # safety-net: catch unexpected errors
            logger.warning(f"Error updating last_login for {user.uid}: {e}")

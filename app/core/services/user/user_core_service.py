"""
User Core Service - CRUD and Authentication
============================================

Focused service handling user lifecycle and authentication operations.

Responsibilities:
- User creation, retrieval, update, deletion
- Username and Supabase ID lookups
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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.models.user import User, create_user
from core.services.protocols.infrastructure_protocols import UserOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.enums.user_enums import UserRole

logger = get_logger(__name__)


class UserCoreService:
    """
    Core user operations: CRUD and authentication.

    This service handles the fundamental user lifecycle operations:
    - Creating new users with default preferences
    - Retrieving users by UID, username, or Supabase ID
    - Updating user information
    - Deleting users
    - Authenticating users with password verification
    - Tracking last login timestamps

    Architecture:
    - Protocol-based repository dependency (UserOperations)
    - Returns Result[T] for error handling
    - Uses frozen dataclass User model with immutable updates
    - Integrates with Supabase authentication


    Source Tag: "user_core_explicit"
    - Format: "user_core_explicit" for user-created relationships
    - Format: "user_core_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    def __init__(self, user_repo: UserOperations) -> None:
        """
        Initialize user core service.

        Args:
            user_repo: Repository implementation for user persistence (protocol-based)

        Raises:
            ValueError: If user_repo is None
        """
        if not user_repo:
            raise ValueError("User repository is required")
        self.repo = user_repo

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

        Uses Supabase for authentication - password management is handled by Supabase.

        Args:
            username: Unique username
            email: Optional email address
            display_name: Display name (defaults to username)
            **kwargs: Additional user properties (MUST include supabase_id for Supabase auth)

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
        # Note: Supabase handles authentication - password_hash is no longer used
        user = create_user(
            username=username,
            email=email or f"{username}@example.com",
            display_name=display_name,
            **kwargs,  # Pass through additional properties (including supabase_id)
        )

        # Save to repository
        result = await self.repo.create_user(user)

        if result.is_ok:
            logger.info(f"Created user: {username} ({user.uid})")
        else:
            logger.error(f"Failed to create user {username}: {result.error}")

        return result

    async def get_user(self, user_uid: str) -> Result[User | None]:
        """
        Get user by UID.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[Optional[User]]: User if found, None otherwise

        Error cases:
            - Database query fails → DATABASE
        """
        try:
            # Use standard backend get() method
            result = await self.repo.get(user_uid)

            if result.is_ok and result.value:
                # Update last active timestamp (if method exists)
                from contextlib import suppress

                with suppress(
                    AttributeError
                ):  # update_last_active not available on frozen dataclass
                    result.value.update_last_active()

            return result

        except AttributeError:
            # Fallback: repo doesn't have get() method, return None
            logger.warning(f"Backend doesn't support get() method for user {user_uid}")
            return Result.ok(None)
        except Exception as e:
            logger.error(f"Error getting user {user_uid}: {e}")
            return Result.fail(
                Errors.database(operation="user_query", message=f"User query failed: {e}")
            )

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

    @with_error_handling("get_user_by_supabase_id", error_type="database")
    async def get_user_by_supabase_id(self, supabase_id: str) -> Result[User | None]:
        """
        Get user by Supabase ID.

        Args:
            supabase_id: Supabase auth user ID

        Returns:
            Result[Optional[User]]: User if found, None otherwise

        Error cases:
            - Database query fails → DATABASE
        """
        # Query Neo4j for user with matching supabase_id
        result = await self.repo.find_by(supabase_id=supabase_id)

        if result.is_ok and result.value:
            # Return first match (supabase_id should be unique)
            return Result.ok(result.value[0] if result.value else None)

        return Result.ok(None)

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
        self, user_uid: str, preferences_update: dict[str, Any]
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
            return Result.fail(user_result.expect_error())

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

    @with_error_handling("delete_user", error_type="database", uid_param="user_uid")
    async def delete_user(self, user_uid: str) -> Result[bool]:
        """
        DETACH DELETE a user.

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[bool]: True if deleted successfully

        Error cases:
            - Database operation fails → DATABASE
        """
        result = await self.repo.delete_user(user_uid)

        if result.is_ok:
            logger.info(f"Deleted user: {user_uid}")
        else:
            logger.error(f"Failed to delete user {user_uid}: {result.error}")

        return result

    # ========================================================================
    # ROLE MANAGEMENT (December 2025)
    # ========================================================================

    @with_error_handling("update_user_role", error_type="database", uid_param="user_uid")
    async def update_user_role(self, user_uid: str, new_role: "UserRole") -> Result[User]:
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
            return Result.fail(user_result.expect_error())

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
            return Result.fail(result.expect_error())

        users = result.value or []

        # Apply pagination (if not handled by backend)
        # Note: Backend may already handle pagination, but we apply safety limits
        paginated = users[offset : offset + limit]

        logger.debug(
            f"Listed {len(paginated)} users (offset={offset}, limit={limit}, "
            f"role_filter={role_filter.value if role_filter else 'all'})"
        )

        return Result.ok(paginated)

    @with_error_handling("deactivate_user", error_type="database", uid_param="user_uid")
    async def deactivate_user(self, user_uid: str, reason: str = "") -> Result[User]:
        """
        Deactivate a user account.

        Args:
            user_uid: User to deactivate
            reason: Reason for deactivation (for logging)

        Returns:
            Result[User]: Updated user or error

        Note:
            This is an internal method. Authorization checks
            should be performed by the caller.
        """
        # Get current user
        user_result = await self.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result.expect_error())

        if not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        if not user.is_active:
            # Already deactivated - return current state
            return Result.ok(user)

        # Deactivate using dataclass replace
        updated_user = dataclasses.replace(user, is_active=False)

        # Save to database
        result = await self.update_user(updated_user)

        if result.is_ok:
            logger.info(f"Deactivated user {user_uid}. Reason: {reason or 'not specified'}")
        else:
            logger.error(f"Failed to deactivate user {user_uid}: {result.error}")

        return result

    @with_error_handling("activate_user", error_type="database", uid_param="user_uid")
    async def activate_user(self, user_uid: str) -> Result[User]:
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
            return Result.fail(user_result.expect_error())

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
            return Result.fail(user_result.expect_error())

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

        except Exception as e:
            # Don't fail authentication if timestamp update fails
            logger.warning(f"Error updating last_login for {user.uid}: {e}")

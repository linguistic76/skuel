"""
Graph-Native Authentication Service
====================================

Main authentication service with full Neo4j integration.

Design Philosophy:
- All auth state lives in Neo4j (sessions, events, tokens)
- No external dependencies for authentication
- Bcrypt password hashing (existing in password.py)
- Rate limiting via graph queries on AuthEvent nodes
- Admin-initiated password reset (no email service)

See Also:
- /core/models/auth/ - Auth domain models
- /adapters/persistence/neo4j/session_backend.py - Session persistence
- /docs/decisions/graph-native-auth.md - ADR
"""

from typing import Any

from core.auth.password import hash_password, verify_password
from core.models.auth.auth_event import AuthEventType, create_auth_event
from core.models.auth.password_reset_token import create_password_reset_token
from core.models.auth.session import create_session
from core.models.user import User, create_user
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.auth.graph")


class GraphAuthService:
    """
    Graph-native authentication service.

    All authentication state (sessions, events, tokens) lives in the graph.
    """

    def __init__(
        self,
        user_backend: Any,  # UserOperations protocol
        session_backend: Any,  # SessionBackend
    ) -> None:
        """
        Initialize graph auth service.

        Args:
            user_backend: Backend for user operations
            session_backend: Backend for session operations
        """
        self.user_backend = user_backend
        self.session_backend = session_backend
        self.logger = logger
        logger.info("Graph-native auth service initialized")

    # ========================================================================
    # REGISTRATION
    # ========================================================================

    async def sign_up(
        self,
        email: str,
        password: str,
        username: str,
        display_name: str | None = None,
        user_metadata: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Register a new user.

        Args:
            email: User's email address
            password: User's password (will be hashed)
            username: Unique username
            display_name: Display name (defaults to username)
            user_metadata: Additional user data

        Returns:
            Result containing user data or error
        """
        try:
            # Validate inputs
            if not email or "@" not in email:
                return Result.fail(
                    Errors.validation(message="Invalid email address", field="email")
                )

            if not password or len(password) < 8:
                return Result.fail(
                    Errors.validation(
                        message="Password must be at least 8 characters", field="password"
                    )
                )

            if not username or len(username) < 3:
                return Result.fail(
                    Errors.validation(
                        message="Username must be at least 3 characters", field="username"
                    )
                )

            # Check if email already exists
            existing_result = await self.user_backend.find_by(email=email)
            if existing_result.is_error:
                return existing_result

            if existing_result.value:
                return Result.fail(
                    Errors.validation(message=f"Email {email} is already registered", field="email")
                )

            # Check if username already exists
            username_result = await self.user_backend.get_user_by_username(username)
            if username_result.is_error:
                return username_result

            if username_result.value:
                return Result.fail(
                    Errors.validation(
                        message=f"Username {username} is already taken", field="username"
                    )
                )

            # Hash password
            password_hash = hash_password(password)

            # Create user
            user = create_user(
                username=username,
                email=email,
                display_name=display_name,
                password_hash=password_hash,
                is_verified=True,  # No email verification in this design
                **(user_metadata or {}),
            )

            create_result = await self.user_backend.create_user(user)
            if create_result.is_error:
                return create_result

            created_user = create_result.value
            self.logger.info(f"User registered: {email}")

            return Result.ok(
                {
                    "user_uid": created_user.uid,
                    "email": created_user.email,
                    "username": created_user.title,
                    "display_name": created_user.display_name,
                    "is_verified": True,
                }
            )

        except Exception as e:
            self.logger.error(f"Sign up error: {e}")
            return Result.fail(Errors.system(operation="sign_up", message=str(e)))

    # ========================================================================
    # AUTHENTICATION
    # ========================================================================

    async def sign_in(
        self,
        email: str,
        password: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[dict[str, Any]]:
        """
        Authenticate user and create session.

        Args:
            email: User's email address
            password: User's password
            ip_address: Client IP for audit trail
            user_agent: Client user agent for audit trail

        Returns:
            Result containing session data or error
        """
        try:
            # Check rate limiting
            is_locked = await self.session_backend.is_account_locked(email)
            if is_locked.is_error:
                return is_locked

            if is_locked.value:
                # Do NOT log another LOGIN_FAILED here — doing so pushes a new
                # timestamp into the rolling window and perpetually extends the
                # lockout.  The original failures that triggered the lock are
                # already recorded; that's sufficient for the audit trail.
                return Result.fail(
                    Errors.business(
                        rule="rate_limit",
                        message="Account temporarily locked due to too many failed attempts. Please try again in 15 minutes.",
                    )
                )

            # Find user by email
            users_result = await self.user_backend.find_by(email=email)
            if users_result.is_error:
                return users_result

            users = users_result.value
            if not users:
                # Log failed attempt (user not found)
                event = create_auth_event(
                    event_type=AuthEventType.LOGIN_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    email=email,
                    metadata={"reason": "user_not_found"},
                )
                await self.session_backend.log_auth_event(event)

                return Result.fail(
                    Errors.validation(message="Invalid email or password", field="password")
                )

            user = users[0]

            # Verify password
            if not verify_password(password, user.password_hash):
                # Log failed attempt (wrong password)
                event = create_auth_event(
                    event_type=AuthEventType.LOGIN_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    user_uid=user.uid,
                    email=email,
                    metadata={"reason": "wrong_password"},
                )
                await self.session_backend.log_auth_event(event)

                return Result.fail(
                    Errors.validation(message="Invalid email or password", field="password")
                )

            # Check if user is active
            if not user.is_active:
                return Result.fail(
                    Errors.business(
                        rule="account_status",
                        message="Account is deactivated. Please contact support.",
                    )
                )

            # Create session with cached user data (avoid DB lookup on validation)
            session = create_session(
                user_uid=user.uid,
                ip_address=ip_address,
                user_agent=user_agent,
                user_is_active=user.is_active,
            )

            session_result = await self.session_backend.create_session(session)
            if session_result.is_error:
                return session_result

            # Log successful login
            event = create_auth_event(
                event_type=AuthEventType.LOGIN_SUCCESS,
                ip_address=ip_address,
                user_agent=user_agent,
                user_uid=user.uid,
                email=email,
                session_uid=session.uid,
            )
            await self.session_backend.log_auth_event(event)

            self.logger.info(f"User signed in: {email}")

            return Result.ok(
                {
                    "user_uid": user.uid,
                    "email": user.email,
                    "session_token": session.session_token,
                    "session_uid": session.uid,
                    "expires_at": session.expires_at.isoformat(),
                    "user": user,
                }
            )

        except Exception as e:
            self.logger.error(f"Sign in error: {e}")
            return Result.fail(Errors.system(operation="sign_in", message=str(e)))

    async def sign_out(
        self,
        session_token: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[bool]:
        """
        Sign out user by invalidating session.

        Args:
            session_token: Session token to invalidate
            ip_address: Client IP for audit trail
            user_agent: Client user agent for audit trail

        Returns:
            Result indicating success
        """
        try:
            # Get session to find user
            session_result = await self.session_backend.get_session_by_token(session_token)
            if session_result.is_error:
                return session_result

            session = session_result.value

            # Invalidate session
            invalidate_result = await self.session_backend.invalidate_session(session_token)
            if invalidate_result.is_error:
                return invalidate_result

            # Log logout event
            if session:
                event = create_auth_event(
                    event_type=AuthEventType.LOGOUT,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    user_uid=session.user_uid,
                    session_uid=session.uid,
                )
                await self.session_backend.log_auth_event(event)

            self.logger.info("User signed out")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Sign out error: {e}")
            return Result.fail(Errors.system(operation="sign_out", message=str(e)))

    async def validate_session_uid(self, session_token: str) -> Result[str | None]:
        """
        Validate session token and return user UID (optimized - no user fetch).

        This is the fast path for session validation. Uses cached user_is_active
        from the session to avoid database lookup for the User entity.

        Args:
            session_token: Session token from cookie

        Returns:
            Result containing user_uid if valid, None if invalid/expired
        """
        try:
            # Get session (single DB call)
            session_result = await self.session_backend.get_session_by_token(session_token)
            if session_result.is_error:
                return session_result

            session = session_result.value

            if not session:
                return Result.ok(None)

            # Check if session is active (expiry + is_valid)
            if not session.is_active():
                return Result.ok(None)

            # Check cached user active status (no DB call needed)
            if not session.user_is_active:
                return Result.ok(None)

            # Update last active time
            await self.session_backend.update_last_active(session_token)

            return Result.ok(session.user_uid)

        except Exception as e:
            self.logger.error(f"Session validation error: {e}")
            return Result.fail(Errors.system(operation="validate_session_uid", message=str(e)))

    async def validate_session(self, session_token: str) -> Result[User | None]:
        """
        Validate session token and return associated user.

        NOTE: For most use cases, prefer validate_session_uid() which is faster.
        This method fetches the full User entity - use only when you need
        user data beyond uid (e.g., role, email, profile).

        Args:
            session_token: Session token from cookie

        Returns:
            Result containing User if valid, None if invalid/expired
        """
        try:
            # First do the fast validation
            uid_result = await self.validate_session_uid(session_token)
            if uid_result.is_error:
                return Result.fail(uid_result.expect_error())

            user_uid = uid_result.value
            if not user_uid:
                return Result.ok(None)

            # Fetch full user (only when explicitly needed)
            user_result = await self.user_backend.get_user_by_uid(user_uid)
            if user_result.is_error:
                return Result.fail(user_result.expect_error())

            return Result.ok(user_result.value)

        except Exception as e:
            self.logger.error(f"Session validation error: {e}")
            return Result.fail(Errors.system(operation="validate_session", message=str(e)))

    # ========================================================================
    # PASSWORD MANAGEMENT
    # ========================================================================

    async def change_password(
        self,
        user_uid: str,
        old_password: str,
        new_password: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[bool]:
        """
        Change user's password.

        Invalidates all existing sessions for security.

        Args:
            user_uid: User UID
            old_password: Current password for verification
            new_password: New password
            ip_address: Client IP for audit
            user_agent: Client user agent for audit

        Returns:
            Result indicating success
        """
        try:
            # Validate new password
            if not new_password or len(new_password) < 8:
                return Result.fail(
                    Errors.validation(
                        message="Password must be at least 8 characters", field="new_password"
                    )
                )

            # Get user
            user_result = await self.user_backend.get_user_by_uid(user_uid)
            if user_result.is_error:
                return user_result

            user = user_result.value
            if not user:
                return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

            # Verify old password
            if not verify_password(old_password, user.password_hash):
                return Result.fail(
                    Errors.validation(message="Current password is incorrect", field="old_password")
                )

            # Hash new password and update user
            new_hash = hash_password(new_password)

            # Create updated user (frozen dataclass, so we need to recreate)
            from dataclasses import replace

            updated_user = replace(user, password_hash=new_hash)

            update_result = await self.user_backend.update_user(updated_user)
            if update_result.is_error:
                return update_result

            # Invalidate all sessions for security
            await self.session_backend.invalidate_all_user_sessions(user_uid)

            # Log password change
            event = create_auth_event(
                event_type=AuthEventType.PASSWORD_CHANGED,
                ip_address=ip_address,
                user_agent=user_agent,
                user_uid=user_uid,
                email=user.email,
            )
            await self.session_backend.log_auth_event(event)

            self.logger.info(f"Password changed for user: {user_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Change password error: {e}")
            return Result.fail(Errors.system(operation="change_password", message=str(e)))

    async def admin_generate_reset_token(
        self,
        user_uid: str,
        admin_uid: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[str]:
        """
        Generate a password reset token (admin-initiated).

        Args:
            user_uid: User who needs password reset
            admin_uid: Admin generating the token
            ip_address: Admin's IP for audit
            user_agent: Admin's user agent for audit

        Returns:
            Result containing the reset token string
        """
        try:
            # Verify user exists
            user_result = await self.user_backend.get_user_by_uid(user_uid)
            if user_result.is_error:
                return user_result

            user = user_result.value
            if not user:
                return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

            # Verify admin exists and has permission
            admin_result = await self.user_backend.get_user_by_uid(admin_uid)
            if admin_result.is_error:
                return admin_result

            admin = admin_result.value
            if not admin or not admin.can_manage_users():
                return Result.fail(
                    Errors.business(
                        rule="permission",
                        message="Only admins can generate password reset tokens",
                    )
                )

            # Create reset token
            token = create_password_reset_token(
                user_uid=user_uid,
                created_by_admin_uid=admin_uid,
            )

            token_result = await self.session_backend.create_reset_token(token)
            if token_result.is_error:
                return token_result

            # Log the event
            event = create_auth_event(
                event_type=AuthEventType.PASSWORD_RESET_REQUESTED,
                ip_address=ip_address,
                user_agent=user_agent,
                user_uid=user_uid,
                email=user.email,
                metadata={"admin_uid": admin_uid},
            )
            await self.session_backend.log_auth_event(event)

            self.logger.info(f"Reset token generated for {user_uid} by admin {admin_uid}")
            return Result.ok(token.token)

        except Exception as e:
            self.logger.error(f"Generate reset token error: {e}")
            return Result.fail(
                Errors.system(operation="admin_generate_reset_token", message=str(e))
            )

    async def reset_password_with_token(
        self,
        token_value: str,
        new_password: str,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> Result[bool]:
        """
        Reset password using a reset token.

        Args:
            token_value: The reset token string
            new_password: New password
            ip_address: Client IP for audit
            user_agent: Client user agent for audit

        Returns:
            Result indicating success
        """
        try:
            # Validate new password
            if not new_password or len(new_password) < 8:
                return Result.fail(
                    Errors.validation(
                        message="Password must be at least 8 characters", field="new_password"
                    )
                )

            # Get token
            token_result = await self.session_backend.get_reset_token(token_value)
            if token_result.is_error:
                return token_result

            token = token_result.value
            if not token:
                return Result.fail(
                    Errors.validation(message="Invalid or expired reset token", field="token")
                )

            # Check if token is valid
            if not token.is_valid():
                return Result.fail(
                    Errors.validation(message="Reset token has expired or been used", field="token")
                )

            # Get user
            user_result = await self.user_backend.get_user_by_uid(token.user_uid)
            if user_result.is_error:
                return user_result

            user = user_result.value
            if not user:
                return Result.fail(Errors.not_found(resource="User", identifier=token.user_uid))

            # Hash new password and update user
            new_hash = hash_password(new_password)
            from dataclasses import replace

            updated_user = replace(user, password_hash=new_hash)

            update_result = await self.user_backend.update_user(updated_user)
            if update_result.is_error:
                return update_result

            # Mark token as used
            await self.session_backend.mark_reset_token_used(token_value)

            # Invalidate all sessions for security
            await self.session_backend.invalidate_all_user_sessions(token.user_uid)

            # Log password reset completion
            event = create_auth_event(
                event_type=AuthEventType.PASSWORD_RESET_COMPLETED,
                ip_address=ip_address,
                user_agent=user_agent,
                user_uid=token.user_uid,
                email=user.email,
            )
            await self.session_backend.log_auth_event(event)

            self.logger.info(f"Password reset completed for user: {token.user_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Reset password with token error: {e}")
            return Result.fail(Errors.system(operation="reset_password_with_token", message=str(e)))

    # ========================================================================
    # EMAIL-BASED PASSWORD RESET (PLACEHOLDER)
    # ========================================================================

    async def reset_password_email(self, email: str) -> Result[bool]:
        """
        Placeholder for email-based password reset.

        In graph-native auth, password reset is admin-initiated via
        admin_generate_reset_token() and reset_password_with_token().
        This method exists for future email service integration.

        TODO: Implement when email service is available.

        Args:
            email: User's email (unused - placeholder for future email integration)

        Returns:
            Result with message about admin-initiated reset
        """
        # Silence unused parameter warning - intentional placeholder
        _ = email
        return Result.fail(
            Errors.business(
                rule="password_reset",
                message="Password reset is admin-initiated. Please contact an administrator.",
            )
        )


# NOTE: GraphAuthService is created via dependency injection in services_bootstrap.py
# No singleton pattern needed - services.graph_auth is the canonical instance.

__all__ = [
    "GraphAuthService",
]

"""
Session Backend - Graph-Native Session Persistence
===================================================

Neo4j backend for session management in the graph-native authentication system.

Design:
- Sessions are stored as Neo4j nodes (:Session)
- Linked to users via (User)-[:HAS_SESSION]->(Session)
- Auth events stored as (:AuthEvent) nodes for audit trail
- Rate limiting uses graph queries on AuthEvent nodes

See Also:
- /core/models/auth/session.py - Session domain model
- /core/auth/graph_auth.py - Main authentication service
- /docs/decisions/graph-native-auth.md - ADR for this system
"""

from datetime import datetime
from typing import Any, cast

from neo4j import AsyncDriver
from neo4j.time import DateTime as Neo4jDateTime

from core.models.auth.auth_event import AuthEvent
from core.models.auth.password_reset_token import PasswordResetToken
from core.models.auth.session import Session
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


# Rate limiting configuration
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class SessionBackend:
    """
    Neo4j backend for session persistence.

    Handles:
    - Session CRUD operations
    - Auth event logging (audit trail)
    - Rate limiting via auth event queries
    - Password reset token management
    """

    def __init__(self, driver: AsyncDriver) -> None:
        """
        Initialize session backend.

        Args:
            driver: Neo4j async driver
        """
        self.driver = driver
        self.logger = logger

    # ========================================================================
    # SESSION CRUD OPERATIONS
    # ========================================================================

    async def create_session(self, session: Session) -> Result[Session]:
        """
        Create a new session in Neo4j.

        Creates both the Session node and HAS_SESSION relationship to User.

        Args:
            session: Session domain model

        Returns:
            Result[Session]: Created session or error
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            CREATE (s:Session {
                uid: $uid,
                session_token: $session_token,
                user_uid: $user_uid,
                created_at: datetime($created_at),
                expires_at: datetime($expires_at),
                last_active_at: datetime($last_active_at),
                ip_address: $ip_address,
                user_agent: $user_agent,
                is_valid: $is_valid,
                user_is_active: $user_is_active
            })
            CREATE (u)-[:HAS_SESSION]->(s)
            RETURN s
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(
                    query,
                    {
                        "uid": session.uid,
                        "session_token": session.session_token,
                        "user_uid": session.user_uid,
                        "created_at": session.created_at.isoformat(),
                        "expires_at": session.expires_at.isoformat(),
                        "last_active_at": session.last_active_at.isoformat(),
                        "ip_address": session.ip_address,
                        "user_agent": session.user_agent,
                        "is_valid": session.is_valid,
                        "user_is_active": session.user_is_active,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="create_session",
                            message="Failed to create session - user may not exist",
                        )
                    )

                self.logger.info(f"Created session: {session.uid} for user: {session.user_uid}")
                return Result.ok(session)

        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            return Result.fail(Errors.database(operation="create_session", message=str(e)))

    async def get_session_by_token(self, session_token: str) -> Result[Session | None]:
        """
        Get session by token value.

        Args:
            session_token: The secure session token from cookie

        Returns:
            Result[Session | None]: Session if found and valid, None otherwise
        """
        try:
            query = """
            MATCH (s:Session {session_token: $token})
            RETURN s
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query, {"token": session_token})
                record = await result.single()

                if not record:
                    return Result.ok(None)

                node = dict(record["s"])
                session = self._node_to_session(node)
                return Result.ok(session)

        except Exception as e:
            self.logger.error(f"Failed to get session by token: {e}")
            return Result.fail(Errors.database(operation="get_session_by_token", message=str(e)))

    async def get_session_by_uid(self, session_uid: str) -> Result[Session | None]:
        """
        Get session by UID.

        Args:
            session_uid: Session unique identifier

        Returns:
            Result[Session | None]: Session if found, None otherwise
        """
        try:
            query = """
            MATCH (s:Session {uid: $uid})
            RETURN s
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query, {"uid": session_uid})
                record = await result.single()

                if not record:
                    return Result.ok(None)

                node = dict(record["s"])
                session = self._node_to_session(node)
                return Result.ok(session)

        except Exception as e:
            self.logger.error(f"Failed to get session by UID: {e}")
            return Result.fail(Errors.database(operation="get_session_by_uid", message=str(e)))

    async def update_last_active(
        self, session_token: str, batch_interval_seconds: int = 300
    ) -> Result[bool]:
        """
        Update session's last_active_at timestamp with batching.

        Only updates if the session's last_active_at is older than the batch interval.
        This reduces write load by ~80% by avoiding updates on every single request.

        Args:
            session_token: Session token to update
            batch_interval_seconds: Minimum seconds between updates (default: 300 = 5 minutes)

        Returns:
            Result[bool]: True if updated, False if session not found or update skipped
        """
        try:
            # Only update if last_active_at is older than batch interval
            # This dramatically reduces DB writes while still tracking activity
            query = """
            MATCH (s:Session {session_token: $token, is_valid: true})
            WHERE s.last_active_at < datetime() - duration({seconds: $interval})
            SET s.last_active_at = datetime()
            RETURN s
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(
                    query, {"token": session_token, "interval": batch_interval_seconds}
                )
                record = await result.single()

                return Result.ok(record is not None)

        except Exception as e:
            self.logger.error(f"Failed to update session activity: {e}")
            return Result.fail(Errors.database(operation="update_last_active", message=str(e)))

    async def invalidate_session(self, session_token: str) -> Result[bool]:
        """
        Invalidate a session (logout).

        Marks session as invalid rather than deleting for audit trail.

        Args:
            session_token: Session token to invalidate

        Returns:
            Result[bool]: True if invalidated, False if not found
        """
        try:
            query = """
            MATCH (s:Session {session_token: $token})
            SET s.is_valid = false
            RETURN s
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query, {"token": session_token})
                record = await result.single()

                if record:
                    self.logger.info(f"Invalidated session with token: {session_token[:8]}...")

                return Result.ok(record is not None)

        except Exception as e:
            self.logger.error(f"Failed to invalidate session: {e}")
            return Result.fail(Errors.database(operation="invalidate_session", message=str(e)))

    async def invalidate_all_user_sessions(self, user_uid: str) -> Result[int]:
        """
        Invalidate all sessions for a user.

        Used for security events like password change.

        Args:
            user_uid: User whose sessions to invalidate

        Returns:
            Result[int]: Number of sessions invalidated
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[:HAS_SESSION]->(s:Session)
            WHERE s.is_valid = true
            SET s.is_valid = false
            RETURN count(s) as invalidated_count
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query, {"user_uid": user_uid})
                record = await result.single()

                count = record["invalidated_count"] if record else 0
                self.logger.info(f"Invalidated {count} sessions for user: {user_uid}")
                return Result.ok(count)

        except Exception as e:
            self.logger.error(f"Failed to invalidate user sessions: {e}")
            return Result.fail(
                Errors.database(operation="invalidate_all_user_sessions", message=str(e))
            )

    async def cleanup_expired_sessions(self) -> Result[int]:
        """
        Delete expired sessions.

        Should be called periodically (e.g., daily) to clean up old sessions.

        Returns:
            Result[int]: Number of sessions deleted
        """
        try:
            query = """
            MATCH (s:Session)
            WHERE s.expires_at < datetime()
            DETACH DELETE s
            RETURN count(s) as deleted_count
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query)
                record = await result.single()

                count = record["deleted_count"] if record else 0
                self.logger.info(f"Cleaned up {count} expired sessions")
                return Result.ok(count)

        except Exception as e:
            self.logger.error(f"Failed to cleanup expired sessions: {e}")
            return Result.fail(
                Errors.database(operation="cleanup_expired_sessions", message=str(e))
            )

    # Query constants for get_user_sessions (no dynamic string interpolation)
    _QUERY_USER_SESSIONS_VALID_ONLY = """
        MATCH (u:User {uid: $user_uid})-[:HAS_SESSION]->(s:Session)
        WHERE s.is_valid = true
        RETURN s
        ORDER BY s.created_at DESC
    """

    _QUERY_USER_SESSIONS_ALL = """
        MATCH (u:User {uid: $user_uid})-[:HAS_SESSION]->(s:Session)
        RETURN s
        ORDER BY s.created_at DESC
    """

    async def get_user_sessions(
        self, user_uid: str, valid_only: bool = True
    ) -> Result[list[Session]]:
        """
        Get all sessions for a user.

        Args:
            user_uid: User UID
            valid_only: If True, only return valid (not invalidated) sessions

        Returns:
            Result[list[Session]]: User's sessions
        """
        try:
            # Use explicit query constants instead of dynamic string interpolation
            query = (
                self._QUERY_USER_SESSIONS_VALID_ONLY
                if valid_only
                else self._QUERY_USER_SESSIONS_ALL
            )

            async with self.driver.session() as db_session:
                result = await db_session.run(query, {"user_uid": user_uid})
                records = [record async for record in result]

                sessions = [self._node_to_session(dict(r["s"])) for r in records]
                return Result.ok(sessions)

        except Exception as e:
            self.logger.error(f"Failed to get user sessions: {e}")
            return Result.fail(Errors.database(operation="get_user_sessions", message=str(e)))

    # ========================================================================
    # AUTH EVENT LOGGING (AUDIT TRAIL)
    # ========================================================================

    async def log_auth_event(self, event: AuthEvent) -> Result[AuthEvent]:
        """
        Log an authentication event.

        Creates AuthEvent node and links to User if user_uid is provided.

        Args:
            event: AuthEvent to log

        Returns:
            Result[AuthEvent]: Logged event or error
        """
        try:
            # Base query creates the event node
            if event.user_uid:
                # Link to user if we have a user_uid
                query = """
                MATCH (u:User {uid: $user_uid})
                CREATE (e:AuthEvent {
                    uid: $uid,
                    event_type: $event_type,
                    timestamp: datetime($timestamp),
                    ip_address: $ip_address,
                    user_agent: $user_agent,
                    user_uid: $user_uid,
                    email: $email,
                    session_uid: $session_uid,
                    metadata: $metadata
                })
                CREATE (u)-[:HAD_AUTH_EVENT]->(e)
                RETURN e
                """
            else:
                # No user link (e.g., failed login with wrong email)
                query = """
                CREATE (e:AuthEvent {
                    uid: $uid,
                    event_type: $event_type,
                    timestamp: datetime($timestamp),
                    ip_address: $ip_address,
                    user_agent: $user_agent,
                    user_uid: $user_uid,
                    email: $email,
                    session_uid: $session_uid,
                    metadata: $metadata
                })
                RETURN e
                """

            import json

            async with self.driver.session() as db_session:
                result = await db_session.run(
                    query,
                    {
                        "uid": event.uid,
                        "event_type": event.event_type.value,
                        "timestamp": event.timestamp.isoformat(),
                        "ip_address": event.ip_address,
                        "user_agent": event.user_agent,
                        "user_uid": event.user_uid,
                        "email": event.email,
                        "session_uid": event.session_uid,
                        "metadata": json.dumps(event.metadata) if event.metadata else "{}",
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="log_auth_event",
                            message="Failed to create auth event",
                        )
                    )

                self.logger.info(
                    f"Logged auth event: {event.event_type.value} for {event.email or event.user_uid}"
                )
                return Result.ok(event)

        except Exception as e:
            self.logger.error(f"Failed to log auth event: {e}")
            return Result.fail(Errors.database(operation="log_auth_event", message=str(e)))

    async def count_recent_failed_attempts(
        self, email: str, minutes: int = LOCKOUT_MINUTES
    ) -> Result[int]:
        """
        Count recent failed login attempts for rate limiting.

        Args:
            email: Email to check
            minutes: Time window in minutes

        Returns:
            Result[int]: Number of failed attempts
        """
        try:
            query = """
            MATCH (e:AuthEvent)
            WHERE e.email = $email
              AND e.event_type = 'LOGIN_FAILED'
              AND e.timestamp > datetime() - duration({minutes: $minutes})
            RETURN count(e) as failed_count
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query, {"email": email, "minutes": minutes})
                record = await result.single()

                count = record["failed_count"] if record else 0
                return Result.ok(count)

        except Exception as e:
            self.logger.error(f"Failed to count failed attempts: {e}")
            return Result.fail(
                Errors.database(operation="count_recent_failed_attempts", message=str(e))
            )

    async def is_account_locked(self, email: str) -> Result[bool]:
        """
        Check if account is locked due to too many failed attempts.

        Args:
            email: Email to check

        Returns:
            Result[bool]: True if locked, False otherwise
        """
        count_result = await self.count_recent_failed_attempts(email)
        if count_result.is_error:
            return Result.fail(count_result)

        return Result.ok(count_result.value >= MAX_FAILED_ATTEMPTS)

    # ========================================================================
    # PASSWORD RESET TOKEN MANAGEMENT
    # ========================================================================

    async def create_reset_token(self, token: PasswordResetToken) -> Result[PasswordResetToken]:
        """
        Create a password reset token.

        Args:
            token: PasswordResetToken to create

        Returns:
            Result[PasswordResetToken]: Created token or error
        """
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            CREATE (t:PasswordResetToken {
                uid: $uid,
                token: $token,
                user_uid: $user_uid,
                created_at: datetime($created_at),
                expires_at: datetime($expires_at),
                is_used: $is_used,
                created_by_admin_uid: $created_by_admin_uid
            })
            CREATE (u)-[:HAS_RESET_TOKEN]->(t)
            RETURN t
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(
                    query,
                    {
                        "uid": token.uid,
                        "token": token.token,
                        "user_uid": token.user_uid,
                        "created_at": token.created_at.isoformat(),
                        "expires_at": token.expires_at.isoformat(),
                        "is_used": token.is_used,
                        "created_by_admin_uid": token.created_by_admin_uid,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            operation="create_reset_token",
                            message="Failed to create reset token - user may not exist",
                        )
                    )

                self.logger.info(f"Created reset token for user: {token.user_uid}")
                return Result.ok(token)

        except Exception as e:
            self.logger.error(f"Failed to create reset token: {e}")
            return Result.fail(Errors.database(operation="create_reset_token", message=str(e)))

    async def get_reset_token(self, token_value: str) -> Result[PasswordResetToken | None]:
        """
        Get password reset token by token value.

        Args:
            token_value: The token string

        Returns:
            Result[PasswordResetToken | None]: Token if found and valid
        """
        try:
            query = """
            MATCH (t:PasswordResetToken {token: $token})
            RETURN t
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query, {"token": token_value})
                record = await result.single()

                if not record:
                    return Result.ok(None)

                node = dict(record["t"])
                token = self._node_to_reset_token(node)
                return Result.ok(token)

        except Exception as e:
            self.logger.error(f"Failed to get reset token: {e}")
            return Result.fail(Errors.database(operation="get_reset_token", message=str(e)))

    async def mark_reset_token_used(self, token_value: str) -> Result[bool]:
        """
        Mark a reset token as used.

        Args:
            token_value: The token string

        Returns:
            Result[bool]: True if marked, False if not found
        """
        try:
            query = """
            MATCH (t:PasswordResetToken {token: $token})
            SET t.is_used = true
            RETURN t
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query, {"token": token_value})
                record = await result.single()

                return Result.ok(record is not None)

        except Exception as e:
            self.logger.error(f"Failed to mark reset token used: {e}")
            return Result.fail(Errors.database(operation="mark_reset_token_used", message=str(e)))

    async def cleanup_expired_tokens(self) -> Result[int]:
        """
        Delete expired password reset tokens.

        Returns:
            Result[int]: Number of tokens deleted
        """
        try:
            query = """
            MATCH (t:PasswordResetToken)
            WHERE t.expires_at < datetime() OR t.is_used = true
            DETACH DELETE t
            RETURN count(t) as deleted_count
            """

            async with self.driver.session() as db_session:
                result = await db_session.run(query)
                record = await result.single()

                count = record["deleted_count"] if record else 0
                self.logger.info(f"Cleaned up {count} expired/used reset tokens")
                return Result.ok(count)

        except Exception as e:
            self.logger.error(f"Failed to cleanup expired tokens: {e}")
            return Result.fail(Errors.database(operation="cleanup_expired_tokens", message=str(e)))

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _node_to_session(self, node: dict[str, Any]) -> Session:
        """Convert Neo4j node to Session domain model."""
        return Session(
            uid=node["uid"],
            session_token=node["session_token"],
            user_uid=node["user_uid"],
            created_at=self._parse_datetime(node["created_at"]),
            expires_at=self._parse_datetime(node["expires_at"]),
            last_active_at=self._parse_datetime(node["last_active_at"]),
            ip_address=node["ip_address"],
            user_agent=node["user_agent"],
            is_valid=node.get("is_valid", True),
            user_is_active=node.get("user_is_active", True),
        )

    def _node_to_reset_token(self, node: dict[str, Any]) -> PasswordResetToken:
        """Convert Neo4j node to PasswordResetToken domain model."""
        return PasswordResetToken(
            uid=node["uid"],
            token=node["token"],
            user_uid=node["user_uid"],
            created_at=self._parse_datetime(node["created_at"]),
            expires_at=self._parse_datetime(node["expires_at"]),
            is_used=node.get("is_used", False),
            created_by_admin_uid=node.get("created_by_admin_uid"),
        )

    def _parse_datetime(self, value: Any) -> datetime:
        """
        Parse datetime from Neo4j value.

        Raises:
            ValueError: If value cannot be parsed as datetime (fail-fast, no silent fallback)
        """
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # Handle ISO format strings
            return datetime.fromisoformat(value)
        # Neo4j DateTime object - use explicit type check (SKUEL011: no hasattr)
        if isinstance(value, Neo4jDateTime):
            return cast("datetime", value.to_native())
        # Fail-fast: don't hide bugs with silent fallback
        raise ValueError(
            f"Cannot parse datetime from value of type {type(value).__name__}: {value!r}"
        )


__all__ = [
    "LOCKOUT_MINUTES",
    "MAX_FAILED_ATTEMPTS",
    "SessionBackend",
]

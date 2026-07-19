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

from typing import Any

from neo4j import AsyncDriver

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from adapters.persistence.neo4j.session_runner import Neo4jSessionRunner
from core.models.auth.auth_event import AuthEvent
from core.models.auth.password_reset_token import PasswordResetToken
from core.models.auth.session import Session, hash_session_token
from core.models.type_hints import UserUID
from core.utils.error_boundary import safe_backend_operation
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


# Rate limiting configuration
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# Per-IP throttle is intentionally LOOSER than per-account: a single office NAT
# routinely covers many users, so we want to block a single host blasting failed
# logins (distributed credential stuffing) without locking out a shared egress
# IP on a few honest typos. 20 in 15 minutes ≈ one wrong attempt every 45s —
# well above realistic human typing-error rates, well below brute-force speeds.
MAX_FAILED_ATTEMPTS_PER_IP = 20


class SessionBackend(Neo4jSessionRunner):
    """
    Neo4j backend for session persistence.

    Handles:
    - Session CRUD operations
    - Auth event logging (audit trail)
    - Rate limiting via auth event queries
    - Password reset token management

    Error boundary: every public method is wrapped in @safe_backend_operation,
    which converts Neo4j exceptions to Result.fail(Errors.database(...)).
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

    @safe_backend_operation("create_session")
    async def create_session(self, session: Session) -> Result[Session]:
        """
        Create a new session in Neo4j.

        Creates both the Session node and HAS_SESSION relationship to User.

        Args:
            session: Session domain model

        Returns:
            Result[Session]: Created session or error
        """
        query = """
        MATCH (u:User {uid: $user_uid})
        CREATE (s:Session {
            uid: $uid,
            token_hash: $token_hash,
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

        record = await self._run_single(
            query,
            {
                "uid": session.uid,
                "token_hash": session.token_hash,
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

        if not record:
            return Result.fail(
                Errors.database(
                    operation="create_session",
                    message="Failed to create session - user may not exist",
                )
            )

        self.logger.info(f"Created session: {session.uid} for user: {session.user_uid}")
        return Result.ok(session)

    @safe_backend_operation("get_session_by_token")
    async def get_session_by_token(self, session_token: str) -> Result[Session | None]:
        """
        Get session by token value.

        Hashes the incoming token and queries by token_hash (raw tokens
        are never stored in Neo4j).

        Args:
            session_token: The secure session token from cookie

        Returns:
            Result[Session | None]: Session if found and valid, None otherwise
        """
        token_hash = hash_session_token(session_token)
        query = """
        MATCH (s:Session {token_hash: $token_hash})
        RETURN s
        """

        record = await self._run_single(query, {"token_hash": token_hash})

        if not record:
            return Result.ok(None)

        return Result.ok(self._node_to_session(dict(record["s"])))

    @safe_backend_operation("get_session_by_uid")
    async def get_session_by_uid(self, session_uid: str) -> Result[Session | None]:
        """
        Get session by UID.

        Args:
            session_uid: Session unique identifier

        Returns:
            Result[Session | None]: Session if found, None otherwise
        """
        query = """
        MATCH (s:Session {uid: $uid})
        RETURN s
        """

        record = await self._run_single(query, {"uid": session_uid})

        if not record:
            return Result.ok(None)

        return Result.ok(self._node_to_session(dict(record["s"])))

    @safe_backend_operation("update_last_active")
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
        # Only update if last_active_at is older than batch interval
        # This dramatically reduces DB writes while still tracking activity
        token_hash = hash_session_token(session_token)
        query = """
        MATCH (s:Session {token_hash: $token_hash, is_valid: true})
        WHERE s.last_active_at < datetime() - duration({seconds: $interval})
        SET s.last_active_at = datetime()
        RETURN s
        """

        record = await self._run_single(
            query, {"token_hash": token_hash, "interval": batch_interval_seconds}
        )

        return Result.ok(record is not None)

    @safe_backend_operation("invalidate_session")
    async def invalidate_session(self, session_token: str) -> Result[bool]:
        """
        Invalidate a session (logout).

        Marks session as invalid rather than deleting for audit trail.

        Args:
            session_token: Session token to invalidate

        Returns:
            Result[bool]: True if invalidated, False if not found
        """
        token_hash = hash_session_token(session_token)
        query = """
        MATCH (s:Session {token_hash: $token_hash})
        SET s.is_valid = false
        RETURN s
        """

        record = await self._run_single(query, {"token_hash": token_hash})

        if record:
            self.logger.info(f"Invalidated session with token hash: {token_hash[:8]}...")

        return Result.ok(record is not None)

    @safe_backend_operation("invalidate_all_user_sessions")
    async def invalidate_all_user_sessions(self, user_uid: UserUID) -> Result[int]:
        """
        Invalidate all sessions for a user.

        Used for security events like password change.

        Args:
            user_uid: User whose sessions to invalidate

        Returns:
            Result[int]: Number of sessions invalidated
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[:HAS_SESSION]->(s:Session)
        WHERE s.is_valid = true
        SET s.is_valid = false
        RETURN count(s) as invalidated_count
        """

        record = await self._run_single(query, {"user_uid": user_uid})

        count = record["invalidated_count"] if record else 0
        self.logger.info(f"Invalidated {count} sessions for user: {user_uid}")
        return Result.ok(count)

    @safe_backend_operation("cleanup_expired_sessions")
    async def cleanup_expired_sessions(self) -> Result[int]:
        """
        Delete expired sessions.

        Should be called periodically (e.g., daily) to clean up old sessions.

        Returns:
            Result[int]: Number of sessions deleted
        """
        query = """
        MATCH (s:Session)
        WHERE s.expires_at < datetime()
        DETACH DELETE s
        RETURN count(s) as deleted_count
        """

        record = await self._run_single(query)

        count = record["deleted_count"] if record else 0
        self.logger.info(f"Cleaned up {count} expired sessions")
        return Result.ok(count)

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

    @safe_backend_operation("get_user_sessions")
    async def get_user_sessions(
        self, user_uid: UserUID, valid_only: bool = True
    ) -> Result[list[Session]]:
        """
        Get all sessions for a user.

        Args:
            user_uid: User UID
            valid_only: If True, only return valid (not invalidated) sessions

        Returns:
            Result[list[Session]]: User's sessions
        """
        # Use explicit query constants instead of dynamic string interpolation
        query = (
            self._QUERY_USER_SESSIONS_VALID_ONLY if valid_only else self._QUERY_USER_SESSIONS_ALL
        )

        async with self.driver.session() as db_session:
            result = await db_session.run(query, {"user_uid": user_uid})
            records = [record async for record in result]

        sessions = [self._node_to_session(dict(r["s"])) for r in records]
        return Result.ok(sessions)

    # ========================================================================
    # AUTH EVENT LOGGING (AUDIT TRAIL)
    # ========================================================================

    @safe_backend_operation("log_auth_event")
    async def log_auth_event(self, event: AuthEvent) -> Result[AuthEvent]:
        """
        Log an authentication event.

        Creates AuthEvent node and links to User if user_uid is provided.

        Args:
            event: AuthEvent to log

        Returns:
            Result[AuthEvent]: Logged event or error
        """
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

        record = await self._run_single(
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

    @safe_backend_operation("count_recent_failed_attempts")
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
        query = """
        MATCH (e:AuthEvent)
        WHERE e.email = $email
          AND e.event_type = 'LOGIN_FAILED'
          AND e.timestamp > datetime() - duration({minutes: $minutes})
        RETURN count(e) as failed_count
        """

        record = await self._run_single(query, {"email": email, "minutes": minutes})

        count = record["failed_count"] if record else 0
        return Result.ok(count)

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

    @safe_backend_operation("count_recent_failed_attempts_by_ip")
    async def count_recent_failed_attempts_by_ip(
        self, ip_address: str, minutes: int = LOCKOUT_MINUTES
    ) -> Result[int]:
        """Count recent LOGIN_FAILED events from a single IP, across all accounts.

        Distinct attack-surface from the per-account counter: catches a single
        host fanning out across many emails (distributed credential stuffing)
        rather than a brute force on one account.
        """
        query = """
        MATCH (e:AuthEvent)
        WHERE e.ip_address = $ip_address
          AND e.event_type = 'LOGIN_FAILED'
          AND e.timestamp > datetime() - duration({minutes: $minutes})
        RETURN count(e) as failed_count
        """

        record = await self._run_single(query, {"ip_address": ip_address, "minutes": minutes})

        count = record["failed_count"] if record else 0
        return Result.ok(count)

    async def is_ip_rate_limited(self, ip_address: str) -> Result[bool]:
        """Check if an IP has exceeded MAX_FAILED_ATTEMPTS_PER_IP in the lockout window.

        The "unknown" sentinel (used for CLI / background entry points) is
        always allowed — throttling without a real IP would block every
        non-HTTP login path.
        """
        if not ip_address or ip_address == "unknown":
            return Result.ok(False)

        count_result = await self.count_recent_failed_attempts_by_ip(ip_address)
        if count_result.is_error:
            return Result.fail(count_result)

        return Result.ok(count_result.value >= MAX_FAILED_ATTEMPTS_PER_IP)

    # ========================================================================
    # PASSWORD RESET TOKEN MANAGEMENT
    # ========================================================================

    @safe_backend_operation("create_reset_token")
    async def create_reset_token(self, token: PasswordResetToken) -> Result[PasswordResetToken]:
        """
        Create a password reset token.

        Args:
            token: PasswordResetToken to create

        Returns:
            Result[PasswordResetToken]: Created token or error
        """
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

        record = await self._run_single(
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

        if not record:
            return Result.fail(
                Errors.database(
                    operation="create_reset_token",
                    message="Failed to create reset token - user may not exist",
                )
            )

        self.logger.info(f"Created reset token for user: {token.user_uid}")
        return Result.ok(token)

    @safe_backend_operation("get_reset_token")
    async def get_reset_token(self, token_value: str) -> Result[PasswordResetToken | None]:
        """
        Get password reset token by token value.

        Args:
            token_value: The token string

        Returns:
            Result[PasswordResetToken | None]: Token if found and valid
        """
        query = """
        MATCH (t:PasswordResetToken {token: $token})
        RETURN t
        """

        record = await self._run_single(query, {"token": token_value})

        if not record:
            return Result.ok(None)

        return Result.ok(from_neo4j_node(dict(record["t"]), PasswordResetToken))

    @safe_backend_operation("mark_reset_token_used")
    async def mark_reset_token_used(self, token_value: str) -> Result[bool]:
        """
        Mark a reset token as used.

        Args:
            token_value: The token string

        Returns:
            Result[bool]: True if marked, False if not found
        """
        query = """
        MATCH (t:PasswordResetToken {token: $token})
        SET t.is_used = true
        RETURN t
        """

        record = await self._run_single(query, {"token": token_value})

        return Result.ok(record is not None)

    @safe_backend_operation("cleanup_expired_tokens")
    async def cleanup_expired_tokens(self) -> Result[int]:
        """
        Delete expired password reset tokens.

        Returns:
            Result[int]: Number of tokens deleted
        """
        query = """
        MATCH (t:PasswordResetToken)
        WHERE t.expires_at < datetime() OR t.is_used = true
        DETACH DELETE t
        RETURN count(t) as deleted_count
        """

        record = await self._run_single(query)

        count = record["deleted_count"] if record else 0
        self.logger.info(f"Cleaned up {count} expired/used reset tokens")
        return Result.ok(count)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    @staticmethod
    def _node_to_session(node: dict[str, Any]) -> Session:
        """Convert Neo4j node to Session domain model via the shared mapper.

        The raw session token is never stored in Neo4j (only token_hash), so
        the required ``session_token`` field is supplied as "" before handing
        the node to ``from_neo4j_node`` — which owns all Neo4j-temporal /
        ISO-string datetime conversion.
        """
        return from_neo4j_node({"session_token": "", **node}, Session)


__all__ = [
    "LOCKOUT_MINUTES",
    "MAX_FAILED_ATTEMPTS",
    "MAX_FAILED_ATTEMPTS_PER_IP",
    "SessionBackend",
]

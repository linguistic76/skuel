"""
Session Model
=============

Graph-native session stored as Neo4j node.

Design:
- Session token stored in HTTP-only cookie
- Session data (user, expiry, metadata) stored in Neo4j
- Validates on each request by querying Neo4j
- Sliding expiration: last_active_at updated on use

Neo4j Schema:
    (:Session {
        uid: "session_{uuid}",
        token_hash: "{sha256_hex}",
        user_uid: "user_5f2c8e1a9b3d7046",
        created_at: datetime(),
        expires_at: datetime(),
        last_active_at: datetime(),
        ip_address: "192.168.1.1",
        user_agent: "Mozilla/5.0...",
        is_valid: true,
        user_is_active: true,
        seen_day: "{YYYY-MM-DD}"
    })

    The raw token lives only in the HTTP-only cookie: ``create_session`` hands it
    out beside the session it mints (``IssuedSession``), and the session holds
    only its hash. Neo4j stores token_hash (SHA-256) — raw tokens are never
    persisted.

    (user:User)-[:HAS_SESSION]->(session:Session)
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from core.models.type_hints import UserUID
from core.utils.timestamp_helpers import as_utc, now_utc
from core.utils.uid_generator import UIDGenerator

# Session configuration
SESSION_TOKEN_BYTES = 32  # 256-bit tokens
SESSION_EXPIRY_DAYS = 30  # 30-day sessions


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def generate_session_uid() -> str:
    """Generate a unique session UID."""
    return UIDGenerator.generate_random_uid("session")


def hash_session_token(token: str) -> str:
    """One-way SHA-256 hash for session token storage in Neo4j."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Session:
    """
    User session stored as Neo4j node.

    Immutable session model following three-tier architecture.

    Attributes:
        uid: Unique session identifier (e.g., "session_abc123...")
        user_uid: Reference to owning user
        created_at: When session was created
        expires_at: When session expires (hard limit)
        last_active_at: Last activity timestamp (for sliding expiration)
        ip_address: Client IP address (for audit)
        user_agent: Client user agent (for audit)
        is_valid: Whether session is valid (can be invalidated on logout)
        user_is_active: The user's active status when the session was minted
        token_hash: SHA-256 hash of the session's token, the property it is found by
    """

    uid: str
    user_uid: UserUID
    created_at: datetime
    expires_at: datetime
    last_active_at: datetime
    ip_address: str
    user_agent: str
    is_valid: bool = True
    # A snapshot at the mint; validation reads the live User, never this.
    user_is_active: bool = True
    token_hash: str = ""  # SHA-256 hash of the session's token, stored in Neo4j

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return now_utc() > as_utc(self.expires_at)

    def is_active(self) -> bool:
        """Check if session is valid and not expired."""
        return self.is_valid and not self.is_expired()

    def time_until_expiry(self) -> timedelta:
        """Get time remaining until expiry."""
        return as_utc(self.expires_at) - now_utc()

    def should_refresh(self, threshold_days: int = 7) -> bool:
        """
        Check if session should be refreshed.

        Returns True if less than threshold_days remain.
        """
        return self.time_until_expiry() < timedelta(days=threshold_days)


@dataclass(frozen=True)
class IssuedSession:
    """A session just minted, and the raw token its cookie carries.

    The graph stores only the token's hash, so the token exists here alone,
    between the mint and the cookie.
    """

    session: Session
    # repr=False: the raw token authenticates the bearer. Keeping it out of
    # repr() keeps it out of log lines, tracebacks and debugger frames that
    # render the dataclass.
    token: str = field(repr=False)


def create_session(
    user_uid: UserUID,
    ip_address: str,
    user_agent: str,
    expiry_days: int = SESSION_EXPIRY_DAYS,
    user_is_active: bool = True,
) -> IssuedSession:
    """
    Mint a new session and the token that authenticates it.

    Args:
        user_uid: The user this session belongs to
        ip_address: Client IP address
        user_agent: Client user agent string
        expiry_days: Days until session expires (default: 30)
        user_is_active: The user's active status at the mint (a snapshot only)

    Returns:
        The session, holding the token's hash, and the token for the cookie
    """
    now = datetime.now(UTC)
    token = generate_session_token()
    session = Session(
        uid=generate_session_uid(),
        user_uid=user_uid,
        created_at=now,
        expires_at=now + timedelta(days=expiry_days),
        last_active_at=now,
        ip_address=ip_address,
        user_agent=user_agent,
        is_valid=True,
        user_is_active=user_is_active,
        token_hash=hash_session_token(token),
    )
    return IssuedSession(session=session, token=token)


__all__ = [
    "SESSION_EXPIRY_DAYS",
    "SESSION_TOKEN_BYTES",
    "IssuedSession",
    "Session",
    "create_session",
    "generate_session_token",
    "generate_session_uid",
    "hash_session_token",
]

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
        session_token: "{secure_token}",
        user_uid: "user_xxx",
        created_at: datetime(),
        expires_at: datetime(),
        last_active_at: datetime(),
        ip_address: "192.168.1.1",
        user_agent: "Mozilla/5.0...",
        is_valid: true
    })

    (user:User)-[:HAS_SESSION]->(session:Session)
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Session configuration
SESSION_TOKEN_BYTES = 32  # 256-bit tokens
SESSION_EXPIRY_DAYS = 30  # 30-day sessions


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def generate_session_uid() -> str:
    """Generate a unique session UID."""
    return f"session_{secrets.token_hex(16)}"


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
        session_token: Secure token stored in HTTP-only cookie
        user_uid: Reference to owning user
        created_at: When session was created
        expires_at: When session expires (hard limit)
        last_active_at: Last activity timestamp (for sliding expiration)
        ip_address: Client IP address (for audit)
        user_agent: Client user agent (for audit)
        is_valid: Whether session is valid (can be invalidated on logout)
    """

    uid: str
    session_token: str
    user_uid: str
    created_at: datetime
    expires_at: datetime
    last_active_at: datetime
    ip_address: str
    user_agent: str
    is_valid: bool = True
    # Cached user data (avoid DB lookup on every validation)
    user_is_active: bool = True  # Cached at session creation
    token_hash: str = ""  # SHA-256 hash of session_token, stored in Neo4j

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def is_active(self) -> bool:
        """Check if session is valid and not expired."""
        return self.is_valid and not self.is_expired()

    def time_until_expiry(self) -> timedelta:
        """Get time remaining until expiry."""
        return self.expires_at - datetime.now(timezone.utc)

    def should_refresh(self, threshold_days: int = 7) -> bool:
        """
        Check if session should be refreshed.

        Returns True if less than threshold_days remain.
        """
        return self.time_until_expiry() < timedelta(days=threshold_days)

    def with_updated_activity(self) -> "Session":
        """
        Create new session with updated last_active_at.

        Since Session is frozen, this returns a new instance.
        Used for sliding expiration updates.
        """
        # Note: We don't extend expires_at to maintain hard limit
        return Session(
            uid=self.uid,
            session_token=self.session_token,
            user_uid=self.user_uid,
            created_at=self.created_at,
            expires_at=self.expires_at,
            last_active_at=datetime.now(timezone.utc),
            ip_address=self.ip_address,
            user_agent=self.user_agent,
            is_valid=self.is_valid,
            user_is_active=self.user_is_active,
            token_hash=self.token_hash,
        )

    def invalidate(self) -> "Session":
        """
        Create invalidated version of this session.

        Used for logout - keeps audit trail but marks as invalid.
        """
        return Session(
            uid=self.uid,
            session_token=self.session_token,
            user_uid=self.user_uid,
            created_at=self.created_at,
            expires_at=self.expires_at,
            last_active_at=self.last_active_at,
            ip_address=self.ip_address,
            user_agent=self.user_agent,
            is_valid=False,
            user_is_active=self.user_is_active,
            token_hash=self.token_hash,
        )


def create_session(
    user_uid: str,
    ip_address: str,
    user_agent: str,
    expiry_days: int = SESSION_EXPIRY_DAYS,
    user_is_active: bool = True,
) -> Session:
    """
    Factory function to create a new session.

    Args:
        user_uid: The user this session belongs to
        ip_address: Client IP address
        user_agent: Client user agent string
        expiry_days: Days until session expires (default: 30)
        user_is_active: Cached user active status (avoid DB lookup on validation)

    Returns:
        New Session instance with secure token
    """
    now = datetime.now(timezone.utc)
    token = generate_session_token()
    return Session(
        uid=generate_session_uid(),
        session_token=token,
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


__all__ = [
    "SESSION_EXPIRY_DAYS",
    "SESSION_TOKEN_BYTES",
    "Session",
    "create_session",
    "generate_session_token",
    "generate_session_uid",
    "hash_session_token",
]

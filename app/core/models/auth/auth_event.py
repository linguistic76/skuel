"""
Auth Event Model
================

Audit trail events for authentication actions.

Every authentication action (login, logout, failed attempt, password change)
creates an AuthEvent node in Neo4j for security auditing.

Neo4j Schema:
    (:AuthEvent {
        uid: "auth_{uuid}",
        event_type: "LOGIN_SUCCESS",
        user_uid: "user_xxx",  # May be null for failed logins
        email: "user@example.com",  # For failed login tracking
        timestamp: datetime(),
        ip_address: "192.168.1.1",
        user_agent: "Mozilla/5.0...",
        metadata: "{...}"
    })

    (user:User)-[:HAD_AUTH_EVENT]->(event:AuthEvent)

Rate Limiting:
    AuthEvents are used for rate limiting by counting recent LOGIN_FAILED events:

    MATCH (e:AuthEvent {event_type: 'LOGIN_FAILED', email: $email})
    WHERE e.timestamp > datetime() - duration({minutes: 15})
    RETURN count(e) as failed_attempts
"""

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AuthEventType(str, Enum):
    """Types of authentication events for audit trail."""

    # Login events
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"

    # Session events
    SESSION_CREATED = "SESSION_CREATED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_INVALIDATED = "SESSION_INVALIDATED"

    # Password events
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_COMPLETED = "PASSWORD_RESET_COMPLETED"

    # Account events
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED"

    def is_success_event(self) -> bool:
        """Check if this is a successful authentication event."""
        return self in {
            AuthEventType.LOGIN_SUCCESS,
            AuthEventType.SESSION_CREATED,
            AuthEventType.PASSWORD_CHANGED,
            AuthEventType.PASSWORD_RESET_COMPLETED,
            AuthEventType.ACCOUNT_CREATED,
            AuthEventType.ACCOUNT_UNLOCKED,
        }

    def is_failure_event(self) -> bool:
        """Check if this is a failed authentication event."""
        return self in {
            AuthEventType.LOGIN_FAILED,
            AuthEventType.ACCOUNT_LOCKED,
        }

    def is_security_relevant(self) -> bool:
        """Check if this event type is security-relevant for alerting."""
        return self in {
            AuthEventType.LOGIN_FAILED,
            AuthEventType.PASSWORD_CHANGED,
            AuthEventType.PASSWORD_RESET_REQUESTED,
            AuthEventType.ACCOUNT_LOCKED,
        }


def generate_auth_event_uid() -> str:
    """Generate a unique auth event UID."""
    return f"auth_{secrets.token_hex(16)}"


@dataclass(frozen=True)
class AuthEvent:
    """
    Authentication audit event stored as Neo4j node.

    Immutable event record following three-tier architecture.

    Attributes:
        uid: Unique event identifier
        event_type: Type of authentication event
        timestamp: When event occurred
        ip_address: Client IP address
        user_agent: Client user agent
        user_uid: User involved (may be None for failed logins)
        email: Email involved (for tracking failed logins by email)
        session_uid: Associated session (if applicable)
        metadata: Additional event-specific data
    """

    uid: str
    event_type: AuthEventType
    timestamp: datetime
    ip_address: str
    user_agent: str
    user_uid: str | None = None
    email: str | None = None
    session_uid: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_recent(self, minutes: int = 15) -> bool:
        """Check if event occurred within the last N minutes."""
        from datetime import timedelta

        return (datetime.now(timezone.utc) - self.timestamp) < timedelta(minutes=minutes)

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for logging."""
        return {
            "uid": self.uid,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "ip_address": self.ip_address,
            "user_uid": self.user_uid,
            "email": self.email,
        }


def create_auth_event(
    event_type: AuthEventType,
    ip_address: str,
    user_agent: str,
    user_uid: str | None = None,
    email: str | None = None,
    session_uid: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthEvent:
    """
    Factory function to create an auth event.

    Args:
        event_type: Type of authentication event
        ip_address: Client IP address
        user_agent: Client user agent string
        user_uid: User involved (optional for failed logins)
        email: Email involved (for failed login tracking)
        session_uid: Associated session UID (optional)
        metadata: Additional event-specific data

    Returns:
        New AuthEvent instance
    """
    return AuthEvent(
        uid=generate_auth_event_uid(),
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        ip_address=ip_address,
        user_agent=user_agent,
        user_uid=user_uid,
        email=email,
        session_uid=session_uid,
        metadata=metadata or {},
    )


__all__ = [
    "AuthEvent",
    "AuthEventType",
    "create_auth_event",
    "generate_auth_event_uid",
]

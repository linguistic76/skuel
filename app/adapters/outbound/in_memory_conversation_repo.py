"""
In-Memory Conversation Repository
=================================

Simple in-memory implementation of ConversationRepoPort for development and testing.
This adapter provides basic persistence without external dependencies.

For production, replace with a proper database adapter (Neo4j, PostgreSQL, etc.).
"""

__version__ = "1.0"


from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from core.utils.logging import get_logger


# ConversationSession stub (module core.models.conversation not implemented)
@dataclass
class ConversationSession:
    """Stub type for conversation session - module not yet implemented."""

    session_id: str
    user_uid: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_activity: datetime | None = None  # Initialized in __post_init__

    def __post_init__(self) -> None:
        if self.last_activity is None:
            self.last_activity = datetime.now()

    def is_active(self, timeout_minutes: int = 60) -> bool:
        """Check if session is still active based on timeout."""
        if self.last_activity is None:
            return False
        return datetime.now() - self.last_activity < timedelta(minutes=timeout_minutes)


class PersistenceError(Exception):
    """Error during persistence operations."""

    pass


logger = get_logger(__name__)


class InMemoryConversationRepo:
    """
    In-memory implementation of ConversationRepoPort.

    Stores sessions in process memory. Data is lost on restart.
    Suitable for development, testing, and single-instance deployments.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._user_sessions: dict[str, list[str]] = {}  # user_uid -> session_ids
        logger.info("InMemoryConversationRepo initialized")

    async def save_session(self, session: ConversationSession) -> None:
        """Save session to memory"""
        try:
            self._sessions[session.session_id] = session

            # Update user session tracking
            if session.user_uid not in self._user_sessions:
                self._user_sessions[session.user_uid] = []

            if session.session_id not in self._user_sessions[session.user_uid]:
                self._user_sessions[session.user_uid].append(session.session_id)

            logger.debug(f"Session {session.session_id} saved for user {session.user_uid}")

        except Exception as e:
            raise PersistenceError(f"Failed to save session {session.session_id}: {e}") from e

    async def load_session(self, session_id: str) -> ConversationSession | None:
        """Load session from memory"""
        try:
            session = self._sessions.get(session_id)
            if session:
                logger.debug(f"Session {session_id} loaded")
            else:
                logger.debug(f"Session {session_id} not found")
            return session

        except Exception as e:
            raise PersistenceError(f"Failed to load session {session_id}: {e}") from e

    async def load_user_sessions(
        self, user_uid: str, limit: int = 10, active_only: bool = True
    ) -> list[ConversationSession]:
        """Load user sessions from memory"""
        try:
            session_ids = self._user_sessions.get(user_uid, [])
            sessions = []

            for session_id in session_ids[-limit:]:  # Get most recent
                session = self._sessions.get(session_id)
                if session and (not active_only or session.is_active()):
                    sessions.append(session)

            # Sort by last activity, most recent first
            def get_last_activity(s) -> Any:
                return s.last_activity

            sessions.sort(key=get_last_activity, reverse=True)

            logger.debug(f"Loaded {len(sessions)} sessions for user {user_uid}")
            return sessions

        except Exception as e:
            raise PersistenceError(f"Failed to load sessions for user {user_uid}: {e}") from e

    async def delete_session(self, session_id: str) -> bool:
        """Delete session from memory"""
        try:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                user_uid = session.user_uid

                # Remove from main storage
                del self._sessions[session_id]

                # Remove from user tracking
                if user_uid in self._user_sessions:
                    from contextlib import suppress

                    with suppress(ValueError):  # Session ID may not be in list
                        self._user_sessions[user_uid].remove(session_id)

                logger.debug(f"Session {session_id} deleted")
                return True

            logger.debug(f"Session {session_id} not found for deletion")
            return False

        except Exception as e:
            raise PersistenceError(f"Failed to delete session {session_id}: {e}") from e

    async def cleanup_inactive_sessions(self, timeout_minutes: int = 60) -> int:
        """Remove inactive sessions"""
        try:
            inactive_sessions = []

            for session_id, session in self._sessions.items():
                if not session.is_active(timeout_minutes):
                    inactive_sessions.append(session_id)

            # Delete inactive sessions
            deleted_count = 0
            for session_id in inactive_sessions:
                if await self.delete_session(session_id):
                    deleted_count += 1

            logger.info(f"Cleaned up {deleted_count} inactive sessions")
            return deleted_count

        except Exception as e:
            raise PersistenceError(f"Failed to cleanup sessions: {e}") from e

    # Additional utility methods for in-memory implementation
    def get_total_sessions(self) -> int:
        """Get total number of stored sessions"""
        return len(self._sessions)

    def get_active_session_count(self) -> int:
        """Get count of currently active sessions"""
        return sum(1 for session in self._sessions.values() if session.is_active())

    def clear_all_sessions(self) -> None:
        """Clear all sessions (useful for testing)"""
        self._sessions.clear()
        self._user_sessions.clear()
        logger.info("All sessions cleared from memory")

"""
Conversation Service — Owner-Private Discussion Persistence (ADR-078)
====================================================================

Thin, understanding-agnostic service over ``ConversationBackend``. It is the
owner-private access boundary: every method is keyed on ``user_uid`` and a
non-owner gets a not-found (404-not-403, SKUEL ownership convention). It
persists sessions/turns and *nothing else* — no embeddings, no MENTIONS edges,
no context contribution. That opt-out IS the journals understanding wall
(ADR-078 §2); a future Askesis adoption would opt understanding wiring back in
*above* this store, never inside it.

Backend: adapters/persistence/neo4j/backends/conversation_backend.py
See: /docs/decisions/ADR-078-discussion-sessions-stored-not-understood.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.models.conversation import (
    ConversationSession,
    ConversationTurn,
    generate_session_id,
    generate_turn_id,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.type_hints import Neo4jProperties, UserUID
    from core.ports.conversation_protocols import ConversationBackendOperations

logger = get_logger("skuel.services.conversation")

# The revisit list is a human-scannable surface, not a bulk export — cap it.
_DEFAULT_SESSION_LIMIT = 50


def _required_datetime(value: object) -> datetime:
    """Narrow a backend property that MUST be a datetime (wiring-defect guard)."""
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime conversation property, got {type(value).__name__}")
    return value


def _session_from_props(props: Neo4jProperties) -> ConversationSession:
    """Build the frozen ConversationSession model from backend properties."""
    return ConversationSession(
        session_id=str(props["session_id"]),
        user_uid=str(props["user_uid"]),
        kind=str(props["kind"]),
        started_at=_required_datetime(props["started_at"]),
        last_activity=_required_datetime(props["last_activity"]),
        title=str(props["title"]),
        source_selection=str(props["source_selection"]),
    )


def _turn_from_props(props: Neo4jProperties) -> ConversationTurn:
    """Build the frozen ConversationTurn model from backend properties."""
    return ConversationTurn(
        turn_id=str(props["turn_id"]),
        session_id=str(props["session_id"]),
        role=str(props["role"]),
        content=str(props["content"]),
        timestamp=_required_datetime(props["timestamp"]),
        turn_number=int(props["turn_number"]),  # type: ignore[arg-type]
    )


class ConversationService:
    """Owner-private persistence for discussion sessions + turns (ADR-078)."""

    def __init__(self, backend: ConversationBackendOperations) -> None:
        if backend is None:
            raise ValueError("Conversation backend is required")
        self.backend = backend

    async def create_session(
        self, user_uid: UserUID, kind: str, title: str, source_selection: str
    ) -> Result[ConversationSession]:
        """Create a new owner-private session (started_at = last_activity = now)."""
        now_iso = datetime.now(UTC).isoformat()
        created = await self.backend.create_session(
            generate_session_id(), user_uid, kind, title, source_selection, now_iso
        )
        if created.is_error:
            return Result.fail(created)
        if created.value is None:
            return Result.fail(Errors.not_found("User", user_uid))
        session = _session_from_props(created.value)
        logger.info("Discussion session %s created for %s", session.session_id, user_uid)
        return Result.ok(session)

    async def append_turn(
        self, session_id: str, user_uid: UserUID, role: str, content: str
    ) -> Result[ConversationTurn]:
        """Append a turn to an owned session; touches ``last_activity``.

        A session the user does not own is indistinguishable from a missing one
        (not-found), never a 403.
        """
        now_iso = datetime.now(UTC).isoformat()
        appended = await self.backend.append_turn(
            generate_turn_id(), session_id, user_uid, role, content, now_iso
        )
        if appended.is_error:
            return Result.fail(appended)
        if appended.value is None:
            return Result.fail(Errors.not_found("ConversationSession", session_id))
        return Result.ok(_turn_from_props(appended.value))

    async def get_session(
        self, session_id: str, user_uid: UserUID
    ) -> Result[ConversationSession | None]:
        """Fetch one owned session (None when absent / not owned)."""
        fetched = await self.backend.get_session(session_id, user_uid)
        if fetched.is_error:
            return Result.fail(fetched)
        if fetched.value is None:
            return Result.ok(None)
        return Result.ok(_session_from_props(fetched.value))

    async def list_sessions(
        self, user_uid: UserUID, limit: int = _DEFAULT_SESSION_LIMIT
    ) -> Result[list[ConversationSession]]:
        """The user's revisit list, most-recent-activity first."""
        rows = await self.backend.list_sessions(user_uid, limit)
        if rows.is_error:
            return Result.fail(rows)
        return Result.ok([_session_from_props(row) for row in rows.value])

    async def get_turns(self, session_id: str, user_uid: UserUID) -> Result[list[ConversationTurn]]:
        """Ordered turns for continue-thread. Not-found on a non-owner."""
        rows = await self.backend.get_turns(session_id, user_uid)
        if rows.is_error:
            return Result.fail(rows)
        if rows.value is None:
            return Result.fail(Errors.not_found("ConversationSession", session_id))
        return Result.ok([_turn_from_props(row) for row in rows.value])

    async def delete_session(self, session_id: str, user_uid: UserUID) -> Result[bool]:
        """Delete an owned session + all its turns (False when absent / not owned)."""
        deleted = await self.backend.delete_session(session_id, user_uid)
        if deleted.is_error:
            return Result.fail(deleted)
        if deleted.value:
            logger.info("Discussion session %s deleted by %s", session_id, user_uid)
        return Result.ok(deleted.value)


__all__ = ["ConversationService"]

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
    ROLE_ASSISTANT,
    ROLE_USER,
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
        model=str(props["model"]),
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
        self, user_uid: UserUID, kind: str, title: str, source_selection: str, model: str
    ) -> Result[ConversationSession]:
        """Create a new owner-private session (started_at = last_activity = now)."""
        now_iso = datetime.now(UTC).isoformat()
        created = await self.backend.create_session(
            generate_session_id(), user_uid, kind, title, source_selection, model, now_iso
        )
        if created.is_error:
            return Result.fail(created)
        if created.value is None:
            return Result.fail(Errors.not_found("User", user_uid))
        session = _session_from_props(created.value)
        logger.info("Discussion session %s created for %s", session.session_id, user_uid)
        return Result.ok(session)

    async def append_exchange(
        self, session_id: str, user_uid: UserUID, user_content: str, assistant_content: str
    ) -> Result[tuple[ConversationTurn, ConversationTurn]]:
        """Append a user+assistant turn pair atomically; touches ``last_activity``.

        The pair is written in one backend transaction so overlapping exchanges
        cannot interleave (Codex #634 P2). A session the user does not own is
        indistinguishable from a missing one (not-found), never a 403.
        """
        now_iso = datetime.now(UTC).isoformat()
        appended = await self.backend.append_exchange(
            generate_turn_id(),
            generate_turn_id(),
            session_id,
            user_uid,
            user_content,
            assistant_content,
            now_iso,
        )
        if appended.is_error:
            return Result.fail(appended)
        if appended.value is None:
            return Result.fail(Errors.not_found("ConversationSession", session_id))
        user_turn, assistant_turn = appended.value
        return Result.ok((_turn_from_props(user_turn), _turn_from_props(assistant_turn)))

    async def save_transcript(
        self,
        user_uid: UserUID,
        kind: str,
        title: str,
        source_selection: str,
        model: str,
        pairs: list[tuple[str, str]],
    ) -> Result[ConversationSession]:
        """Promote an ephemeral transcript into a saved owner-private session (ADR-078 §5).

        The single explicit *Save this chat* path. The whole transcript is
        promoted **atomically**: the service mints the session id and every turn's
        id + ordinal, then the backend writes the session AND all turns in ONE
        transaction (``backend.save_transcript``). They become visible together,
        so a concurrent reader never observes an empty or truncated saved
        discussion (Codex #638 P2) — this is why Save does not create-then-append
        in separate transactions. Returns the created session so the caller can
        bind the composer to its ``session_id`` and add its revisit row.

        An empty transcript is a validation error — there is nothing to save, and
        (per ADR-078 §7 guard 7) an unsaved discussion must create zero nodes, so
        we never create a session with no turns.
        """
        if not pairs:
            return Result.fail(Errors.validation("Cannot save an empty discussion."))
        now_iso = datetime.now(UTC).isoformat()
        turns: list[Neo4jProperties] = []
        for user_content, assistant_content in pairs:
            turns.append(
                {
                    "turn_id": generate_turn_id(),
                    "role": ROLE_USER,
                    "content": user_content,
                    "turn_number": len(turns) + 1,
                }
            )
            turns.append(
                {
                    "turn_id": generate_turn_id(),
                    "role": ROLE_ASSISTANT,
                    "content": assistant_content,
                    "turn_number": len(turns) + 1,
                }
            )
        saved = await self.backend.save_transcript(
            generate_session_id(), user_uid, kind, title, source_selection, model, turns, now_iso
        )
        if saved.is_error:
            return Result.fail(saved)
        if saved.value is None:
            return Result.fail(Errors.not_found("User", user_uid))
        session = _session_from_props(saved.value)
        logger.info(
            "Saved discussion %s for %s (%d turns)", session.session_id, user_uid, len(turns)
        )
        return Result.ok(session)

    async def rename_session(self, session_id: str, user_uid: UserUID, title: str) -> Result[bool]:
        """Rename an owned session (False when absent / not owned).

        Leaves ``last_activity`` untouched — a rename must not reorder the
        revisit list.
        """
        return await self.backend.update_session_meta(session_id, user_uid, title, None)

    async def update_source_selection(
        self,
        session_id: str,
        user_uid: UserUID,
        source_selection: str,
        model: str | None = None,
    ) -> Result[bool]:
        """Persist the latest source selection (and model) on an owned session (last-write-wins).

        The per-turn state write for a session-backed follow-up: the grounding
        dials and the per-conversation model choice co-persist in one update so a
        *continued* session restores both. ``model=None`` leaves the stored model
        unchanged (coalesce).
        """
        return await self.backend.update_session_meta(
            session_id, user_uid, None, source_selection, model
        )

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

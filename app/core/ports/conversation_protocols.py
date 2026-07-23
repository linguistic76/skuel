"""
Conversation Protocols — Persisted Discussion Sessions (ADR-078)
================================================================

Protocol Responsibilities
--------------------------
    ConversationBackendOperations — persistence-layer operations consumed by
                                    ConversationService (typed against
                                    ``self.backend``). Speaks raw property dicts
                                    keyed on the owner-private graph shape.
    ConversationOperations        — the route-facing owner-private API the thin
                                    ``ConversationService`` exposes; every method
                                    is keyed on ``user_uid`` (404-not-403 on a
                                    non-owner, SKUEL ownership convention).

``:ConversationSession`` / ``:ConversationTurn`` are conversation-persistence
infrastructure (like sessions / devices), NOT an EntityType — the backend speaks
property dicts over the ``(User)-[:HAS_SESSION]->(ConversationSession)
-[:HAS_TURN]->(ConversationTurn)`` shape; the service converts to the frozen
``ConversationSession`` / ``ConversationTurn`` models.

Implementation: adapters/persistence/neo4j/backends/conversation_backend.py
Service:        core/services/conversation/conversation_service.py

See: /docs/decisions/ADR-078-discussion-sessions-stored-not-understood.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.conversation import ConversationSession, ConversationTurn
    from core.models.type_hints import Neo4jProperties, UserUID


@runtime_checkable
class ConversationBackendOperations(Protocol):
    """Backend operations consumed by ConversationService (owner-scoped Cypher)."""

    async def create_session(
        self,
        session_id: str,
        user_uid: UserUID,
        kind: str,
        title: str,
        source_selection: str,
        model: str,
        now_iso: str,
    ) -> Result[Neo4jProperties | None]:
        """Create the ConversationSession node + HAS_SESSION edge from its owner.

        ``started_at`` and ``last_activity`` both stamp ``now_iso``. ``model`` is
        the per-conversation LLM choice. None when the owner user does not exist.
        """
        ...

    async def append_exchange(
        self,
        user_turn_id: str,
        assistant_turn_id: str,
        session_id: str,
        user_uid: UserUID,
        user_content: str,
        assistant_content: str,
        now_iso: str,
    ) -> Result[list[Neo4jProperties] | None]:
        """Append a user+assistant turn PAIR to an OWNED session, atomically.

        Both turns are written in one transaction under the session write-lock,
        landing as consecutive ``n+1``/``n+2`` ordinals — concurrent exchanges
        cannot interleave. Returns the two turn property dicts ``[user,
        assistant]`` in order, or None when the session is absent / not owned.
        """
        ...

    async def save_transcript(
        self,
        session_id: str,
        user_uid: UserUID,
        kind: str,
        title: str,
        source_selection: str,
        model: str,
        turns: list[Neo4jProperties],
        now_iso: str,
    ) -> Result[Neo4jProperties | None]:
        """Create a session AND all its turns in ONE transaction (atomic Save).

        Whole-transcript promotion (ADR-078 §5): session + turns commit together
        so a concurrent read never sees a partial discussion. None when the owner
        user does not exist.
        """
        ...

    async def update_session_meta(
        self,
        session_id: str,
        user_uid: UserUID,
        title: str | None,
        source_selection: str | None,
        model: str | None = None,
    ) -> Result[bool]:
        """Update an OWNED session's title, source selection, and/or model (coalesce).

        Leaves ``last_activity`` untouched (a rename / source re-pick / model
        switch is not activity). True when an owned session was updated, False
        when absent / not owned.
        """
        ...

    async def get_session(
        self, session_id: str, user_uid: UserUID
    ) -> Result[Neo4jProperties | None]:
        """Fetch one OWNED session's properties. None when absent / not owned."""
        ...

    async def list_sessions(self, user_uid: UserUID, limit: int) -> Result[list[Neo4jProperties]]:
        """A user's sessions, ``last_activity`` desc — the revisit list."""
        ...

    async def get_turns(
        self, session_id: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties] | None]:
        """Ordered turns of an OWNED session (``turn_number`` asc).

        None when the session is absent / not owned (distinct from an owned
        session with zero turns, which is an empty list).
        """
        ...

    async def delete_session(self, session_id: str, user_uid: UserUID) -> Result[bool]:
        """DETACH DELETE an OWNED session and all its turns. True if deleted."""
        ...


@runtime_checkable
class ConversationOperations(Protocol):
    """Route-facing owner-private API exposed by ConversationService."""

    async def create_session(
        self, user_uid: UserUID, kind: str, title: str, source_selection: str, model: str
    ) -> Result[ConversationSession]:
        """Create a new owner-private session."""
        ...

    async def append_exchange(
        self, session_id: str, user_uid: UserUID, user_content: str, assistant_content: str
    ) -> Result[tuple[ConversationTurn, ConversationTurn]]:
        """Append a user+assistant turn pair atomically (not-found on a non-owner)."""
        ...

    async def save_transcript(
        self,
        user_uid: UserUID,
        kind: str,
        title: str,
        source_selection: str,
        model: str,
        pairs: list[tuple[str, str]],
    ) -> Result[ConversationSession]:
        """Promote an ephemeral transcript into a saved session (ADR-078 §5 opt-in Save)."""
        ...

    async def rename_session(self, session_id: str, user_uid: UserUID, title: str) -> Result[bool]:
        """Rename an owned session (False when absent / not owned)."""
        ...

    async def update_source_selection(
        self,
        session_id: str,
        user_uid: UserUID,
        source_selection: str,
        model: str | None = None,
    ) -> Result[bool]:
        """Persist the latest source selection (and model) on an owned session (last-write-wins)."""
        ...

    async def get_session(
        self, session_id: str, user_uid: UserUID
    ) -> Result[ConversationSession | None]:
        """Fetch one owned session (None when absent / not owned)."""
        ...

    async def list_sessions(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[ConversationSession]]:
        """The user's revisit list (most-recent-activity first)."""
        ...

    async def get_turns(self, session_id: str, user_uid: UserUID) -> Result[list[ConversationTurn]]:
        """Ordered turns for continue-thread (not-found on a non-owner)."""
        ...

    async def delete_session(self, session_id: str, user_uid: UserUID) -> Result[bool]:
        """Delete an owned session + its turns (False when absent / not owned)."""
        ...


__all__ = ["ConversationBackendOperations", "ConversationOperations"]

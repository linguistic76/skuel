"""
Conversation Backend — Persisted Discussion Sessions (ADR-078)
==============================================================

Neo4j persistence for owner-private discussion sessions and their turns. A thin
standalone backend mirroring ``SessionBackend`` / ``DeviceBackend`` — NOT a
``UniversalNeo4jBackend`` subclass. That is the load-bearing choice: routing
these nodes through the universal Entity path would auto-wire the search +
embedding machinery ADR-078 §2 forbids. ``:ConversationSession`` /
``:ConversationTurn`` are NeoLabels only (never EntityTypes), so the
understanding wall is *structural* — the nodes are never in the universal path
to begin with.

Graph shape (both edges owner-private):

    (User)-[:HAS_SESSION]->(ConversationSession {session_id, user_uid, kind,
                                                  started_at, last_activity,
                                                  title, source_selection})
    (ConversationSession)-[:HAS_TURN {turn_number}]->(ConversationTurn {turn_id,
                                                  session_id, role, content,
                                                  timestamp, turn_number})

Every read/write is scoped to the owner via the ``(User)-[:HAS_SESSION]->``
anchor; a non-owner sees an empty / None result (the service maps that to
404-not-403). ``turn_count`` is never stored — derived by ``COUNT``-ing
``HAS_TURN`` where needed (ADR-078 §3 self-consistency).

Protocol: core/ports/conversation_protocols.py (ConversationBackendOperations)
See Also: session_backend.py, device_backend.py — sibling thin backends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from adapters.persistence.neo4j._backend_helpers import to_native_datetime
from core.models.conversation import ROLE_ASSISTANT as _ROLE_ASSISTANT
from core.models.conversation import ROLE_USER as _ROLE_USER
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.type_hints import Neo4jProperties, UserUID

logger = get_logger(__name__)

_SESSION_LABEL = NeoLabel.CONVERSATION_SESSION.value
_TURN_LABEL = NeoLabel.CONVERSATION_TURN.value
_HAS_SESSION = RelationshipName.HAS_SESSION.value
_HAS_TURN = RelationshipName.HAS_TURN.value

# Shared RETURN shape for a session's properties (native datetimes downstream).
_SESSION_RETURN = """
        RETURN s.session_id AS session_id, s.user_uid AS user_uid, s.kind AS kind,
               s.started_at AS started_at, s.last_activity AS last_activity,
               s.title AS title, s.source_selection AS source_selection
"""

# The turn RETURN shape is a map projection inlined at each call site
# (append_exchange RETURNs two, get_turns collects a list), so no shared
# constant — the projected key list is identical in all three places.


def _session_record(data: dict[str, object]) -> Neo4jProperties:
    """Normalize a session row: Neo4j temporals → native datetimes."""
    return {
        "session_id": str(data["session_id"]),
        "user_uid": str(data["user_uid"]),
        "kind": str(data["kind"]),
        "started_at": to_native_datetime(data.get("started_at")),
        "last_activity": to_native_datetime(data.get("last_activity")),
        "title": str(data["title"]),
        "source_selection": str(data["source_selection"]),
    }


def _turn_record(data: dict[str, object]) -> Neo4jProperties:
    """Normalize a turn row: Neo4j temporals → native datetimes."""
    return {
        "turn_id": str(data["turn_id"]),
        "session_id": str(data["session_id"]),
        "role": str(data["role"]),
        "content": str(data["content"]),
        "timestamp": to_native_datetime(data.get("timestamp")),
        "turn_number": int(cast("int", data["turn_number"])),
    }


class ConversationBackend:
    """Neo4j persistence for owner-private discussion sessions (ADR-078)."""

    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver
        self.logger = logger

    async def create_session(
        self,
        session_id: str,
        user_uid: UserUID,
        kind: str,
        title: str,
        source_selection: str,
        now_iso: str,
    ) -> Result[Neo4jProperties | None]:
        """Create the ConversationSession node + HAS_SESSION edge from its owner."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        CREATE (u)-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL} {{
            session_id: $session_id,
            user_uid: $user_uid,
            kind: $kind,
            title: $title,
            source_selection: $source_selection,
            started_at: datetime($now),
            last_activity: datetime($now)
        }})
        {_SESSION_RETURN}
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "session_id": session_id,
                        "kind": kind,
                        "title": title,
                        "source_selection": source_selection,
                        "now": now_iso,
                    },
                )
                record = await result.single()
                return Result.ok(_session_record(dict(record)) if record else None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to create conversation session: {e}")
            return Result.fail(Errors.database("create_session", str(e)))

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

        Both turns are created in ONE write (a single implicit transaction) under
        the session write-lock: ``SET s.last_activity`` is placed BEFORE the turn
        count, so two concurrent exchanges (double-click, two tabs) serialize —
        the second blocks on the lock, then counts against the first's committed
        turns. The pair therefore always lands as consecutive ``n+1`` (user) and
        ``n+2`` (assistant) ordinals and never interleaves as
        ``user A, user B, assistant A, assistant B`` (Codex #634 P2).

        Returns the two turn property dicts ``[user, assistant]`` in order, or
        ``None`` when the session is absent / not owned.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL} {{session_id: $session_id}})
        SET s.last_activity = datetime($now)
        WITH s
        OPTIONAL MATCH (s)-[:{_HAS_TURN}]->(existing:{_TURN_LABEL})
        WITH s, count(existing) AS n
        CREATE (s)-[:{_HAS_TURN} {{turn_number: n + 1}}]->(ut:{_TURN_LABEL} {{
            turn_id: $user_turn_id,
            session_id: $session_id,
            role: $user_role,
            content: $user_content,
            timestamp: datetime($now),
            turn_number: n + 1
        }})
        CREATE (s)-[:{_HAS_TURN} {{turn_number: n + 2}}]->(at:{_TURN_LABEL} {{
            turn_id: $assistant_turn_id,
            session_id: $session_id,
            role: $assistant_role,
            content: $assistant_content,
            timestamp: datetime($now),
            turn_number: n + 2
        }})
        RETURN ut {{.turn_id, .session_id, .role, .content, .timestamp, .turn_number}} AS user_turn,
               at {{.turn_id, .session_id, .role, .content, .timestamp, .turn_number}} AS assistant_turn
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "session_id": session_id,
                        "user_turn_id": user_turn_id,
                        "assistant_turn_id": assistant_turn_id,
                        "user_role": _ROLE_USER,
                        "assistant_role": _ROLE_ASSISTANT,
                        "user_content": user_content,
                        "assistant_content": assistant_content,
                        "now": now_iso,
                    },
                )
                record = await result.single()
                if record is None:
                    return Result.ok(None)
                return Result.ok(
                    [
                        _turn_record(dict(record["user_turn"])),
                        _turn_record(dict(record["assistant_turn"])),
                    ]
                )
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to append conversation exchange: {e}")
            return Result.fail(Errors.database("append_exchange", str(e)))

    async def save_transcript(
        self,
        session_id: str,
        user_uid: UserUID,
        kind: str,
        title: str,
        source_selection: str,
        turns: list[Neo4jProperties],
        now_iso: str,
    ) -> Result[Neo4jProperties | None]:
        """Create the session AND all its turns in ONE transaction (ADR-078 §5).

        The *Save this chat* write. Because the session node and every turn are
        created in a single implicit transaction, they become visible together —
        a concurrent reader (a ``/journals`` reload in another tab) can never
        observe an empty or truncated saved discussion (Codex #638 P2). This is
        why Save does NOT reuse create_session + a loop of append_exchange (each a
        separate transaction, with a partial-visibility window between them).

        ``turns`` is the ordered, id-and-ordinal-stamped payload
        (``{turn_id, role, content, turn_number}`` per turn) the service builds;
        all turns share ``now_iso`` as their timestamp. The service guards against
        an empty transcript (guard 7), so ``turns`` is always non-empty here.
        Returns the session properties, or ``None`` when the owner does not exist.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        CREATE (u)-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL} {{
            session_id: $session_id,
            user_uid: $user_uid,
            kind: $kind,
            title: $title,
            source_selection: $source_selection,
            started_at: datetime($now),
            last_activity: datetime($now)
        }})
        WITH s
        UNWIND $turns AS turn
        CREATE (s)-[:{_HAS_TURN} {{turn_number: turn.turn_number}}]->(:{_TURN_LABEL} {{
            turn_id: turn.turn_id,
            session_id: $session_id,
            role: turn.role,
            content: turn.content,
            timestamp: datetime($now),
            turn_number: turn.turn_number
        }})
        WITH DISTINCT s
        {_SESSION_RETURN}
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "session_id": session_id,
                        "kind": kind,
                        "title": title,
                        "source_selection": source_selection,
                        "turns": turns,
                        "now": now_iso,
                    },
                )
                record = await result.single()
                return Result.ok(_session_record(dict(record)) if record else None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to save conversation transcript: {e}")
            return Result.fail(Errors.database("save_transcript", str(e)))

    async def update_session_meta(
        self,
        session_id: str,
        user_uid: UserUID,
        title: str | None,
        source_selection: str | None,
    ) -> Result[bool]:
        """Update an OWNED session's title and/or source selection (last-write-wins).

        A ``None`` argument leaves that field unchanged (``coalesce``). Returns
        True when an owned session was updated, False when absent / not owned.
        Does NOT touch ``last_activity`` — a rename or a source re-pick is not
        conversational activity and must not reorder the revisit list.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL} {{session_id: $session_id}})
        SET s.title = coalesce($title, s.title),
            s.source_selection = coalesce($source_selection, s.source_selection)
        RETURN s.session_id AS session_id
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "session_id": session_id,
                        "title": title,
                        "source_selection": source_selection,
                    },
                )
                record = await result.single()
                return Result.ok(record is not None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to update conversation session meta: {e}")
            return Result.fail(Errors.database("update_session_meta", str(e)))

    async def get_session(
        self, session_id: str, user_uid: UserUID
    ) -> Result[Neo4jProperties | None]:
        """Fetch one OWNED session's properties (None when absent / not owned)."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL} {{session_id: $session_id}})
        {_SESSION_RETURN}
        LIMIT 1
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "session_id": session_id})
                record = await result.single()
                return Result.ok(_session_record(dict(record)) if record else None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to get conversation session: {e}")
            return Result.fail(Errors.database("get_session", str(e)))

    async def list_sessions(self, user_uid: UserUID, limit: int) -> Result[list[Neo4jProperties]]:
        """A user's sessions, most-recent-activity first — the revisit list."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL})
        {_SESSION_RETURN}
        ORDER BY s.last_activity DESC
        LIMIT $limit
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "limit": limit})
                records = await result.data()
                return Result.ok([_session_record(row) for row in records])
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to list conversation sessions: {e}")
            return Result.fail(Errors.database("list_sessions", str(e)))

    async def get_turns(
        self, session_id: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties] | None]:
        """Ordered turns of an OWNED session (None when absent / not owned).

        Single query: anchor on the owned session, then collect its turns. Zero
        rows means the session is not owned/present → None; an owned session with
        no turns yet returns an empty list.
        """
        # ``s.session_id`` is a non-aggregate grouping key so the aggregation does
        # NOT collapse zero input rows into one empty row: a non-owned/absent
        # session yields ZERO groups (record None → 404), while an owned session
        # with no turns yet yields one group with an empty list. Dropping the
        # grouping key would make those two cases indistinguishable.
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL} {{session_id: $session_id}})
        OPTIONAL MATCH (s)-[:{_HAS_TURN}]->(t:{_TURN_LABEL})
        WITH s.session_id AS sid, t ORDER BY t.turn_number ASC, t.turn_id ASC
        RETURN sid, collect(t {{.turn_id, .session_id, .role, .content, .timestamp, .turn_number}}) AS turns
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "session_id": session_id})
                record = await result.single()
                if record is None:
                    return Result.ok(None)
                turns = record["turns"] or []
                return Result.ok([_turn_record(dict(row)) for row in turns])
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to get conversation turns: {e}")
            return Result.fail(Errors.database("get_turns", str(e)))

    async def delete_session(self, session_id: str, user_uid: UserUID) -> Result[bool]:
        """DETACH DELETE an OWNED session and all its turns (True if deleted)."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL} {{session_id: $session_id}})
        OPTIONAL MATCH (s)-[:{_HAS_TURN}]->(t:{_TURN_LABEL})
        WITH s, collect(t) AS turns
        DETACH DELETE s
        FOREACH (turn IN turns | DETACH DELETE turn)
        RETURN true AS deleted
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "session_id": session_id})
                record = await result.single()
                return Result.ok(record is not None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to delete conversation session: {e}")
            return Result.fail(Errors.database("delete_session", str(e)))


__all__ = ["ConversationBackend"]

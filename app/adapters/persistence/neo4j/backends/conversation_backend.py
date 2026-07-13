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

from datetime import datetime
from typing import TYPE_CHECKING, cast

from neo4j.time import DateTime as Neo4jDateTime

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

_TURN_RETURN = """
        RETURN t.turn_id AS turn_id, t.session_id AS session_id, t.role AS role,
               t.content AS content, t.timestamp AS timestamp,
               t.turn_number AS turn_number
"""


def _to_native_datetime(value: object) -> datetime | None:
    """Convert a Neo4j temporal to a native datetime (None passes through)."""
    if isinstance(value, Neo4jDateTime):
        return cast("datetime", value.to_native())
    if isinstance(value, datetime):
        return value
    return None


def _session_record(data: dict[str, object]) -> Neo4jProperties:
    """Normalize a session row: Neo4j temporals → native datetimes."""
    return {
        "session_id": str(data["session_id"]),
        "user_uid": str(data["user_uid"]),
        "kind": str(data["kind"]),
        "started_at": _to_native_datetime(data.get("started_at")),
        "last_activity": _to_native_datetime(data.get("last_activity")),
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
        "timestamp": _to_native_datetime(data.get("timestamp")),
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

    async def append_turn(
        self,
        turn_id: str,
        session_id: str,
        user_uid: UserUID,
        role: str,
        content: str,
        now_iso: str,
    ) -> Result[Neo4jProperties | None]:
        """Append a turn to an OWNED session; assign turn_number; touch activity.

        ``turn_number`` = existing turn count + 1, computed and persisted in the
        same write. The ``SET s.last_activity`` is deliberately placed BEFORE the
        turn count: it takes the write-lock on the session node, so two concurrent
        appends to the same session (double-submit, retry, two tabs) serialize —
        the second blocks on the lock, then re-counts against the first's
        committed turn and gets the next ordinal instead of a duplicate (Codex
        #633 P2). Ordering the SET after the count would leave that race open.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL} {{session_id: $session_id}})
        SET s.last_activity = datetime($now)
        WITH s
        OPTIONAL MATCH (s)-[:{_HAS_TURN}]->(existing:{_TURN_LABEL})
        WITH s, count(existing) + 1 AS next_number
        CREATE (s)-[:{_HAS_TURN} {{turn_number: next_number}}]->(t:{_TURN_LABEL} {{
            turn_id: $turn_id,
            session_id: $session_id,
            role: $role,
            content: $content,
            timestamp: datetime($now),
            turn_number: next_number
        }})
        {_TURN_RETURN}
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "role": role,
                        "content": content,
                        "now": now_iso,
                    },
                )
                record = await result.single()
                return Result.ok(_turn_record(dict(record)) if record else None)
        except NEO4J_EXCEPTIONS as e:
            logger.error(f"Failed to append conversation turn: {e}")
            return Result.fail(Errors.database("append_turn", str(e)))

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

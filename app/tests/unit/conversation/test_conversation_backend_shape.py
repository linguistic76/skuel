"""
ConversationBackend structural guards (ADR-078) — CI-runnable source checks.

The backend's behaviour (create/append/read-back/delete) is exercised by the
integration guards against a live Docker Neo4j. These source-inspection tests
lock the load-bearing SHAPE invariants that must survive any reshape and DO run
in CI:

- every read/write is owner-scoped through ``(User {uid: $user_uid})-[:HAS_SESSION]->``
- the backend is a standalone thin class (no UniversalNeo4jBackend superclass) —
  the structural understanding wall (ADR-078 §3)
- delete detaches the session AND its turns (guard 2 completeness at the Cypher)
- append touches ``last_activity`` (the revisit-list ordering key)
"""

from __future__ import annotations

import inspect

from adapters.persistence.neo4j.backends.conversation_backend import ConversationBackend
from adapters.persistence.neo4j.session_runner import Neo4jSessionRunner

# Cypher is built with f-strings, so source shows the templated forms: the User
# match doubles its braces and the edge type interpolates the _HAS_SESSION const.
_OWNER_MATCH = "u:User {{uid: $user_uid}}"
_OWNER_EDGE = "_HAS_SESSION"
# Every method that touches a specific session/turn set must be owner-scoped.
_OWNER_SCOPED_METHODS = [
    "create_session",
    "append_exchange",
    "save_transcript",
    "update_session_meta",
    "get_session",
    "list_sessions",
    "get_turns",
    "delete_session",
]


def test_backend_is_standalone_thin_class() -> None:
    # NOT a UniversalNeo4jBackend subclass — routing through the universal path
    # would auto-wire the search/embedding machinery ADR-078 §2 forbids.
    # Neo4jSessionRunner is allowed: it is the session-run chokepoint only
    # (open/run/drain a session), carrying none of the universal machinery.
    assert ConversationBackend.__mro__[1:] == (Neo4jSessionRunner, object)


def test_every_owner_scoped_method_anchors_on_the_owner() -> None:
    for name in _OWNER_SCOPED_METHODS:
        source = inspect.getsource(getattr(ConversationBackend, name))
        assert _OWNER_MATCH in source and _OWNER_EDGE in source, (
            f"{name} is not owner-scoped — every discussion read/write must match "
            f"the owner ({_OWNER_MATCH}) across HAS_SESSION so a non-owner sees "
            "nothing (404-not-403)."
        )


def test_delete_detaches_session_and_its_turns() -> None:
    source = inspect.getsource(ConversationBackend.delete_session)
    assert "DETACH DELETE s" in source
    # Turns are detach-deleted too (no orphaned :ConversationTurn nodes).
    assert "DETACH DELETE turn" in source


def test_append_touches_last_activity() -> None:
    source = inspect.getsource(ConversationBackend.append_exchange)
    assert "s.last_activity = datetime($now)" in source


def test_append_exchange_is_one_atomic_pair() -> None:
    # Both turns are created in ONE query (a single transaction) with consecutive
    # ordinals, under the SET-before-count session lock — concurrent exchanges
    # cannot interleave (Codex #634 P2).
    source = inspect.getsource(ConversationBackend.append_exchange)
    assert source.count("CREATE (s)-[:{_HAS_TURN}") == 2
    assert "n + 1" in source and "n + 2" in source


def test_save_transcript_is_one_transaction() -> None:
    # Save writes the session AND all turns in ONE query (a single implicit
    # transaction) via UNWIND, so a concurrent reader never observes a partial
    # session (Codex #638 P2). It must NOT be a create-then-loop shape.
    source = inspect.getsource(ConversationBackend.save_transcript)
    assert "CREATE (u)-[:{_HAS_SESSION}]->(s:{_SESSION_LABEL}" in source
    assert "UNWIND $turns AS turn" in source
    assert "CREATE (s)-[:{_HAS_TURN}" in source
    # Single statement via the session-run chokepoint → one implicit
    # transaction for the whole subtree (no create-then-append shape).
    assert source.count("self._run_single(") == 1
    assert "self.driver.session()" not in source

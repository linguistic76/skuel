"""A session is stored by its token's hash; the raw token is handed out beside it, once.

``create_session`` mints the token and the session together and returns both: the
session holds only the token's hash, which is all the graph stores, and the token goes
to the cookie. So a Session node, read exactly as ``SessionBackend.create_session``
stores it, reads as a ``Session`` with nothing supplied in its place.
"""

from __future__ import annotations

from typing import Any

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, unreadable_fields
from core.models.auth.session import Session, create_session, hash_session_token
from core.models.type_hints import UserUID


def _as_stored(session: Session) -> dict[str, Any]:  # boundary: node properties
    """The properties ``SessionBackend.create_session``'s CREATE writes, and no others."""
    return {
        "uid": session.uid,
        "token_hash": session.token_hash,
        "user_uid": session.user_uid,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "last_active_at": session.last_active_at,
        "ip_address": session.ip_address,
        "user_agent": session.user_agent,
        "is_valid": session.is_valid,
        "seen_day": session.created_at.date().isoformat(),
    }


def test_the_token_is_handed_out_beside_the_session_that_stores_its_hash() -> None:
    issued = create_session(UserUID("user_x"), ip_address="203.0.113.1", user_agent="pytest")

    assert issued.token
    assert hash_session_token(issued.token) == issued.session.token_hash
    assert create_session(UserUID("user_x"), "203.0.113.1", "pytest").token != issued.token


def test_a_stored_session_reads_as_it_is_stored() -> None:
    session = create_session(UserUID("user_x"), "203.0.113.1", "pytest").session
    stored = _as_stored(session)

    assert unreadable_fields(stored, Session) == []
    read = from_neo4j_node(stored, Session)
    assert (read.uid, read.token_hash, read.user_uid) == (
        session.uid,
        session.token_hash,
        session.user_uid,
    )

"""Minimal frozen models for persisted discussion sessions (ADR-078 §3).

Maps ONLY the identity + transcript subset the *revisit + continue* flow needs.
Everything the deferred Askesis schema modelled for understanding
(``guidance_mode``, ``anchor_ku_uid``, ``topic_summary``, ``MENTIONS`` …) is
deliberately absent — importing it would breach the understanding wall
(ADR-078 §2). Two derivations the ADR calls out are NOT stored:

- ``turn_count`` — derived by ``COUNT``-ing ``HAS_TURN`` at read time.
- ``state`` — no lifecycle writer exists, so it would be the exact vestigial
  trap ADR-078 criticises. Every session is simply the user's owned history,
  resumable until deleted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

# The ``kind`` discriminator value journals writes. It is the Askesis-adoption
# seam (ADR-078 §3) — nothing branches on it in this arc; journals writes only
# this one value.
CONVERSATION_KIND_DISCUSSION = "discussion"


def generate_session_id() -> str:
    """Mint a session id: ``cs_<uuid hex[:12]>`` (ADR-078 §3)."""
    return f"cs_{uuid.uuid4().hex[:12]}"


def generate_turn_id() -> str:
    """Mint a turn id: ``ct_<uuid hex[:12]>`` (ADR-078 §3)."""
    return f"ct_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True, kw_only=True, slots=True)
class ConversationSession:
    """An owner-private discussion session — the revisit-list unit.

    ``user_uid`` is the ONLY access key; every backend read/write is scoped to
    it (404-not-403 on a non-owner). ``kind`` is the companion discriminator
    (journals writes ``"discussion"``). ``source_selection`` is the JSON canon-
    shelf + vault selection so a *continued* session restores its own sources.
    """

    session_id: str
    user_uid: str
    kind: str
    started_at: datetime
    last_activity: datetime
    title: str
    source_selection: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ConversationTurn:
    """A single message within a session. ``content`` is plaintext at rest
    until the ADR-042 field-level-encryption phase lands (ADR-078 §6)."""

    turn_id: str
    session_id: str
    role: str
    content: str
    timestamp: datetime
    turn_number: int

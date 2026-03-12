"""
Askesis Conversation Entity — Persistent Socratic Session (Skeleton)
=====================================================================

Stores a Socratic tutoring conversation session as a graph node. This enables:
- Session resumption across page reloads
- Conversation analytics (topics explored, depth achieved)
- ZPD signal generation from conversation patterns

Skeleton: the model is defined, persistence is deferred until the Socratic
pipeline demonstrates value in the in-memory ConversationContext.

UID prefix: conv_
ContentOrigin: USER_CREATED
Ownership: requires_user_uid() = True

See: /docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True)
class AskesisConversation(UserOwnedEntity):
    """Persistent Socratic conversation session.

    Stores the metadata of a tutoring conversation. Turns are stored
    as JSON in turns_json for now — separate Turn nodes can be added
    later if conversation analytics require graph queries across turns.
    """

    session_id: str = ""
    learning_step_uid: str | None = None
    turn_count: int = 0
    topics_discussed: tuple[str, ...] = ()
    entities_mentioned: tuple[str, ...] = ()
    concepts_explored: tuple[str, ...] = ()
    # Turns stored as JSON property — separate nodes later if needed
    turns_json: str = "[]"

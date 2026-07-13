"""Persisted conversation models (ADR-078).

Companion-neutral store for discussion sessions and their turns. These are the
minimal frozen dataclasses that back the owner-private *revisit + continue*
capability — deliberately NOT the ~40-field in-memory
``core.models.user.conversation`` model (~35 of whose fields the Askesis study
proved vestigial; see ADR-078 *Learning from Askesis*).

Understanding-agnostic by construction: these carry identity + transcript only,
no pedagogical / search / analytics state. The understanding wall (ADR-078 §2)
holds because ``ConversationSession`` / ``ConversationTurn`` are NeoLabels only,
never ``EntityType`` members.
"""

from __future__ import annotations

from core.models.conversation.models import (
    CONVERSATION_KIND_DISCUSSION,
    ROLE_ASSISTANT,
    ROLE_USER,
    ConversationSession,
    ConversationTurn,
    generate_session_id,
    generate_turn_id,
)

__all__ = [
    "CONVERSATION_KIND_DISCUSSION",
    "ROLE_ASSISTANT",
    "ROLE_USER",
    "ConversationSession",
    "ConversationTurn",
    "generate_session_id",
    "generate_turn_id",
]

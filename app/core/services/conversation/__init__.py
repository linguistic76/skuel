"""Conversation persistence service (ADR-078).

The owner-private boundary + understanding-agnostic store for discussion
sessions. It persists sessions/turns and nothing else — all understanding
wiring (embeddings, MENTIONS, ZPD) lives *above* the store, opt-in per consumer.
Journals opts out entirely (the wall).
"""

from core.services.conversation.conversation_service import ConversationService

__all__ = ["ConversationService"]

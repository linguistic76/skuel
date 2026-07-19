"""Conversation persistence service (ADR-078).

The owner-private boundary + understanding-agnostic store for discussion
sessions. It persists sessions/turns and nothing else — all understanding
wiring (embeddings, MENTIONS, ZPD) lives *above* the store, opt-in per consumer.
Journals opts out entirely (the wall).
"""

from core.services.conversation.conversation_service import ConversationService
from core.services.conversation.transcript_codec import (
    build_source_selection,
    history_to_follow_up_context,
    parse_source_selection,
    parse_transcript,
    render_discussion_markdown,
    render_follow_up_context,
    safe_export_filename,
    serialize_transcript,
    transcript_to_pairs,
)

__all__ = [
    "ConversationService",
    "build_source_selection",
    "history_to_follow_up_context",
    "parse_source_selection",
    "parse_transcript",
    "render_discussion_markdown",
    "render_follow_up_context",
    "safe_export_filename",
    "serialize_transcript",
    "transcript_to_pairs",
]

"""
Text Truncation — Sentence-Boundary-Aware Truncation for LLM Context
=====================================================================

Truncates text to a character budget while preserving readability by
cutting at sentence or paragraph boundaries where possible.

Used by Askesis pipeline components (LSBundle, ResponseGenerator,
QueryProcessor) to prevent unbounded context growth.

March 2026: Created to fix unbounded LLM context in Askesis RAG pipeline.
"""

from typing import Final

# Minimum text length where truncation logic is worth running.
# Below this, the text is short enough to pass through unchanged.
_MIN_TRUNCATION_LENGTH: Final = 100


def truncate_to_budget(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, cutting at a sentence or paragraph boundary.

    Prefers cutting at (in order): paragraph break, sentence end, word boundary.
    Appends "..." when truncation occurs.

    Args:
        text: The text to truncate.
        max_chars: Maximum character count for the result (including "...").

    Returns:
        The original text if within budget, or a truncated version with "...".
    """
    if len(text) <= max_chars:
        return text

    # Reserve space for the ellipsis
    cutoff = max_chars - 3
    if cutoff < _MIN_TRUNCATION_LENGTH:
        return text[:max_chars - 3] + "..."

    # Try paragraph boundary first (\n\n), then sentence (. ), then newline
    for delimiter in ("\n\n", ". ", "\n"):
        boundary = text.rfind(delimiter, 0, cutoff)
        if boundary > cutoff // 2:  # Don't cut too early
            end = boundary + len(delimiter)
            return text[:end].rstrip() + "..."

    # Fall back to word boundary
    boundary = text.rfind(" ", 0, cutoff)
    if boundary > cutoff // 2:
        return text[:boundary] + "..."

    # Hard cut as last resort
    return text[:cutoff] + "..."

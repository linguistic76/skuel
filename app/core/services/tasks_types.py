"""
Tasks Analysis Types (Pattern 3C Migration)
============================================

Frozen dataclasses for tasks knowledge pattern analysis returns.
Replaces dict[str, Any] with strongly-typed, immutable structures.

Pattern 3C: Internal Analytics Types
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgePatternAnalysis:
    """Knowledge pattern analysis across tasks."""

    common_patterns: dict[str, int]
    frequent_knowledge_combinations: dict[tuple[str, ...], int]
    total_unique_patterns: int
    total_knowledge_combinations: int

"""
Adaptive Learning Path Service Types
======================================

Frozen dataclasses for adaptive learning path service results.
Follows Pattern 3C: dict[str, Any] → frozen dataclasses

Pattern:
- Frozen (immutable after construction)
- Type-safe field access
- Self-documenting structure
- Follows user_stats_types.py pattern
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnowledgeState:
    """
    User's current knowledge state analysis.

    Tracks what knowledge the user has mastered, applied, and is working on,
    along with strengths and learning velocity metrics.

    Attributes:
        mastered_knowledge: Set of mastered knowledge unit UIDs
        in_progress_knowledge: Set of knowledge units being learned
        applied_knowledge: Set of knowledge units applied in tasks
        knowledge_strengths: Usage frequency by knowledge unit UID
        knowledge_gaps: List of knowledge gap identifiers
        mastery_levels: Mastery level (0.0-1.0) by knowledge unit UID
        learning_velocity: Knowledge units learned per week
    """

    mastered_knowledge: set[str] = field(default_factory=set)
    in_progress_knowledge: set[str] = field(default_factory=set)
    applied_knowledge: set[str] = field(default_factory=set)
    knowledge_strengths: dict[str, int] = field(default_factory=dict)
    knowledge_gaps: list[str] = field(default_factory=list)
    mastery_levels: dict[str, float] = field(default_factory=dict)
    learning_velocity: float = 0.0

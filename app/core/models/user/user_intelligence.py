"""
User Learning Intelligence
==========================

``UserLearningIntelligence`` is the per-user learning profile the adaptive
PathStep service loads from the graph (``PsAdaptiveService._load_user_intelligence``):
current masteries, active and completed learning paths, and the intelligence
sources that fed them. Its one live reading is ``get_dominant_learning_velocity``.

A former ``EnhancedUserContext`` in this module grouped masteries "by domain" by
sniffing substrings out of Ku uids ("tech", "python", "finance") — a Domain no
entity carries (ADR-013: uids are opaque; never sniff type from a uid). Nothing
consumed it; it was deleted 2026-08-28 with the sniffer. A real per-domain
grouping, if one is ever wanted, keys on ``Mastery.sel_category`` — the field the
mastery record actually carries.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from core.models.pathways.learning_path import LearningPath
from core.models.pathways.mastery import (
    LearningPreference,
    LearningVelocity,
)
from core.models.pathways.mastery import LearningRecommendation as KnowledgeRecommendation
from core.models.pathways.mastery import Mastery as KnowledgeMastery
from core.models.type_hints import UserUID

# NOTE: SearchIntent and SearchQuery removed - deprecated search_archive dependency
# Search intelligence now uses simple dict structures for flexibility


class IntelligenceSource(StrEnum):
    """Sources of intelligence for UserContext enhancement."""

    KNOWLEDGE_MASTERY = "knowledge_mastery"
    LEARNING_PREFERENCE = "learning_preference"
    SEARCH_PATTERNS = "search_patterns"
    RELATIONSHIP_ANALYSIS = "relationship_analysis"
    CROSS_DOMAIN_TRANSFER = "cross_domain_transfer"


@dataclass
class UserLearningIntelligence:
    """
    Persistent Learning Intelligence for UserContext.

    Aggregates learning intelligence from Knowledge/Learning/Search domains
    to provide adaptive, context-aware user understanding.
    """

    user_uid: UserUID

    # Knowledge Intelligence
    current_masteries: dict[str, KnowledgeMastery] = field(default_factory=dict)
    learning_preferences: LearningPreference | None = None
    knowledge_recommendations: list[KnowledgeRecommendation] = field(default_factory=list)

    # Learning Path Intelligence
    active_learning_paths: list[LearningPath] = field(default_factory=list)
    completed_learning_paths: list[str] = field(default_factory=list)

    # Search Intelligence (simplified - no longer using deprecated SearchQuery/SearchIntent)
    recent_search_queries: list[dict[str, Any]] = field(
        default_factory=list
    )  # Simple search history,
    search_interests: dict[str, float] = field(default_factory=dict)  # topic -> interest_score,
    search_intent_patterns: dict[str, int] = field(default_factory=dict)  # intent_name -> count

    # Cross-Domain Intelligence
    knowledge_to_learning_transfers: list[tuple[str, str]] = field(
        default_factory=list
    )  # knowledge_uid -> path_uid,
    learning_to_search_patterns: list[tuple[str, str]] = field(
        default_factory=list
    )  # path_uid -> search_pattern,
    search_to_knowledge_discoveries: list[tuple[str, str]] = field(
        default_factory=list
    )  # search_uid -> knowledge_uid

    # Intelligence Evolution
    intelligence_sources: list[IntelligenceSource] = field(default_factory=list)
    last_intelligence_update: datetime = field(default_factory=datetime.now)
    intelligence_confidence: float = 0.5  # How confident are we in our intelligence

    def get_dominant_learning_velocity(self) -> LearningVelocity:
        """Most frequent learning velocity across the user's masteries.

        Computed directly from ``current_masteries`` — the former
        by-"domain" grouping parsed uid strings for a Domain that no
        entity actually carries (ADR-013: uids are opaque), so every
        mastery landed in one bucket and this was always the mode.
        """
        if not self.current_masteries:
            return LearningVelocity.MODERATE

        from core.utils.sort_functions import make_dict_value_getter

        # Count velocity occurrences
        velocity_counts: dict[LearningVelocity, int] = {}
        for mastery in self.current_masteries.values():
            velocity = mastery.learning_velocity
            velocity_counts[velocity] = velocity_counts.get(velocity, 0) + 1

        return max(velocity_counts.keys(), key=make_dict_value_getter(velocity_counts))

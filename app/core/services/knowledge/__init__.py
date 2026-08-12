"""
Knowledge Intelligence Services
================================

Shared intelligence services for knowledge-activity integration.

ActivityKnowledgeIntelligenceService provides knowledge intelligence
for ANY activity domain entity — not just Tasks.
"""

from core.services.knowledge.activity_knowledge_intelligence_service import (
    ActivityKnowledgeIntelligenceService,
)
from core.services.knowledge.knowledge_pattern_analyzer import (
    ActivityInsight,
    KnowledgePatternAnalyzer,
    LearningPattern,
    LearningPatternType,
    MasteryProgression,
)
from core.services.knowledge.user_substance import (
    USER_SUBSTANCE_CHANNELS,
    SubstanceChannel,
    SubstanceIndex,
    build_substance_index,
    channel_counts,
    empty_channel_prompts,
    substance_breakdown,
    substance_score,
    user_substance_score,
)

__all__ = [
    "USER_SUBSTANCE_CHANNELS",
    "ActivityKnowledgeIntelligenceService",
    "ActivityInsight",
    "KnowledgePatternAnalyzer",
    "LearningPattern",
    "LearningPatternType",
    "MasteryProgression",
    "SubstanceChannel",
    "SubstanceIndex",
    "build_substance_index",
    "channel_counts",
    "empty_channel_prompts",
    "substance_breakdown",
    "substance_score",
    "user_substance_score",
]

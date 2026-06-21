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

__all__ = [
    "ActivityKnowledgeIntelligenceService",
    "ActivityInsight",
    "KnowledgePatternAnalyzer",
    "LearningPattern",
    "LearningPatternType",
    "MasteryProgression",
]

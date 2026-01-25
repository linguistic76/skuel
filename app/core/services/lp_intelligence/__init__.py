"""
LP Intelligence Services Module
================================

Service-layer components for learning path intelligence and recommendations.

This module was created on 2025-11-05 by refactoring LpIntelligenceService
to follow Single Responsibility Principle.

Components (Refactored Architecture - November 5, 2025):
---------------------------------------------------------
Sub-Services (SRP Refactoring):
--------------------------------
- LearningStateAnalyzer: Learning state assessment
- LearningRecommendationEngine: Personalized recommendations
- ContentAnalyzer: Content analysis and metadata
- ContentQualityAssessor: Quality assessment and similarity

Architecture Philosophy:
-----------------------
"Specialized services coordinated by facade"

Each sub-service has a single, focused responsibility, making the system
more maintainable, testable, and comprehensible.
"""

from core.services.lp_intelligence.content_analyzer import ContentAnalyzer
from core.services.lp_intelligence.content_quality_assessor import ContentQualityAssessor
from core.services.lp_intelligence.learning_recommendation_engine import (
    LearningRecommendationEngine,
)
from core.services.lp_intelligence.learning_state_analyzer import LearningStateAnalyzer
from core.services.lp_intelligence.types import (
    ContentAnalysisResult,
    ContentMetadata,
    ContentRecommendation,
    LearningAnalysis,
    LearningIntervention,
    LearningReadiness,
    ProgressSummary,
)

__all__ = [
    "ContentAnalysisResult",
    "ContentAnalyzer",
    "ContentMetadata",
    "ContentQualityAssessor",
    "ContentRecommendation",
    "LearningAnalysis",
    "LearningIntervention",
    "LearningReadiness",
    "LearningRecommendationEngine",
    "LearningStateAnalyzer",
    "ProgressSummary",
]

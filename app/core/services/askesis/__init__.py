"""
Askesis Services Module
========================

Service-layer components for intelligent user assistance and recommendations.

This module was created on 2025-11-05 by refactoring EnhancedAskesisService
to follow Single Responsibility Principle.

Components (Refactored Architecture - November 5, 2025):
---------------------------------------------------------
Sub-Services (SRP Refactoring):
--------------------------------
- UserStateAnalyzer: Analyze current user state and patterns
- ActionRecommendationEngine: Generate personalized action recommendations
- QueryProcessor: Process and answer natural language queries
- EntityExtractor: Extract entities from natural language
- ContextRetriever: Retrieve domain-specific context

Architecture Philosophy:
-----------------------
"Specialized services coordinated by facade"

Each sub-service has a single, focused responsibility, making the system
more maintainable, testable, and comprehensible.
"""

__all__ = [
    "ActionRecommendationEngine",
    "AskesisAnalysis",
    "AskesisInsight",
    "AskesisRecommendation",
    "ContextRetriever",
    "EntityExtractionResult",
    "EntityExtractor",
    "InsightType",
    "LearningContext",
    "OptimizationOpportunity",
    "PatternDetection",
    "QueryProcessor",
    "QueryResult",
    "RecommendationCategory",
    "StateSnapshot",
    "UserStateAnalyzer",
]

from core.services.askesis.action_recommendation_engine import ActionRecommendationEngine
from core.services.askesis.context_retriever import ContextRetriever
from core.services.askesis.entity_extractor import EntityExtractor
from core.services.askesis.query_processor import QueryProcessor
from core.services.askesis.types import (
    AskesisAnalysis,
    AskesisInsight,
    AskesisRecommendation,
    EntityExtractionResult,
    InsightType,
    LearningContext,
    OptimizationOpportunity,
    PatternDetection,
    QueryResult,
    RecommendationCategory,
    StateSnapshot,
)
from core.services.askesis.user_state_analyzer import UserStateAnalyzer

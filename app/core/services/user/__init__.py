"""
User Services Module
====================

Service-layer components for user context management and intelligence.

**Decomposed Architecture (December 2025):**
--------------------------------------------
Context building decomposed from 1 file (2,100 lines) to 4 focused modules:

- user_context_builder.py - Orchestration only (~330 lines)
- user_context_queries.py - Cypher query definitions (~700 lines)
- user_context_extractor.py - Result parsing (~400 lines)
- user_context_populator.py - Context population (~300 lines)

Benefits: Better separation of concerns, easier testing, reduced cognitive load.

Core Components:
----------------
- UserContext: The master user state aggregate (~240 fields)
- UserContextBuilder: Orchestrates context building (composes query/extract/populate)
- UserContextQueryExecutor: Executes MEGA-QUERY and consolidated queries
- UserContextExtractor: Parses query results into typed structures
- UserContextPopulator: Populates UserContext fields from parsed data
- UserContextCache: Performance caching with TTL and invalidation
- UserContextIntelligence: Learning journey intelligence (9 methods)

Sub-Services:
-------------
- UserCoreService: CRUD + Authentication
- UserProgressRecorderService: Learning progress recording (writes)
- UserActivityService: Activity tracking
- UserStatsAggregator: Stats aggregation

Orchestration:
--------------
- UserContextService: API orchestration layer (coordinates builder + intelligence)

Architecture Philosophy:
-----------------------
"Context is a service-layer aggregate, not a model"

UserContext contains cross-domain business logic and intelligence
methods, making it a service-layer component rather than a simple data model.
"""

from core.models.context_types import DailyWorkPlan, LearningStep
from core.services.user.intelligence import UserContextIntelligence
from core.services.user.unified_user_context import UnifiedUserContext, UserContext
from core.services.user.user_activity_service import (
    ACTIVITY_FIELD_MAP,
    InvalidationReason,
    UserActivityService,
)
from core.services.user.user_context_builder import UserContextBuilder
from core.services.user.user_context_cache import UserContextCache
from core.services.user.user_context_extractor import (
    GoalRelationshipData,
    GraphSourcedData,
    HabitRelationshipData,
    KnowledgeRelationshipData,
    TaskRelationshipData,
    UserContextExtractor,
)
from core.services.user.user_context_populator import UserContextPopulator
from core.services.user.user_context_queries import (
    CONSOLIDATED_QUERY,
    MEGA_QUERY,
    UserContextQueryExecutor,
    empty_context_data,
)
from core.services.user.user_context_service import UserContextService
from core.services.user.user_core_service import UserCoreService
from core.services.user.user_progress_recorder_service import UserProgressRecorderService
from core.services.user.user_stats_aggregator import UserStatsAggregator

__all__ = [
    # Activity constants
    "ACTIVITY_FIELD_MAP",
    "CONSOLIDATED_QUERY",
    "InvalidationReason",
    "MEGA_QUERY",  # Query constants
    # Intelligence data classes
    "DailyWorkPlan",
    "GoalRelationshipData",
    # Extractor data classes
    "GraphSourcedData",
    "HabitRelationshipData",
    "KnowledgeRelationshipData",
    "LearningStep",
    "TaskRelationshipData",
    "UnifiedUserContext",  # Backward compatibility alias
    "UserActivityService",
    # Core context
    "UserContext",
    # Context Building (Decomposed December 2025)
    "UserContextBuilder",  # Orchestration
    # Infrastructure
    "UserContextCache",
    "UserContextExtractor",  # Result parsing
    # Intelligence
    "UserContextIntelligence",
    "UserContextPopulator",  # Context population
    "UserContextQueryExecutor",  # Query execution
    "UserContextService",  # API orchestration
    # Sub-Services
    "UserCoreService",
    "UserProgressRecorderService",
    "UserStatsAggregator",
    "empty_context_data",
]

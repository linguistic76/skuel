"""
Learning Domain Events
======================

Events published by learning services (KuService, LpService, LpIntelligenceService).

Event Catalog:
- knowledge.mastered - KU mastered by user
- learning_path.started - Learning path started
- learning_path.completed - Learning path completed
- prerequisites.analyzed - Prerequisites computed for KU

Subscribers:
- UserService (context invalidation)
- ProgressTrackingService (update learning progress)
- RecommendationEngine (suggest next learning)
- AnalyticsEngine (learning patterns)
"""

from dataclasses import dataclass
from datetime import datetime

from core.events.base import BaseEvent

# ============================================================================
# KNOWLEDGE UNIT EVENTS
# ============================================================================


@dataclass(frozen=True)
class KnowledgeMastered(BaseEvent):
    """
    Published when user masters a knowledge unit.

    Mastery criteria: Typically >80% score on assessments + consistent application.

    Subscribers:
    - UserService (invalidate context)
    - LearningPathService (unlock next KUs)
    - AchievementService (award mastery badges)
    - RecommendationEngine (suggest advanced topics)
    """

    ku_uid: str
    user_uid: str
    occurred_at: datetime

    # Mastery metrics
    mastery_score: float  # 0.0 to 1.0
    time_to_mastery_hours: int | None = None

    # Learning context
    learning_path_uid: str | None = None
    related_kus_mastered: int = 0

    @property
    def event_type(self) -> str:
        return "knowledge.mastered"


@dataclass(frozen=True)
class KnowledgeCreated(BaseEvent):
    """
    Published when a new knowledge unit is created.

    Subscribers:
    - LearningIntelligenceService (analyze prerequisites)
    - SearchService (index for discovery)
    - RecommendationEngine (suggest to relevant users)
    """

    ku_uid: str
    title: str
    domain: str | None
    occurred_at: datetime

    # Creation context
    created_by_user: str | None = (None,)
    created_from_template: bool = False

    @property
    def event_type(self) -> str:
        return "knowledge.created"


# ============================================================================
# LEARNING PATH EVENTS
# ============================================================================


@dataclass(frozen=True)
class LearningPathStarted(BaseEvent):
    """
    Published when user starts a learning path.

    Subscribers:
    - UserService (invalidate context)
    - ProgressTrackingService (initialize progress)
    - AnalyticsEngine (track path popularity)
    """

    path_uid: str
    user_uid: str
    occurred_at: datetime

    # Path details
    path_title: str
    estimated_duration_hours: int | None = None
    total_kus: int = 0

    @property
    def event_type(self) -> str:
        return "learning_path.started"


@dataclass(frozen=True)
class LearningPathCompleted(BaseEvent):
    """
    Published when user completes a learning path.

    Completion criteria: All required KUs mastered.

    Subscribers:
    - UserService (invalidate context)
    - AchievementService (award completion badge)
    - RecommendationEngine (suggest next paths)
    - AnalyticsEngine (completion patterns)
    """

    path_uid: str
    user_uid: str
    occurred_at: datetime

    # Completion metrics
    actual_duration_hours: int | None = (None,)
    estimated_duration_hours: int | None = None
    completed_ahead_of_schedule: bool = False

    # Achievement context
    kus_mastered: int = 0
    average_mastery_score: float = 0.0

    @property
    def event_type(self) -> str:
        return "learning_path.completed"


@dataclass(frozen=True)
class LearningPathProgressUpdated(BaseEvent):
    """
    Published when learning path progress changes.

    Subscribers:
    - DashboardService (update progress visualization)
    - NotificationService (milestone notifications)
    """

    path_uid: str
    user_uid: str
    occurred_at: datetime

    # Progress tracking
    old_progress: float  # 0.0 to 1.0
    new_progress: float  # 0.0 to 1.0
    kus_completed: int
    kus_total: int

    @property
    def event_type(self) -> str:
        return "learning_path.progress_updated"

    @property
    def progress_delta(self) -> float:
        """Calculate progress change."""
        return self.new_progress - self.old_progress


# ============================================================================
# LEARNING INTELLIGENCE EVENTS
# ============================================================================


@dataclass(frozen=True)
class PrerequisitesAnalyzed(BaseEvent):
    """
    Published when prerequisites are computed for a KU.

    This event enables decoupling LpIntelligenceService from KuService.

    Subscribers:
    - KuService (update KU prerequisite relationships)
    - SearchService (update dependency graph)
    """

    ku_uid: str
    occurred_at: datetime

    # Analysis results
    prerequisite_uids: list[str]
    confidence_scores: dict[str, float] | None = None

    # Analysis metadata
    analysis_method: str = "semantic"  # "semantic", "manual", "inferred"

    @property
    def event_type(self) -> str:
        return "prerequisites.analyzed"


@dataclass(frozen=True)
class LearningRecommendationGenerated(BaseEvent):
    """
    Published when personalized learning recommendations are generated.

    Subscribers:
    - DashboardService (display recommendations)
    - NotificationService (notify user of new recommendations)
    """

    user_uid: str
    occurred_at: datetime

    # Recommendations
    recommended_ku_uids: list[str]
    recommendation_reason: str  # "next_in_path", "related_to_interests", "skill_gap"

    @property
    def event_type(self) -> str:
        return "learning.recommendation_generated"


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Publishing Learning Events:
===========================

# In KuService.mark_mastered()
async def mark_mastered(self, ku_uid: str, user_uid: str, score: float) -> Result[None]:
    '''Mark a KU as mastered by user.'''

    # Update mastery record
    result = await self.progress_backend.create_mastery(ku_uid, user_uid, score)

    if result.is_ok and self.event_bus:
        event = KnowledgeMastered(
            ku_uid=ku_uid,
            user_uid=user_uid,
            occurred_at=datetime.now(),
            mastery_score=score
        )
        await self.event_bus.publish_async(event)

    return result


# In LpService.start_path()
async def start_path(self, path_uid: str, user_uid: str) -> Result[None]:
    '''Start a learning path.'''

    # Get path details
    path_result = await self.backend.get(path_uid)
    if path_result.is_error:
        return path_result

    path = path_result.value

    # Create progress record
    result = await self.progress_backend.create_path_progress(path_uid, user_uid)

    if result.is_ok and self.event_bus:
        event = LearningPathStarted(
            path_uid=path_uid,
            user_uid=user_uid,
            occurred_at=datetime.now(),
            path_title=path.title,
            estimated_duration_hours=path.estimated_hours,
            total_kus=len(path.ku_uids)
        )
        await self.event_bus.publish_async(event)

    return result


# In LpService.complete_path()
async def complete_path(self, path_uid: str, user_uid: str) -> Result[None]:
    '''Mark learning path as completed.'''

    # Get progress to calculate metrics
    progress_result = await self.progress_backend.get_progress(path_uid, user_uid)
    if progress_result.is_error:
        return progress_result

    progress = progress_result.value

    # Mark complete
    result = await self.progress_backend.mark_complete(path_uid, user_uid)

    if result.is_ok and self.event_bus:
        event = LearningPathCompleted(
            path_uid=path_uid,
            user_uid=user_uid,
            occurred_at=datetime.now(),
            actual_duration_hours=progress.total_hours,
            estimated_duration_hours=progress.estimated_hours,
            completed_ahead_of_schedule=progress.total_hours < progress.estimated_hours if progress.estimated_hours else False,
            kus_mastered=len(progress.completed_ku_uids),
            average_mastery_score=progress.average_score
        )
        await self.event_bus.publish_async(event)

    return result


# In LpIntelligenceService.analyze_prerequisites()
async def analyze_prerequisites(self, ku_uid: str) -> Result[list[str]]:
    '''Analyze and compute prerequisites for a KU.'''

    # Perform semantic analysis
    prerequisites = await self._semantic_prerequisite_analysis(ku_uid)

    # Publish event instead of directly updating KuService
    if self.event_bus:
        event = PrerequisitesAnalyzed(
            ku_uid=ku_uid,
            occurred_at=datetime.now(),
            prerequisite_uids=prerequisites,
            analysis_method="semantic"
        )
        await self.event_bus.publish_async(event)

    return Result.ok(prerequisites)


Event Handlers (Subscribers):
=============================

# In KuService - Handling prerequisite analysis
async def handle_prerequisites_analyzed(self, event: PrerequisitesAnalyzed) -> None:
    '''Update KU with computed prerequisites.'''
    try:
        # Create prerequisite relationships
        for prereq_uid in event.prerequisite_uids:
            await self.create_prerequisite_relationship(
                from_uid=event.ku_uid,
                to_uid=prereq_uid,
                confidence=event.confidence_scores.get(prereq_uid, 0.8) if event.confidence_scores else 0.8
            )

        self.logger.info(
            f"Updated prerequisites for KU {event.ku_uid}: "
            f"{len(event.prerequisite_uids)} prerequisites"
        )

    except Exception as e:
        self.logger.error(f"Error handling prerequisites.analyzed: {e}")


# In UserService - Handling learning events
async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> None:
    '''Invalidate context when KU mastered.'''
    await self.invalidate_context(
        user_uid=event.user_uid,
        reason="knowledge_mastered",
        affected_contexts=["askesis", "recommendations"]
    )


async def handle_learning_path_started(self, event: LearningPathStarted) -> None:
    '''Invalidate context when learning path started.'''
    await self.invalidate_context(
        user_uid=event.user_uid,
        reason="learning_path_started",
        affected_contexts=["askesis", "dashboard"]
    )


# In AchievementService - Handling learning milestones
async def handle_learning_path_completed(self, event: LearningPathCompleted) -> None:
    '''Award achievement when learning path completed.'''

    # Award completion badge
    await self.award_badge(event.user_uid, "path_completer")

    # Extra badges for fast completion
    if event.completed_ahead_of_schedule:
        await self.award_badge(event.user_uid, "speed_learner")

    # Badge for high mastery
    if event.average_mastery_score >= 0.9:
        await self.award_badge(event.user_uid, "master_student")

    self.logger.info(f"Awarded badges for learning path completion: {event.path_uid}")


async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> None:
    '''Award badges for knowledge mastery.'''

    # Check for mastery streak
    mastered_count = await self.count_user_masteries(event.user_uid)

    if mastered_count in [10, 50, 100]:
        milestone_badges = {10: "decade_scholar", 50: "fifty_master", 100: "centurion_scholar"}
        await self.award_badge(event.user_uid, milestone_badges[mastered_count])


# In RecommendationEngine - Generating next recommendations
async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> None:
    '''Generate new recommendations when KU mastered.'''

    # Find next recommended KUs based on mastered KU
    recommendations = await self._find_next_kus(event.ku_uid, event.user_uid)

    if recommendations and self.event_bus:
        rec_event = LearningRecommendationGenerated(
            user_uid=event.user_uid,
            occurred_at=datetime.now(),
            recommended_ku_uids=[ku.uid for ku in recommendations],
            recommendation_reason="next_in_sequence"
        )
        await self.event_bus.publish_async(rec_event)


Bootstrap Wiring:
================

# In services_bootstrap.py
def _wire_event_subscribers(event_bus: EventBusOperations, services: Services):
    '''Wire learning event subscribers.'''

    # Learning events → UserService
    event_bus.subscribe(KnowledgeMastered, services.user_service.handle_knowledge_mastered)
    event_bus.subscribe(LearningPathStarted, services.user_service.handle_learning_path_started)
    event_bus.subscribe(LearningPathCompleted, services.user_service.handle_learning_path_completed)

    # Prerequisites analysis → KuService
    event_bus.subscribe(PrerequisitesAnalyzed, services.ku.handle_prerequisites_analyzed)

    # Learning achievements
    event_bus.subscribe(LearningPathCompleted, services.achievements.handle_learning_path_completed)
    event_bus.subscribe(KnowledgeMastered, services.achievements.handle_knowledge_mastered)

    # Learning recommendations
    event_bus.subscribe(KnowledgeMastered, services.recommendations.handle_knowledge_mastered)

    logger.info("✅ Learning event subscribers wired")


Breaking Circular Dependency:
=============================

# Before (Circular):
learning_intelligence = LpIntelligenceService(ku_service=None)  # ← Needs KuService
ku_service = KuService(intelligence_service=learning_intelligence)  # ← Needs LpIntelligenceService
learning_intelligence.ku_service = ku_service  # ← Post-construction hack


# After (Event-driven):
learning_intelligence = LpIntelligenceService(event_bus=event_bus)  # ← Independent
ku_service = KuService(event_bus=event_bus)  # ← Independent

# Wire via events
event_bus.subscribe(PrerequisitesAnalyzed, ku_service.handle_prerequisites_analyzed)
event_bus.subscribe(KnowledgeCreated, learning_intelligence.handle_knowledge_created)

# No circular dependency - both services are independent!
"""

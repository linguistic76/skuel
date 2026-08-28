"""
Learning Domain Events
======================

Events published by learning services (PsService, LpService, LpIntelligenceService).

The mastery cascade
-------------------
``KnowledgeMastered`` is the entry point, published by ``PsMasteryService.mark_mastered``.
Three subscribers fan out from it, and one of them re-publishes — the chain crosses
services, so no single file shows it::

    KnowledgeMastered
      -> PsMasteryService.handle_knowledge_mastered    # detects PathStep completion
           -> PathStepCompleted
                -> LpProgressService.handle_step_completed
      -> PsProgressService.handle_knowledge_mastered   # PathStep progress
           -> PathStepProgressUpdated
      -> LpProgressService.handle_knowledge_mastered   # LearningPath progress
           -> LearningPathProgressUpdated

Wired in ``services_bootstrap/_event_wiring.py``; the classes this module defines are
the catalog.
"""

from dataclasses import dataclass
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID

# ============================================================================
# KNOWLEDGE UNIT EVENTS
# ============================================================================


@dataclass(frozen=True)
class KnowledgeMastered(BaseEvent):
    """
    Published when user masters a knowledge unit.

    Mastery criteria: Typically >80% score on assessments + consistent application.

    Subscribers:
    - PsMasteryService (detect PathStep completion)
    - PsProgressService (update PathStep progress)
    - LpProgressService (update LearningPath progress)
    - UserService (invalidate context)
    - RecommendationEngine (suggest advanced topics)
    """

    ku_uid: str
    user_uid: UserUID

    # Mastery metrics
    mastery_score: float  # 0.0 to 1.0
    time_to_mastery_hours: int | None = None

    # Learning context
    learning_path_uid: str | None = None
    related_kus_mastered: int = 0

    event_type: ClassVar[str] = "knowledge.mastered"


@dataclass(frozen=True)
class PathStepProgressUpdated(BaseEvent):
    """
    Published when path step progress changes.

    Progress is driven directly by KU mastery: kus_mastered / kus_total
    (via USES_KU and CONTAINS_KNOWLEDGE relationships).

    Subscribers:
    - DashboardService (update progress visualization)
    - NotificationService (milestone notifications)
    """

    ps_uid: str
    user_uid: UserUID
    old_progress: float  # 0.0 to 1.0
    new_progress: float  # 0.0 to 1.0
    kus_mastered: int
    kus_total: int

    event_type: ClassVar[str] = "path_step.progress_updated"

    @property
    def progress_delta(self) -> float:
        """Calculate progress change."""
        return self.new_progress - self.old_progress


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

    # Creation context
    created_by_user: str | None = None
    created_from_template: bool = False

    event_type: ClassVar[str] = "knowledge.created"


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
    user_uid: UserUID

    # Path details
    path_title: str
    estimated_duration_hours: int | None = None
    total_kus: int = 0

    event_type: ClassVar[str] = "learning_path.started"


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
    user_uid: UserUID

    # Completion metrics
    actual_duration_hours: int | None = None
    estimated_duration_hours: int | None = None
    completed_ahead_of_schedule: bool = False

    # Achievement context
    kus_mastered: int = 0
    average_mastery_score: float = 0.0

    event_type: ClassVar[str] = "learning_path.completed"


@dataclass(frozen=True)
class LearningPathProgressUpdated(BaseEvent):
    """
    Published when learning path progress changes.

    Subscribers:
    - DashboardService (update progress visualization)
    - NotificationService (milestone notifications)
    """

    path_uid: str
    user_uid: UserUID

    # Progress tracking
    old_progress: float  # 0.0 to 1.0
    new_progress: float  # 0.0 to 1.0
    kus_completed: int
    kus_total: int

    event_type: ClassVar[str] = "learning_path.progress_updated"

    @property
    def progress_delta(self) -> float:
        """Calculate progress change."""
        return self.new_progress - self.old_progress


@dataclass(frozen=True)
class LearningRecommendationGenerated(BaseEvent):
    """
    Published when personalized learning recommendations are generated.

    Subscribers:
    - DashboardService (display recommendations)
    - NotificationService (notify user of new recommendations)
    """

    user_uid: UserUID

    # Recommendations
    recommended_ku_uids: list[str]
    recommendation_reason: str  # "next_in_path", "related_to_interests", "skill_gap"

    event_type: ClassVar[str] = "learning.recommendation_generated"

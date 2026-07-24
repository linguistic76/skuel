"""
Knowledge Generation Service
==========================================

**UTILITY SERVICE** - Injected dependency, not a standalone service.
This service is used BY TasksService for task-to-knowledge conversion, not a duplicate.

AI-powered automatic knowledge extraction from completed tasks with:
- Pattern recognition for best practices and anti-patterns
- Insight generation from successful task completion patterns
- Knowledge quality scoring and curation
- Automatic knowledge unit creation from task insights

Integrates with existing knowledge infrastructure while adding
advanced generative capabilities for task-based learning.

Architecture:
- Lives in `core/services/insight/` alongside InsightStore (persistence side)
- Injected into TasksService for automatic knowledge creation
- Shell + three mixins (July 2026 decomposition): pattern analysis,
  insight synthesis, quality curation
- Models in `core/models/insight/generated_insight.py`
- See /docs/patterns/SERVICE_DECOMPOSITION_RULE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.services.insight._insight_synthesis_mixin import _InsightSynthesisMixin
from core.services.insight._pattern_analysis_mixin import _PatternAnalysisMixin
from core.services.insight._quality_curation_mixin import _QualityCurationMixin
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.curriculum_dto import CurriculumDTO
    from core.models.insight import TaskPattern
    from core.models.type_hints import UserUID


class InsightGenerationService(
    _PatternAnalysisMixin,  # pattern recognition over completed tasks
    _InsightSynthesisMixin,  # patterns → actionable insights
    _QualityCurationMixin,  # quality scoring, curation, insight → knowledge unit
):
    """
    Service for automatic knowledge generation from completed tasks.

    Core capabilities:
    1. Analyze completed task patterns to extract knowledge
    2. Recognize best practices and anti-patterns
    3. Generate actionable insights from successful completion patterns
    4. Score and curate generated knowledge for quality
    """

    def __init__(
        self,
        ku_service: Any = None,
        tasks_service: Any = None,
        analytics_engine: Any = None,
    ) -> None:
        """
        Initialize the knowledge generation service.

        All dependencies are optional at construction time because this service
        is created early in bootstrap before domain services exist. Dependencies
        are wired later via TasksService injection.

        Args:
            ku_service: For creating new knowledge units
            tasks_service: For accessing task completion data
            analytics_engine: For advanced pattern analysis
        """
        self.ku_service = ku_service
        self.tasks_service = tasks_service
        self.analytics_engine = analytics_engine
        self.logger = get_logger("skuel.knowledge.generation")

        # Pattern detection thresholds
        self.min_pattern_frequency = 3
        self.min_confidence_score = 0.7
        self.min_success_rate = 0.8

        # Knowledge quality thresholds
        self.min_quality_score = 0.6
        self.auto_publish_threshold = 0.8

        # Cache for pattern analysis
        self._pattern_cache: dict[str, list[TaskPattern]] = {}
        self._cache_ttl = 3600  # 1 hour
        self._cache_timestamps: dict[str, datetime] = {}

    # ========================================================================
    # AUTOMATIC KNOWLEDGE EXTRACTION FROM COMPLETED TASKS
    # ========================================================================

    @with_error_handling("extract_knowledge_from_completed_tasks", error_type="system")
    async def extract_knowledge_from_completed_tasks(
        self, user_uid: UserUID, days_back: int = 30, min_tasks: int = 5
    ) -> Result[list[CurriculumDTO]]:
        """
        Extract knowledge from user's completed tasks over a time period.

        Args:
            user_uid: User to analyze tasks for,
            days_back: How many days back to analyze,
            min_tasks: Minimum completed tasks needed for analysis

        Returns:
            Result containing list of generated CurriculumDTO objects
        """
        # Get completed tasks for analysis
        since_date = datetime.now() - timedelta(days=days_back)
        completed_tasks = await self._get_completed_tasks_since(user_uid, since_date)

        if len(completed_tasks) < min_tasks:
            return Result.ok([])  # Not enough data for meaningful analysis

        # Analyze patterns in completed tasks
        patterns_result = await self.analyze_task_completion_patterns(completed_tasks)
        if patterns_result.is_error:
            return Result.fail(patterns_result)

        patterns = patterns_result.value

        # Generate insights from patterns
        insights_result = self.generate_insights_from_patterns(patterns)
        if insights_result.is_error:
            return Result.fail(insights_result)

        insights = insights_result.value

        # Convert high-quality insights to knowledge units
        knowledge_units = []
        for insight in insights:
            if insight.confidence_score >= self.min_confidence_score:
                knowledge_dto = self._convert_insight_to_knowledge(insight, user_uid)
                if knowledge_dto:
                    knowledge_units.append(knowledge_dto)

        self.logger.info(
            f"Generated {len(knowledge_units)} knowledge units from {len(completed_tasks)} "
            f"completed tasks for user {user_uid}"
        )

        return Result.ok(knowledge_units)

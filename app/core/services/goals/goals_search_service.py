"""
Goal Search Service - Search and Discovery Operations
======================================================

Handles search and discovery operations for goals.
Implements DomainSearchOperations[Goal] protocol plus goal-specific methods.

**Responsibilities:**
- Text search on title/description
- Filter by status, domain/category, timeframe
- Time-based queries (due soon, overdue)
- Context-aware prioritization
- Graph-based relationship queries

**Pattern:**
This service follows the SearchService pattern documented in:
/docs/patterns/search_service_pattern.md
"""

from core.models.enums import EntityStatus
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.search.scoring import score_goal
from core.ports.domain_protocols import GoalsOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score


class GoalsSearchService(BaseService[GoalsOperations, Goal]):
    """
    Goal search and discovery operations.

    Implements DomainSearchOperations[Goal] protocol for consistent
    search interface across all activity domains.

    Universal Methods (DomainSearchOperations protocol):
    - search() - Text search on title/description (inherited from BaseService)
    - get_by_status() - Filter by EntityStatus
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_upcoming() - Goals upcoming within N days
    - get_overdue() - Past-due goals
    - get_active() - Non-terminal goals for a user

    Goal-Specific Methods:
    - get_by_category() - Filter by domain/category string
    - list_categories() - Get all unique goal categories

    Semantic Types Used:
    - FULFILLS_GOAL: Task contributes to goal completion
    - SUPPORTS_GOAL: Habit supports goal achievement
    - PARENT_GOAL: Goal is a sub-goal of another
    - REQUIRES_KNOWLEDGE: Goal requires knowledge prerequisites
    - SERVES_LIFE_PATH: Goal aligns with ultimate life path
    """

    # DomainConfig consolidation (January 2026)
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    _config = create_activity_domain_config(
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(EntityStatus.COMPLETED.value, EntityStatus.CANCELLED.value),
        category_field="domain",  # Goals use 'domain' field for categorization
        entity_label="Entity",
    )

    # Inherited from BaseService (December 2025):
    # - search() - Text search on title/description
    # - get_by_relationship() - Graph relationship queries
    # - get_by_status() - Filter by status field
    # - get_by_category() - Filter by domain field (via DomainConfig category_field)
    # - list_categories() - List unique domain values

    # ========================================================================
    # DOMAIN SEARCH OPERATIONS PROTOCOL IMPLEMENTATION
    # ========================================================================
    # Inherited from BaseService: search(), get_by_status(),
    # get_by_category(), list_categories(), get_by_relationship()

    @with_error_handling("get_prioritized", error_type="database")
    async def get_prioritized(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Goal]]:
        """
        Get goals prioritized for the user's current context.

        Delegates to the unified ``score_goal`` scorer so ranking is
        consistent with the other Activity Domains.

        Args:
            user_context: User's current context (~240 fields)
            limit: Maximum results to return

        Returns:
            Result containing goals sorted by priority/relevance
        """
        result = await self.backend.find_by(
            user_uid=user_context.user_uid, status=EntityStatus.ACTIVE.value
        )
        if result.is_error:
            return result

        goals = self._to_domain_models(result.value, GoalDTO, Goal)
        scored = [(goal, score_goal(goal, user_context).total) for goal in goals]
        scored.sort(key=get_result_score, reverse=True)
        prioritized = [goal for goal, _ in scored[:limit]]

        self.logger.info(f"Prioritized {len(prioritized)} goals for user {user_context.user_uid}")
        return Result.ok(prioritized)

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class
    # get_upcoming(), get_overdue(), get_active() - inherited from TimeQueryMixin via DomainConfig

    # get_by_category() - inherited from BaseService (uses category_field = "domain")
    # list_categories() - inherited from BaseService (uses category_field = "domain")

    # ========================================================================
    # GRAPH-AWARE FACETED SEARCH
    # ========================================================================
    # graph_aware_faceted_search() is inherited from BaseService (January 2026)
    # Configured via _graph_enrichment_patterns class attribute above
    # See: BaseService.graph_aware_faceted_search() for implementation

    # ========================================================================
    # INTELLIGENT SEARCH
    # ========================================================================

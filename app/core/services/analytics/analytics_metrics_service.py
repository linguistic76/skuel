"""
Analytics Metrics Service
==========================

Calculates statistical metrics for all domains AND layers.

This service extracts metrics from:

**Layer 1 Domains (7):**
- Tasks: completion rates, priority distribution, overdue counts
- Habits: streaks, consistency, completion by day
- Goals: progress percentages, on-track vs at-risk
- Events: scheduled hours, event types, attendance
- Finance: expense totals, category breakdowns, budget adherence
- Choices: decision counts, domain distribution
- Principles: alignment scores, strength changes, active principles

**Layer 0 Curriculum (NEW):**
- Knowledge Units: substance scores, decay warnings, domain distribution
- Learning Paths: completion rates, active paths, mastered knowledge

**Layer 2 Submissions (NEW):**
- Journals: entry counts, reflection frequency, themes, metacognition

Part of the 4-service Analytics architecture:
- AnalyticsMetricsService: Domain & layer statistics (this file)
- AnalyticsAggregationService: Cross-domain synthesis
- AnalyticsLifePathService: Life Path alignment tracking
- AnalyticsService: Facade orchestrating all
"""

import contextlib
from datetime import date
from typing import Any, Protocol, runtime_checkable

from core.constants import QueryLimit
from core.models.enums import EntityStatus
from core.models.entity import Entity
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_days_until_review, get_theme_count

logger = get_logger(__name__)


@runtime_checkable
class HasDateRangeBackend(Protocol):
    """Protocol for services with backend that supports date range queries."""

    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        date_field: str,
        additional_filters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> Any:
        """Find entities within a date range."""
        ...


class AnalyticsMetricsService:
    """
    Calculate statistical metrics for all domains and layers.

    This service provides metric calculations from:
    - Layer 1: 7 domain services (tasks, habits, goals, etc.)
    - Layer 0: Curriculum services (ku_service, lp_service)
    - Layer 2: Journal service

    Used by single-domain analytics, cross-domain Life Analytics, and
    cross-layer synthesis.


    Source Tag: "analytics_metrics_explicit"
    - Format: "analytics_metrics_explicit" for user-created relationships
    - Format: "analytics_metrics_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from reports metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self,
        tasks_service=None,
        habits_service=None,
        goals_service=None,
        events_service=None,
        finance_service=None,
        choices_service=None,
        principle_service=None,
        content_enrichment=None,
        ku_service=None,
        lp_service=None,
    ) -> None:
        """
        Initialize with domain and layer services.

        Args:
            tasks_service: TasksService facade (Layer 1)
            habits_service: HabitsService facade (Layer 1)
            goals_service: GoalsService facade (Layer 1)
            events_service: EventsService facade (Layer 1)
            finance_service: FinanceService facade (Layer 1)
            choices_service: ChoicesService facade (Layer 1)
            principle_service: PrinciplesService facade (Layer 1)
            content_enrichment: ContentEnrichmentService (Layer 2)
            ku_service: KuService for knowledge metrics (Layer 0)
            lp_service: LpService for curriculum metrics (Layer 0)
        """
        # Layer 1 domain services
        self.tasks = tasks_service
        self.habits = habits_service
        self.goals = goals_service
        self.events = events_service
        self.finance = finance_service
        self.choices = choices_service
        self.principles = principle_service

        # Layer 2 submission service
        self.content_enrichment = content_enrichment

        # Layer 0 curriculum services
        self.ku_service = ku_service
        self.lp_service = lp_service

        self.logger = logger
        logger.info("AnalyticsMetricsService initialized with 7 domain + 3 layer services")

    # ========================================================================
    # TASKS METRICS
    # ========================================================================

    async def calculate_task_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate statistical metrics for tasks.

        Phase 5 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level filtering.
        """
        if not self.tasks:
            return Result.fail(
                Errors.system(
                    message="Tasks service not available", operation="calculate_task_metrics"
                )
            )

        # Use unified API for Cypher-level filtering (Phase 5)
        tasks_result = await self.tasks.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=True,  # Include all statuses for reporting
        )

        if tasks_result.is_error or not tasks_result.value:
            return Result.ok(
                {
                    "total_count": 0,
                    "completed_count": 0,
                    "in_progress_count": 0,
                    "pending_count": 0,
                    "overdue_count": 0,
                    "completion_rate": 0.0,
                    "priority_distribution": {},
                }
            )

        tasks = tasks_result.value

        # Calculate metrics
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == EntityStatus.COMPLETED)
        in_progress = sum(1 for t in tasks if t.status == EntityStatus.ACTIVE)
        pending = sum(1 for t in tasks if t.status.value == "pending")
        overdue = sum(1 for t in tasks if self._is_overdue(t))

        completion_rate = (completed / total * 100) if total > 0 else 0.0

        # Priority distribution
        priority_dist: dict[str, int] = {}
        for task in tasks:
            priority = task.priority or "medium"
            priority_dist[priority] = priority_dist.get(priority, 0) + 1

        # Average completion time (for completed tasks with dates)
        completion_times = []
        for task in tasks:
            if task.status == EntityStatus.COMPLETED and task.created_at and task.completed_at:
                delta = (task.completed_at - task.created_at).days
                completion_times.append(delta)

        avg_completion_time = (
            sum(completion_times) / len(completion_times) if completion_times else 0
        )

        return Result.ok(
            {
                "total_count": total,
                "completed_count": completed,
                "in_progress_count": in_progress,
                "pending_count": pending,
                "overdue_count": overdue,
                "completion_rate": round(completion_rate, 1),
                "priority_distribution": priority_dist,
                "avg_completion_time_days": round(avg_completion_time, 1),
            }
        )

    # ========================================================================
    # HABITS METRICS
    # ========================================================================

    async def calculate_habit_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate statistical metrics for habits.

        Phase 5 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level filtering.
        Note: Habits don't use date filtering (ongoing practices).
        """
        if not self.habits:
            return Result.fail(
                Errors.system(
                    message="Habits service not available", operation="calculate_habit_metrics"
                )
            )

        # Use unified API (Phase 5) - dates ignored for habits
        habits_result = await self.habits.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=False,  # Exclude archived habits
        )

        if habits_result.is_error or not habits_result.value:
            return Result.ok(
                {
                    "total_active": 0,
                    "completion_rate": 0.0,
                    "current_streaks": {},
                    "best_streaks": {},
                    "consistency_rate": 0.0,
                }
            )

        habits = habits_result.value

        # Calculate metrics
        current_streaks = {}
        best_streaks = {}
        completion_rates = []

        for habit in habits:
            current_streaks[habit.title] = getattr(habit, "current_streak", 0)
            best_streaks[habit.title] = getattr(habit, "best_streak", 0)
            # completion_rate may not be present on all habit types
            with contextlib.suppress(AttributeError):
                completion_rates.append(habit.completion_rate)

        avg_completion = sum(completion_rates) / len(completion_rates) if completion_rates else 0.0

        return Result.ok(
            {
                "total_active": len(habits),
                "completion_rate": round(avg_completion * 100, 1),
                "current_streaks": current_streaks,
                "best_streaks": best_streaks,
                "consistency_rate": round(avg_completion * 100, 1),
            }
        )

    # ========================================================================
    # GOALS METRICS
    # ========================================================================

    async def calculate_goal_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate statistical metrics for goals.

        Phase 5 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level filtering.
        """
        if not self.goals:
            return Result.fail(
                Errors.system(
                    message="Goals service not available", operation="calculate_goal_metrics"
                )
            )

        # Use unified API (Phase 5) - gets active goals by target_date
        goals_result = await self.goals.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=False,  # Exclude completed/abandoned
        )

        if goals_result.is_error or not goals_result.value:
            return Result.ok(
                {
                    "total_active": 0,
                    "total_completed": 0,
                    "on_track_count": 0,
                    "at_risk_count": 0,
                    "avg_progress_percentage": 0.0,
                    "completion_rate": 0.0,
                }
            )

        goals = goals_result.value

        # Calculate metrics
        on_track = 0
        at_risk = 0
        progress_values = []

        for goal in goals:
            progress = getattr(goal, "progress", 0.0)
            progress_values.append(progress)

            # Simple heuristic: < 30% is at risk, >= 30% is on track
            if progress < 0.3:
                at_risk += 1
            else:
                on_track += 1

        avg_progress = sum(progress_values) / len(progress_values) if progress_values else 0.0

        # Get completed goals in same period (Phase 5 unified API)
        completed_goals_result = await self.goals.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=True,  # Include all statuses
        )

        # Count completed goals
        completed_count = 0
        if completed_goals_result.is_ok and completed_goals_result.value:
            from core.models.enums import EntityStatus

            completed_count = sum(
                1 for g in completed_goals_result.value if g.status == EntityStatus.COMPLETED
            )

        # Calculate completion rate
        total_goals = len(goals) + completed_count
        completion_rate = (completed_count / total_goals) if total_goals > 0 else 0.0

        return Result.ok(
            {
                "total_active": len(goals),
                "total_completed": completed_count,
                "on_track_count": on_track,
                "at_risk_count": at_risk,
                "avg_progress_percentage": round(avg_progress * 100, 1),
                "completion_rate": round(completion_rate * 100, 1),
            }
        )

    # ========================================================================
    # EVENTS METRICS
    # ========================================================================

    async def calculate_event_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate statistical metrics for events.

        Phase 5 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level filtering.
        """
        if not self.events:
            return Result.fail(
                Errors.system(
                    message="Events service not available", operation="calculate_event_metrics"
                )
            )

        # Use unified API for Cypher-level filtering (Phase 5)
        events_result = await self.events.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=True,  # Include all statuses for reporting
        )

        if events_result.is_error or not events_result.value:
            return Result.ok(
                {
                    "total_count": 0,
                    "upcoming_count": 0,
                    "completed_count": 0,
                    "cancelled_count": 0,
                    "total_hours_scheduled": 0.0,
                    "events_by_type": {},
                }
            )

        events = events_result.value

        # Calculate metrics
        from datetime import datetime

        total = len(events)
        upcoming = sum(1 for e in events if e.start_time > datetime.now())
        completed = sum(1 for e in events if e.status == EntityStatus.COMPLETED)
        cancelled = sum(1 for e in events if e.status == EntityStatus.CANCELLED)

        # Total scheduled hours
        total_hours = 0.0
        for event in events:
            total_hours += event.duration_minutes / 60.0

        # Events by type
        events_by_type: dict[str, int] = {}
        for event in events:
            event_type = event.event_type or "unknown"
            events_by_type[event_type] = events_by_type.get(event_type, 0) + 1

        return Result.ok(
            {
                "total_count": total,
                "upcoming_count": upcoming,
                "completed_count": completed,
                "cancelled_count": cancelled,
                "total_hours_scheduled": round(total_hours, 1),
                "events_by_type": events_by_type,
            }
        )

    # ========================================================================
    # FINANCE METRICS
    # ========================================================================

    async def calculate_finance_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate statistical metrics for finance.

        Phase 5 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level filtering.
        """
        if not self.finance:
            return Result.fail(
                Errors.system(
                    message="Finance service not available", operation="calculate_finance_metrics"
                )
            )

        # Use unified API for Cypher-level filtering (Phase 5)
        expenses_result = await self.finance.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=True,  # Include all statuses (no status filtering for expenses)
        )

        if expenses_result.is_error or not expenses_result.value:
            return Result.ok(
                {
                    "total_expenses": 0.0,
                    "total_income": 0.0,
                    "net_balance": 0.0,
                    "expenses_by_category": {},
                    "budget_adherence": 0.0,
                    "avg_daily_expense": 0.0,
                }
            )

        expenses = expenses_result.value  # Extract list from Result

        # Calculate metrics
        total_expenses = sum(e.amount for e in expenses if e.amount > 0)
        total_income = sum(abs(e.amount) for e in expenses if e.amount < 0)

        # Expenses by category
        expenses_by_category: dict[str, float] = {}
        for expense in expenses:
            if expense.amount > 0:
                category = getattr(expense, "category", "Uncategorized")
                expenses_by_category[category] = (
                    expenses_by_category.get(category, 0.0) + expense.amount
                )

        # Calculate average daily expense
        days_in_period = (end_date - start_date).days + 1
        avg_daily_expense = total_expenses / days_in_period if days_in_period > 0 else 0.0

        return Result.ok(
            {
                "total_expenses": round(total_expenses, 2),
                "total_income": round(total_income, 2),
                "net_balance": round(total_income - total_expenses, 2),
                "expenses_by_category": {k: round(v, 2) for k, v in expenses_by_category.items()},
                "budget_adherence": 0.0,  # Would need budget data to calculate
                "avg_daily_expense": round(avg_daily_expense, 2),
            }
        )

    # ========================================================================
    # CHOICES METRICS
    # ========================================================================

    async def calculate_choice_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate statistical metrics for choices.

        Phase 5 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level filtering.
        Note: Choices don't use date filtering (decision points in time).
        """
        if not self.choices:
            return Result.ok(
                {
                    "total_choices": 0,
                    "choices_by_domain": {},
                    "decision_quality_avg": 0.0,
                    "choices_reviewed_count": 0,
                }
            )

        # Use unified API (Phase 5) - dates ignored for choices
        choices_result = await self.choices.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=True,  # Include all statuses for reporting
        )

        if choices_result.is_error or not choices_result.value:
            return Result.ok(
                {
                    "total_choices": 0,
                    "choices_by_domain": {},
                    "decision_quality_avg": 0.0,
                    "choices_reviewed_count": 0,
                }
            )

        choices = choices_result.value  # Extract list from Result

        # Calculate metrics
        choices_by_domain: dict[str, int] = {}
        quality_scores: list[float] = []
        reviewed_count = 0

        for choice in choices:
            # Group by domain
            domain = getattr(choice, "domain", "Unknown")
            choices_by_domain[str(domain)] = choices_by_domain.get(str(domain), 0) + 1

            # Track quality if available
            quality = getattr(choice, "quality_score", None)
            if quality is not None:
                quality_scores.append(quality)

            # Count reviewed
            if getattr(choice, "reviewed", False):
                reviewed_count += 1

        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        return Result.ok(
            {
                "total_choices": len(choices),
                "choices_by_domain": choices_by_domain,
                "decision_quality_avg": round(avg_quality, 2),
                "choices_reviewed_count": reviewed_count,
            }
        )

    # ========================================================================
    # PRINCIPLES METRICS (NEW!)
    # ========================================================================

    async def calculate_principle_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate statistical metrics for principles.

        Phase 5 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level filtering.
        Note: Principles are timeless values (no date filtering).
        """
        if not self.principles:
            return Result.ok(
                {
                    "total_principles": 0,
                    "active_principles": 0,
                    "avg_strength": 0.0,
                    "principles_by_category": {},
                    "alignment_score": 0.0,
                }
            )

        # Use unified API (Phase 5) - dates ignored for principles
        principles_result = await self.principles.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=True,  # No status filtering for principles
        )

        if principles_result.is_error or not principles_result.value:
            return Result.ok(
                {
                    "total_principles": 0,
                    "active_principles": 0,
                    "avg_strength": 0.0,
                    "principles_by_category": {},
                    "alignment_score": 0.0,
                }
            )

        principles = principles_result.value

        # Calculate metrics
        total = len(principles)
        active = sum(1 for p in principles if getattr(p, "is_active", True))

        # Strength analysis
        strengths = [getattr(p, "strength", 0.5) for p in principles]
        avg_strength = sum(strengths) / len(strengths) if strengths else 0.0

        # Category distribution
        by_category: dict[str, int] = {}
        for principle in principles:
            category = str(getattr(principle, "category", "Unknown"))
            by_category[category] = by_category.get(category, 0) + 1

        # Overall alignment (would need goals/habits to calculate properly)
        # For now, use average strength as proxy
        alignment_score = avg_strength

        return Result.ok(
            {
                "total_principles": total,
                "active_principles": active,
                "avg_strength": round(avg_strength, 2),
                "principles_by_category": by_category,
                "alignment_score": round(alignment_score * 100, 1),
            }
        )

    # ========================================================================
    # LAYER 0: KNOWLEDGE & CURRICULUM METRICS (NEW)
    # ========================================================================

    async def calculate_knowledge_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate knowledge substance metrics (Layer 0).

        This provides insights into how well knowledge is being APPLIED
        in real life, not just learned theoretically.

        Args:
            user_uid: User identifier
            start_date: Start of reporting period
            end_date: End of reporting period

        Returns:
            Result[dict] with knowledge substance analysis:
            {
                "total_knowledge_units": 50,
                "avg_substance_score": 0.62,
                "theoretical_knowledge": 15,  # < 0.3 substance
                "applied_knowledge": 20,      # 0.3-0.6
                "practiced_knowledge": 10,     # 0.6-0.8
                "embodied_knowledge": 5,       # 0.8+
                "knowledge_by_domain": {
                    "TECH": {"count": 20, "avg_substance": 0.75},
                    "BUSINESS": {"count": 15, "avg_substance": 0.52}
                },
                "decay_warnings": [
                    {"ku_uid": "ku:python", "title": "...", "days_until_review": 5}
                ]
            }
        """
        if not self.ku_service:
            return Result.fail(
                Errors.system(
                    message="KuService not available", operation="calculate_knowledge_metrics"
                )
            )

        try:
            # Get knowledge units for user filtered by date range
            # Use backend's find_by_date_range for efficient date filtering
            backend = getattr(self.ku_service, "backend", None)
            if backend is not None and isinstance(backend, HasDateRangeBackend):
                kus_result = await backend.find_by_date_range(
                    start_date=start_date,
                    end_date=end_date,
                    date_field="updated_at",  # Filter by last update date
                    additional_filters={"user_uid": user_uid},
                    limit=QueryLimit.COMPREHENSIVE,
                )
            else:
                # Fallback: get all and filter in memory (less efficient)
                all_kus_result = await self.ku_service.list_by_user(
                    user_uid, QueryLimit.COMPREHENSIVE
                )
                if all_kus_result.is_error:
                    return Result.fail(
                        Errors.system(
                            message="Could not retrieve knowledge units",
                            operation="calculate_knowledge_metrics",
                        )
                    )

                # Filter by date range in memory
                all_kus = all_kus_result.value
                knowledge_units = [
                    ku
                    for ku in all_kus
                    if isinstance(ku, Entity)
                    and ku.updated_at
                    and start_date <= ku.updated_at.date() <= end_date
                ]
                kus_result = Result.ok(knowledge_units)

            if kus_result.is_error or not kus_result.value:
                return Result.ok(
                    {
                        "total_knowledge_units": 0,
                        "avg_substance_score": 0.0,
                        "theoretical_knowledge": 0,
                        "applied_knowledge": 0,
                        "practiced_knowledge": 0,
                        "embodied_knowledge": 0,
                        "knowledge_by_domain": {},
                        "decay_warnings": [],
                        "date_range": f"{start_date} to {end_date}",
                    }
                )

            knowledge_units = kus_result.value

            # Analyze substance scores
            total_substance = 0.0
            theoretical = 0  # < 0.3
            applied = 0  # 0.3-0.6
            practiced = 0  # 0.6-0.8
            embodied = 0  # 0.8+

            by_domain: dict[str, dict[str, Any]] = {}
            decay_warnings = []

            for ku_dto in knowledge_units:
                # Backend returns Entity instances (entity_class=Ku), not DTOs
                ku = ku_dto
                substance = ku.substance_score()

                total_substance += substance

                # Categorize by substance level
                if substance >= 0.8:
                    embodied += 1
                elif substance >= 0.6:
                    practiced += 1
                elif substance >= 0.3:
                    applied += 1
                else:
                    theoretical += 1

                # Group by domain
                domain = str(getattr(ku, "domain", "UNKNOWN"))
                if domain not in by_domain:
                    by_domain[domain] = {"count": 0, "total_substance": 0.0}
                by_domain[domain]["count"] += 1
                by_domain[domain]["total_substance"] += substance

                # Check for decay warnings (substance review needed)
                days_until_review = getattr(ku, "days_until_review", None)
                if callable(days_until_review):
                    days_left = days_until_review()
                    if days_left is not None and days_left <= 7:
                        decay_warnings.append(
                            {
                                "ku_uid": ku.uid,
                                "title": ku.title,
                                "days_until_review": days_left,
                                "current_substance": round(substance, 2),
                            }
                        )

            count = len(knowledge_units)
            avg_substance = total_substance / count if count > 0 else 0.0

            # Calculate average substance by domain
            knowledge_by_domain = {}
            for domain, data in by_domain.items():
                knowledge_by_domain[domain] = {
                    "count": data["count"],
                    "avg_substance": round(data["total_substance"] / data["count"], 2),
                }

            return Result.ok(
                {
                    "total_knowledge_units": count,
                    "avg_substance_score": round(avg_substance, 2),
                    "theoretical_knowledge": theoretical,
                    "applied_knowledge": applied,
                    "practiced_knowledge": practiced,
                    "embodied_knowledge": embodied,
                    "knowledge_by_domain": knowledge_by_domain,
                    "decay_warnings": sorted(decay_warnings, key=get_days_until_review)[:10],
                    "date_range": f"{start_date} to {end_date}",  # Show filtered date range
                    "user_uid": user_uid,
                }
            )

        except Exception as e:
            self.logger.error(f"Failed to calculate knowledge metrics: {e}")
            return Result.fail(
                Errors.system(
                    message="Knowledge metrics calculation failed",
                    exception=e,
                    operation="calculate_knowledge_metrics",
                )
            )

    async def calculate_curriculum_metrics(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Calculate progress through curriculum layer (Layer 0).

        Shows user's learning path progress, completion rates, and
        current focus areas.

        Args:
            user_uid: User identifier

        Returns:
            Result[dict] with curriculum progress:
            {
                "active_learning_paths": 3,
                "completed_learning_paths": 7,
                "in_progress_learning_steps": 12,
                "completed_learning_steps": 85,
                "total_knowledge_units": 50,
                "mastered_knowledge_units": 23,
                "current_focus": {
                    "lp_uid": "lp:python-mastery",
                    "lp_title": "Python Mastery",
                    "progress": 0.65
                }
            }
        """
        if not self.lp_service:
            return Result.fail(Errors.system(message="LpService not available"))

        try:
            # Get all learning paths for user
            lps_result = await self.lp_service.list_by_user(user_uid, QueryLimit.COMPREHENSIVE)

            if lps_result.is_error or not lps_result.value:
                return Result.ok(
                    {
                        "active_learning_paths": 0,
                        "completed_learning_paths": 0,
                        "in_progress_learning_steps": 0,
                        "completed_learning_steps": 0,
                        "total_knowledge_units": 0,
                        "mastered_knowledge_units": 0,
                        "current_focus": None,
                    }
                )

            learning_paths = lps_result.value

            active_lps = 0
            completed_lps = 0
            total_steps = 0
            completed_steps = 0
            current_focus = None

            for lp_dto in learning_paths:
                # Use DTO directly (Lp doesn't have from_dto method yet)
                lp = lp_dto

                # Check completion status
                is_completed = getattr(lp, "is_completed", False)
                if is_completed:
                    completed_lps += 1
                else:
                    active_lps += 1

                # Get learning steps
                steps = getattr(lp, "learning_steps", [])
                if steps:
                    total_steps += len(steps)
                    completed_steps += sum(1 for s in steps if getattr(s, "is_completed", False))

                # Track most recently active path as current focus
                if not is_completed and not current_focus:
                    progress = 0.0
                    if steps:
                        progress = completed_steps / len(steps)

                    current_focus = {
                        "lp_uid": lp.uid,
                        "lp_title": lp.title,
                        "progress": round(progress, 2),
                    }

            # Get knowledge unit metrics
            ku_metrics = {"total": 0, "mastered": 0}
            if self.ku_service:
                kus_result = await self.ku_service.list_by_user(user_uid, QueryLimit.COMPREHENSIVE)
                if kus_result.is_ok and kus_result.value:
                    ku_metrics["total"] = len(kus_result.value)
                    ku_metrics["mastered"] = sum(
                        1 for ku in kus_result.value if getattr(ku, "is_mastered", False)
                    )

            return Result.ok(
                {
                    "active_learning_paths": active_lps,
                    "completed_learning_paths": completed_lps,
                    "in_progress_learning_steps": total_steps - completed_steps,
                    "completed_learning_steps": completed_steps,
                    "total_knowledge_units": ku_metrics["total"],
                    "mastered_knowledge_units": ku_metrics["mastered"],
                    "current_focus": current_focus,
                }
            )

        except Exception as e:
            self.logger.error(f"Failed to calculate curriculum metrics: {e}")
            return Result.fail(
                Errors.system(message="Curriculum metrics calculation failed", exception=e)
            )

    # ========================================================================
    # LAYER 2: JOURNAL METRICS (NEW)
    # ========================================================================

    async def calculate_journal_metrics(
        self, user_uid: str, start_date: date, end_date: date
    ) -> Result[dict[str, Any]]:
        """
        Calculate journal reflection metrics (Layer 2).

        UPDATED (January 2026): Queries Report nodes instead of Journal nodes.
        This ensures new content created via the Report path is included in analytics.

        Analyzes journal entries for reflection patterns, themes,
        and metacognition quality.

        Args:
            user_uid: User identifier
            start_date: Start of reporting period
            end_date: End of reporting period

        Returns:
            Result[dict] with journal analysis:
            {
                "total_entries": 15,
                "avg_entry_length": 1250,  # characters
                "reflection_frequency": 0.5,  # entries per day
                "top_themes": ["learning", "meditation", "productivity"],
                "action_items_identified": 23,
                "metacognition_score": 0.72  # journal substance contribution
            }
        """
        if not self.content_enrichment:
            return Result.fail(
                Errors.system(
                    message="ContentEnrichmentService not available",
                    operation="calculate_journal_metrics",
                )
            )

        try:
            # Query Report nodes directly instead of calling list_journals()
            # This ensures we capture journals created via the Report path
            journals = await self._get_journal_reports(user_uid, start_date, end_date)

            if not journals:
                return Result.ok(
                    {
                        "total_entries": 0,
                        "avg_entry_length": 0,
                        "reflection_frequency": 0.0,
                        "top_themes": [],
                        "action_items_identified": 0,
                        "metacognition_score": 0.0,
                    }
                )

            # Calculate metrics
            total_entries = len(journals)
            total_length = 0
            all_themes: list[str] = []
            action_items_count = 0

            for journal in journals:
                # Entry length - use processed_content from Report
                content = journal.get("processed_content", "")
                if content:
                    total_length += len(content)

                # Themes and action items from metadata
                metadata = journal.get("metadata") or {}
                if isinstance(metadata, dict):
                    themes = metadata.get("themes", [])
                    if isinstance(themes, list):
                        all_themes.extend(themes)
                    action_items = metadata.get("action_items", [])
                    if isinstance(action_items, list):
                        action_items_count += len(action_items)

            avg_length = total_length / total_entries if total_entries > 0 else 0

            # Calculate reflection frequency (entries per day)
            days_in_period = (end_date - start_date).days + 1
            frequency = total_entries / days_in_period if days_in_period > 0 else 0

            # Top themes (count frequency)
            theme_counts: dict[str, int] = {}
            for theme in all_themes:
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
            top_themes = sorted(theme_counts.items(), key=get_theme_count, reverse=True)[:5]
            top_themes_list = [theme for theme, _ in top_themes]

            # Metacognition score (placeholder - would need deeper analysis)
            # For now, use frequency + length as proxy
            metacognition_score = min(1.0, (frequency * 0.5) + (min(avg_length, 2000) / 2000 * 0.5))

            return Result.ok(
                {
                    "total_entries": total_entries,
                    "avg_entry_length": int(avg_length),
                    "reflection_frequency": round(frequency, 2),
                    "top_themes": top_themes_list,
                    "action_items_identified": action_items_count,
                    "metacognition_score": round(metacognition_score, 2),
                }
            )

        except Exception as e:
            self.logger.error(f"Failed to calculate journal metrics: {e}")
            return Result.fail(
                Errors.system(
                    message="Journal metrics calculation failed",
                    exception=e,
                    operation="calculate_journal_metrics",
                )
            )

    async def _get_journal_reports(
        self, user_uid: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """
        Get journal Report nodes for a user within a date range.

        ADDED (January 2026): Direct query to Report nodes for journal metrics.

        Args:
            user_uid: User identifier
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of journal report dictionaries
        """
        from datetime import datetime

        # Access the driver through content_enrichment's backend
        if not self.content_enrichment or not self.content_enrichment.backend:
            return []

        # Convert dates to datetime for Neo4j comparison
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        # Updated January 2026: Query :Journal nodes directly (domain separation)
        cypher = """
        MATCH (j:Journal {user_uid: $user_uid})
        WHERE j.created_at >= datetime($start_datetime)
          AND j.created_at <= datetime($end_datetime)
        RETURN j.uid as uid,
               j.content as processed_content,
               {title: j.title, summary: j.summary, themes: j.key_topics} as metadata,
               j.created_at as created_at
        ORDER BY j.created_at DESC
        """

        try:
            result = await self.content_enrichment.backend.execute_query(
                cypher,
                {
                    "user_uid": user_uid,
                    "start_datetime": start_datetime.isoformat(),
                    "end_datetime": end_datetime.isoformat(),
                },
            )
            if result.is_error:
                self.logger.warning(f"Failed to query journal assignments: {result.error}")
                return []

            import json

            journals = []
            for record in result.value:
                metadata = record["metadata"]
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {}

                journals.append(
                    {
                        "uid": record["uid"],
                        "processed_content": record["processed_content"] or "",
                        "metadata": metadata or {},
                        "created_at": record["created_at"],
                    }
                )

            return journals

        except Exception as e:
            self.logger.warning(f"Failed to query journal assignments: {e}")
            return []

    # ========================================================================
    # HELPERS
    # ========================================================================

    def _is_overdue(self, task: Any) -> bool:
        """Check if task is overdue"""
        due_date = getattr(task, "due_date", None)
        if not due_date:
            return False
        return due_date < date.today() and task.status != EntityStatus.COMPLETED

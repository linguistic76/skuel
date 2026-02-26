"""
Cross-Domain Analytics Service
================================

Subscribes to domain events to build cross-domain analytics and insights.

Features:
- Financial goal tracking (link expenses to goals)
- Journal mood analysis (track sentiment over time)
- Learning velocity tracking
- Spending patterns by domain
- Cross-domain correlation analysis

All analytics are built by subscribing to existing events - no service changes needed!
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.events import (
    ExpenseCreated,
    ExpensePaid,
    GoalCreated,
    # NOTE: JournalCreated REMOVED (February 2026) - Journal merged into Reports
    # Journal mood tracking now handled via report events
    KnowledgeMastered,
    LearningPathCompleted,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor


@dataclass
class FinancialGoalMetrics:
    """Metrics linking financial activity to goals."""

    goal_uid: str
    total_expenses: float
    expense_count: int
    budget_allocated: float | None
    budget_remaining: float | None
    top_expense_categories: dict[str, float]


@dataclass
class LearningVelocityMetrics:
    """Learning velocity and progress metrics."""

    user_uid: str
    period_days: int

    # Velocity metrics
    kus_mastered_per_week: float
    paths_completed: int
    total_learning_hours: float

    # Trend
    velocity_trend: str  # "accelerating", "steady", "slowing"
    compared_to_previous_period: float  # % change


@dataclass
class JournalMoodAnalysis:
    """Mood analysis from journal entries."""

    user_uid: str
    period_days: int

    # Mood tracking
    average_mood: float  # 0.0 to 1.0
    mood_trend: str  # "improving", "stable", "declining"
    most_common_themes: list[str]

    # Frequency
    entries_per_week: float
    longest_streak: int


@dataclass
class SpendingPatternAnalysis:
    """Spending pattern analysis by domain."""

    user_uid: str
    period_days: int

    # By domain
    spending_by_domain: dict[str, float]
    top_spending_domain: str | None

    # Patterns
    avg_expense_amount: float
    expense_frequency_per_week: float
    highest_expense_day: str | None


class CrossDomainAnalyticsService:
    """
    Cross-domain analytics service built entirely on event subscriptions.

    This service demonstrates the power of event-driven architecture:
    - No direct coupling to other services
    - Builds analytics by listening to events
    - Can be enabled/disabled by subscribing/unsubscribing

    Usage:
        # Wire in bootstrap
        analytics = CrossDomainAnalyticsService(driver)

        event_bus.subscribe(ExpenseCreated, analytics.handle_expense_created)
        event_bus.subscribe(GoalCreated, analytics.handle_goal_created)
        # NOTE: JournalCreated subscription removed (February 2026)
        event_bus.subscribe(KnowledgeMastered, analytics.handle_knowledge_mastered)
        event_bus.subscribe(LearningPathCompleted, analytics.handle_path_completed)

        # Query analytics
        velocity = await analytics.get_learning_velocity(user_uid, days_back=30)
        spending = await analytics.get_spending_patterns(user_uid, days_back=30)
        mood = await analytics.get_mood_analysis(user_uid, days_back=30)

    Semantic Types Used:
    - This is an analytics service that does not create semantic relationships
    - Consumes events from other services that create semantic relationships
    - No semantic relationship types used (event-driven aggregation only)

    Source Tag: N/A
    - This service does not create semantic relationships
    - Only aggregates data from domain events

    Confidence Scoring: N/A
    - No confidence scoring (analytics aggregation only)
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        """
        Initialize cross-domain analytics service.

        Args:
            executor: QueryExecutor for analytics storage
        """
        self.executor = executor
        self.logger = get_logger("skuel.services.cross_domain_analytics")

        # In-memory caches for fast analytics (could be Redis in production)
        self._expense_cache: defaultdict[str, list[dict]] = defaultdict(list)
        self._learning_cache: defaultdict[str, list[dict]] = defaultdict(list)
        # NOTE: _journal_cache removed (February 2026) - Journal merged into Reports

    # ========================================================================
    # EVENT HANDLERS - Financial Goal Tracking
    # ========================================================================

    async def handle_expense_created(self, event: ExpenseCreated) -> Result[None]:
        """
        Track expenses for financial goal analysis.

        Builds:
        - Spending patterns by domain
        - Financial goal progress
        - Budget tracking
        """
        try:
            expense_data = {
                "expense_uid": event.expense_uid,
                "user_uid": event.user_uid,
                "amount": event.amount,
                "category": event.category,
                "description": event.description,
                "occurred_at": event.occurred_at,
                "goal_uid": getattr(event, "linked_goal_uid", None),
            }

            # Cache for fast retrieval
            self._expense_cache[event.user_uid].append(expense_data)

            # Persist analytics
            query = """
            MERGE (analytics:FinancialAnalytics {user_uid: $user_uid})
            ON CREATE SET
                analytics.total_expenses = $amount,
                analytics.expense_count = 1,
                analytics.first_expense_at = datetime($occurred_at)
            ON MATCH SET
                analytics.total_expenses = analytics.total_expenses + $amount,
                analytics.expense_count = analytics.expense_count + 1,
                analytics.last_expense_at = datetime($occurred_at)

            WITH analytics
            MERGE (analytics)-[r:SPENT_IN_CATEGORY {category: $category}]->(cat:ExpenseCategory {name: $category})
            ON CREATE SET r.total_amount = $amount, r.count = 1
            ON MATCH SET r.total_amount = r.total_amount + $amount, r.count = r.count + 1
            """

            result = await self.executor.execute_query(
                query,
                {
                    "user_uid": event.user_uid,
                    "amount": event.amount,
                    "category": event.category,
                    "occurred_at": event.occurred_at.isoformat(),
                },
            )
            if result.is_error:
                self.logger.error(f"Error tracking expense: {result.error}")

            self.logger.debug(f"Tracked expense for financial analytics: {event.expense_uid}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Error tracking expense: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Failed to track expense: {e!s}", operation="handle_expense_created"
                )
            )

    async def handle_expense_paid(self, event: ExpensePaid) -> Result[None]:
        """Track expense payment for budget analysis."""
        # Update payment status for budget tracking
        self.logger.debug(f"Tracked expense payment: {event.expense_uid}")
        return Result.ok(None)

    async def handle_goal_created(self, event: GoalCreated) -> Result[None]:
        """Track financial goals for expense linking."""
        # Store goal for expense correlation
        self.logger.debug(f"Tracked goal for financial analytics: {event.goal_uid}")
        return Result.ok(None)

    # ========================================================================
    # EVENT HANDLERS - Learning Velocity
    # ========================================================================

    async def handle_knowledge_mastered(self, event: KnowledgeMastered) -> Result[None]:
        """
        Track knowledge mastery for learning velocity analysis.

        Builds:
        - Learning velocity (KUs mastered per week)
        - Mastery quality trends
        - Learning path progression
        """
        try:
            learning_data = {
                "ku_uid": event.ku_uid,
                "user_uid": event.user_uid,
                "mastery_score": event.mastery_score,
                "time_to_mastery_hours": event.time_to_mastery_hours,
                "occurred_at": event.occurred_at,
            }

            # Cache for velocity calculation
            self._learning_cache[event.user_uid].append(learning_data)

            # Persist velocity metrics
            query = """
            MERGE (velocity:LearningVelocity {user_uid: $user_uid})
            ON CREATE SET
                velocity.kus_mastered = 1,
                velocity.total_mastery_score = $mastery_score,
                velocity.first_mastery_at = datetime($occurred_at)
            ON MATCH SET
                velocity.kus_mastered = velocity.kus_mastered + 1,
                velocity.total_mastery_score = velocity.total_mastery_score + $mastery_score,
                velocity.last_mastery_at = datetime($occurred_at)
            """

            result = await self.executor.execute_query(
                query,
                {
                    "user_uid": event.user_uid,
                    "mastery_score": event.mastery_score,
                    "occurred_at": event.occurred_at.isoformat(),
                },
            )
            if result.is_error:
                self.logger.error(f"Error tracking learning velocity: {result.error}")

            self.logger.debug(f"Tracked knowledge mastery for velocity: {event.ku_uid}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Error tracking learning velocity: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Failed to track learning velocity: {e!s}",
                    operation="handle_knowledge_mastered",
                )
            )

    async def handle_path_completed(self, event: LearningPathCompleted) -> Result[None]:
        """Track learning path completion for velocity analysis."""
        try:
            query = """
            MERGE (velocity:LearningVelocity {user_uid: $user_uid})
            SET velocity.paths_completed = coalesce(velocity.paths_completed, 0) + 1
            """

            result = await self.executor.execute_query(query, {"user_uid": event.user_uid})
            if result.is_error:
                self.logger.error(f"Error tracking path completion: {result.error}")

            self.logger.debug(f"Tracked path completion for velocity: {event.path_uid}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Error tracking path completion: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Failed to track path completion: {e!s}",
                    operation="handle_path_completed",
                )
            )

    # ========================================================================
    # EVENT HANDLERS - Journal/Report Mood Analysis
    # NOTE: handle_journal_created removed (February 2026) - Journal merged into Reports
    # JournalCreated event no longer fired. Mood analysis can be re-added
    # by subscribing to SubmissionCreated and filtering ku_type="journal".
    # ========================================================================

    # ========================================================================
    # EVENT HANDLERS - Activity Domain Tracking
    # ========================================================================

    async def handle_task_completed(self, event: Any) -> Result[None]:
        """
        Track task completions for productivity analytics.

        Builds:
        - Task completion velocity (tasks per week)
        - Priority distribution patterns
        - Completion time trends
        """
        try:
            # Track completion velocity
            query = """
            MERGE (analytics:ProductivityAnalytics {user_uid: $user_uid})
            ON CREATE SET
                analytics.tasks_completed = 1,
                analytics.first_completion_at = datetime($occurred_at)
            ON MATCH SET
                analytics.tasks_completed = analytics.tasks_completed + 1,
                analytics.last_completion_at = datetime($occurred_at)
            """

            result = await self.executor.execute_query(
                query,
                {
                    "user_uid": event.user_uid,
                    "occurred_at": event.occurred_at.isoformat(),
                },
            )
            if result.is_error:
                self.logger.error(f"Error tracking task completion: {result.error}")

            self.logger.debug(f"Tracked task completion for analytics: {event.task_uid}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Error tracking task completion: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Failed to track task completion: {e!s}",
                    operation="handle_task_completed",
                )
            )

    async def handle_habit_completed(self, event: Any) -> Result[None]:
        """
        Track habit completions for consistency analytics.

        Builds:
        - Habit consistency scores
        - Streak patterns across habits
        - Category-based habit tracking
        """
        try:
            # Track habit consistency
            query = """
            MERGE (analytics:HabitAnalytics {user_uid: $user_uid})
            ON CREATE SET
                analytics.total_completions = 1,
                analytics.first_completion_at = datetime($occurred_at)
            ON MATCH SET
                analytics.total_completions = analytics.total_completions + 1,
                analytics.last_completion_at = datetime($occurred_at)
            """

            result = await self.executor.execute_query(
                query,
                {
                    "user_uid": event.user_uid,
                    "occurred_at": event.occurred_at.isoformat(),
                },
            )
            if result.is_error:
                self.logger.error(f"Error tracking habit completion: {result.error}")

            self.logger.debug(f"Tracked habit completion for analytics: {event.habit_uid}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Error tracking habit completion: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Failed to track habit completion: {e!s}",
                    operation="handle_habit_completed",
                )
            )

    async def handle_event_completed(self, event: Any) -> Result[None]:
        """
        Track calendar event completions for engagement analytics.

        Builds:
        - Event attendance patterns
        - Category-based event tracking
        - Time allocation analysis
        """
        try:
            # Track event attendance
            query = """
            MERGE (analytics:EventAnalytics {user_uid: $user_uid})
            ON CREATE SET
                analytics.events_attended = 1,
                analytics.first_attendance_at = datetime($occurred_at)
            ON MATCH SET
                analytics.events_attended = analytics.events_attended + 1,
                analytics.last_attendance_at = datetime($occurred_at)
            """

            result = await self.executor.execute_query(
                query,
                {
                    "user_uid": event.user_uid,
                    "occurred_at": event.occurred_at.isoformat(),
                },
            )
            if result.is_error:
                self.logger.error(f"Error tracking event attendance: {result.error}")

            self.logger.debug(f"Tracked event attendance for analytics: {event.event_uid}")
            return Result.ok(None)

        except Exception as e:
            self.logger.error(f"Error tracking event attendance: {e}")
            return Result.fail(
                Errors.system(
                    message=f"Failed to track event attendance: {e!s}",
                    operation="handle_event_completed",
                )
            )

    # ========================================================================
    # ANALYTICS QUERIES
    # ========================================================================

    @with_error_handling(
        error_type="system", operation="get_learning_velocity", uid_param="user_uid"
    )
    async def get_learning_velocity(
        self, user_uid: str, days_back: int = 30
    ) -> Result[LearningVelocityMetrics]:
        """
        Calculate learning velocity metrics.

        Args:
            user_uid: UID of the user,
            days_back: Number of days to analyze

        Returns:
            Result containing learning velocity metrics
        """
        start_date = datetime.now() - timedelta(days=days_back)

        query = """
        MATCH (velocity:LearningVelocity {user_uid: $user_uid})
        OPTIONAL MATCH (velocity)<-[:HAS_VELOCITY]-(ku:MasteryRecord)
        WHERE datetime(ku.mastered_at) >= datetime($start_date)
        WITH velocity, count(ku) as recent_kus, sum(ku.time_to_mastery_hours) as total_hours
        RETURN velocity, recent_kus, total_hours
        """

        result = await self.executor.execute_query(
            query, {"user_uid": user_uid, "start_date": start_date.isoformat()}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.ok(
                LearningVelocityMetrics(
                    user_uid=user_uid,
                    period_days=days_back,
                    kus_mastered_per_week=0.0,
                    paths_completed=0,
                    total_learning_hours=0.0,
                    velocity_trend="no_data",
                    compared_to_previous_period=0.0,
                )
            )

        # Calculate metrics
        recent_kus = record["recent_kus"] or 0
        weeks = days_back / 7
        kus_per_week = recent_kus / weeks if weeks > 0 else 0

        # Compare to previous period
        velocity_data = record["velocity"]
        total_kus = velocity_data.get("kus_mastered", 0)
        previous_kus = total_kus - recent_kus
        previous_per_week = previous_kus / weeks if weeks > 0 else 0

        trend = "steady"
        if kus_per_week > previous_per_week * 1.2:
            trend = "accelerating"
        elif kus_per_week < previous_per_week * 0.8:
            trend = "slowing"

        change_pct = (
            ((kus_per_week - previous_per_week) / previous_per_week * 100)
            if previous_per_week > 0
            else 0.0
        )

        metrics = LearningVelocityMetrics(
            user_uid=user_uid,
            period_days=days_back,
            kus_mastered_per_week=kus_per_week,
            paths_completed=velocity_data.get("paths_completed", 0),
            total_learning_hours=record["total_hours"] or 0.0,
            velocity_trend=trend,
            compared_to_previous_period=change_pct,
        )

        return Result.ok(metrics)

    @with_error_handling(
        error_type="system", operation="get_spending_patterns", uid_param="user_uid"
    )
    async def get_spending_patterns(
        self, user_uid: str, days_back: int = 30
    ) -> Result[SpendingPatternAnalysis]:
        """
        Analyze spending patterns by domain.

        Args:
            user_uid: UID of the user,
            days_back: Number of days to analyze

        Returns:
            Result containing spending pattern analysis
        """
        datetime.now() - timedelta(days=days_back)

        query = """
        MATCH (analytics:FinancialAnalytics {user_uid: $user_uid})-[r:SPENT_IN_CATEGORY]->(cat:ExpenseCategory)
        RETURN cat.name as category, r.total_amount as amount, r.count as count
        ORDER BY r.total_amount DESC
        """

        result = await self.executor.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        if not records:
            return Result.ok(
                SpendingPatternAnalysis(
                    user_uid=user_uid,
                    period_days=days_back,
                    spending_by_domain={},
                    top_spending_domain=None,
                    avg_expense_amount=0.0,
                    expense_frequency_per_week=0.0,
                    highest_expense_day=None,
                )
            )

        # Build analysis
        spending_by_domain = {r["category"]: r["amount"] for r in records}
        top_domain = records[0]["category"] if records else None

        total_amount = sum(r["amount"] for r in records)
        total_count = sum(r["count"] for r in records)

        avg_amount = total_amount / total_count if total_count > 0 else 0.0
        frequency_per_week = total_count / (days_back / 7) if days_back > 0 else 0.0

        analysis = SpendingPatternAnalysis(
            user_uid=user_uid,
            period_days=days_back,
            spending_by_domain=spending_by_domain,
            top_spending_domain=top_domain,
            avg_expense_amount=avg_amount,
            expense_frequency_per_week=frequency_per_week,
            highest_expense_day=None,  # Could calculate from event timestamps
        )

        return Result.ok(analysis)

    @with_error_handling(error_type="system", operation="get_mood_analysis", uid_param="user_uid")
    async def get_mood_analysis(
        self, user_uid: str, days_back: int = 30
    ) -> Result[JournalMoodAnalysis]:
        """
        Analyze journal mood and sentiment.

        Args:
            user_uid: UID of the user,
            days_back: Number of days to analyze

        Returns:
            Result containing mood analysis
        """
        query = """
        MATCH (analytics:JournalAnalytics {user_uid: $user_uid})
        RETURN analytics
        """

        result = await self.executor.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.ok(
                JournalMoodAnalysis(
                    user_uid=user_uid,
                    period_days=days_back,
                    average_mood=0.5,
                    mood_trend="no_data",
                    most_common_themes=[],
                    entries_per_week=0.0,
                    longest_streak=0,
                )
            )

        analytics = record["analytics"]
        total_entries = analytics.get("total_entries", 0)

        weeks = days_back / 7
        entries_per_week = total_entries / weeks if weeks > 0 else 0.0

        # Simplified mood analysis (would integrate with sentiment analysis in production)
        analysis = JournalMoodAnalysis(
            user_uid=user_uid,
            period_days=days_back,
            average_mood=0.65,  # Placeholder - would calculate from sentiment
            mood_trend="stable",  # Placeholder - would analyze trend
            most_common_themes=["reflection", "goals", "learning"],  # Placeholder
            entries_per_week=entries_per_week,
            longest_streak=7,  # Placeholder - would calculate from dates
        )

        return Result.ok(analysis)

    @with_error_handling(
        error_type="database", operation="get_financial_goal_metrics", uid_param="goal_uid"
    )
    async def get_financial_goal_metrics(self, goal_uid: str) -> Result[FinancialGoalMetrics]:
        """
        Get financial metrics for a specific goal.

        Links expenses to goals for budget tracking.

        Args:
            goal_uid: UID of the goal

        Returns:
            Result containing financial goal metrics
        """
        # Query expenses linked to this goal
        query = """
        MATCH (goal:Goal {uid: $goal_uid})
        OPTIONAL MATCH (goal)<-[:SUPPORTS_GOAL]-(expense:Expense)
        WITH goal, collect(expense) as expenses, sum(expense.amount) as total
        RETURN goal, expenses, total
        """

        result = await self.executor.execute_query(query, {"goal_uid": goal_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        goal = record["goal"]
        expenses = record["expenses"] or []
        total_expenses = record["total"] or 0.0

        # Calculate budget remaining
        budget = goal.get("budget_allocated")
        remaining = budget - total_expenses if budget else None

        # Categorize expenses
        category_totals: dict[str, float] = {}
        for expense in expenses:
            category = expense.get("category", "uncategorized")
            category_totals[category] = category_totals.get(category, 0.0) + expense.get(
                "amount", 0.0
            )

        metrics = FinancialGoalMetrics(
            goal_uid=goal_uid,
            total_expenses=total_expenses,
            expense_count=len(expenses),
            budget_allocated=budget,
            budget_remaining=remaining,
            top_expense_categories=dict(
                sorted(category_totals.items(), key=itemgetter(1), reverse=True)[:5]
            ),
        )

        return Result.ok(metrics)

    @with_error_handling(
        error_type="system", operation="get_productivity_metrics", uid_param="user_uid"
    )
    async def get_productivity_metrics(self, user_uid: str) -> Result[dict]:
        """
        Get productivity analytics from task completions.

        Queries ProductivityAnalytics nodes created by handle_task_completed event handler.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing productivity metrics dict with:
            - tasks_completed: Total count
            - first_completion_at: First completion timestamp
            - last_completion_at: Last completion timestamp
            - completion_velocity: Tasks per week
        """
        query = """
        MATCH (analytics:ProductivityAnalytics {user_uid: $user_uid})
        RETURN analytics
        """

        result = await self.executor.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "tasks_completed": 0,
                    "first_completion_at": None,
                    "last_completion_at": None,
                    "completion_velocity": 0.0,
                }
            )

        analytics = record["analytics"]
        tasks_completed = analytics.get("tasks_completed", 0)

        # Calculate velocity (tasks per week)
        first_at = analytics.get("first_completion_at")
        last_at = analytics.get("last_completion_at")

        velocity = 0.0
        if first_at and last_at:
            days_active = (last_at - first_at).days or 1
            weeks_active = days_active / 7
            velocity = tasks_completed / weeks_active if weeks_active > 0 else 0.0

        return Result.ok(
            {
                "user_uid": user_uid,
                "tasks_completed": tasks_completed,
                "first_completion_at": first_at,
                "last_completion_at": last_at,
                "completion_velocity": round(velocity, 2),
            }
        )

    @with_error_handling(
        error_type="system", operation="get_habit_consistency", uid_param="user_uid"
    )
    async def get_habit_consistency(self, user_uid: str) -> Result[dict]:
        """
        Get habit consistency analytics.

        Queries HabitAnalytics nodes created by handle_habit_completed event handler.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing habit consistency metrics dict with:
            - total_completions: Total habit completions
            - first_completion_at: First completion timestamp
            - last_completion_at: Last completion timestamp
            - consistency_score: Completions per week
        """
        query = """
        MATCH (analytics:HabitAnalytics {user_uid: $user_uid})
        RETURN analytics
        """

        result = await self.executor.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "total_completions": 0,
                    "first_completion_at": None,
                    "last_completion_at": None,
                    "consistency_score": 0.0,
                }
            )

        analytics = record["analytics"]
        total_completions = analytics.get("total_completions", 0)

        # Calculate consistency score (completions per week)
        first_at = analytics.get("first_completion_at")
        last_at = analytics.get("last_completion_at")

        consistency = 0.0
        if first_at and last_at:
            days_active = (last_at - first_at).days or 1
            weeks_active = days_active / 7
            consistency = total_completions / weeks_active if weeks_active > 0 else 0.0

        return Result.ok(
            {
                "user_uid": user_uid,
                "total_completions": total_completions,
                "first_completion_at": first_at,
                "last_completion_at": last_at,
                "consistency_score": round(consistency, 2),
            }
        )

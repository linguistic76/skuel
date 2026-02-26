# BaseAnalyticsService Implementation Patterns

## Pattern 1: Complete Service Implementation

A full analytics service with all common patterns:

```python
"""
Habits Intelligence Service
===========================

Intelligence for habit streak patterns and knowledge reinforcement.
"""

from typing import Any, ClassVar

from core.events.habit_events import HabitCompleted, HabitStreakBroken
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.enums import Domain
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence.orchestrator import GraphContextOrchestrator
from core.ports import HabitsOperations
from core.utils.result_simplified import Result
from core.utils.errors_simplified import Errors


class HabitsIntelligenceService(BaseAnalyticsService[HabitsOperations, Habit]):
    """Analytics service for habit analysis and recommendations."""

    # Class attributes
    _service_name: ClassVar[str] = "habits.analytics"
    _require_relationships: ClassVar[bool] = False
    _event_handlers: ClassVar[dict[type, str]] = {
        HabitCompleted: "handle_habit_completed",
        HabitStreakBroken: "handle_streak_broken",
    }

    def __init__(
        self,
        backend: HabitsOperations,
        graph_intelligence_service=None,
        relationship_service=None,
        event_bus=None,
    ) -> None:
        # ALWAYS call super first
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            event_bus=event_bus,
        )

        # Initialize orchestrator if graph intelligence available
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Habit, HabitDTO](
                service=self,
                backend_get_method="get",
                dto_class=HabitDTO,
                model_class=Habit,
                domain=Domain.HABITS,
            )

        # Domain-specific initialization
        self._streak_thresholds = {
            "at_risk": 7,    # Days without completion
            "broken": 14,   # Days to consider streak broken
            "strong": 21,   # Days for strong streak
        }

    # =========================================================================
    # PROTOCOL METHODS (Three Standardized)
    # =========================================================================

    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Habit, Any]]:
        """Get habit with full graph neighborhood."""
        if not self.orchestrator:
            return Result.fail(Errors.system(
                "Orchestrator unavailable - graph intelligence not provided"
            ))
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Analyze habit performance over period."""
        habits = await self.backend.get_user_habits(user_uid)
        if habits.is_error:
            return habits

        return Result.ok({
            "total_habits": len(habits.value),
            "active_habits": sum(1 for h in habits.value if h.is_active),
            "average_streak": self._avg_streak(habits.value),
            "at_risk_count": sum(1 for h in habits.value if h.streak_at_risk),
            "completion_rate": self._completion_rate(habits.value, period_days),
        })

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """Get habit-specific insights."""
        self._require_graph_intelligence("get_domain_insights")

        habit_result = await self.backend.get(uid)
        if habit_result.is_error:
            return habit_result

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found("Habit", uid))

        return Result.ok({
            "streak_analysis": self._analyze_streak(habit),
            "recommendations": self._generate_recommendations(habit),
            "knowledge_reinforcement": await self._get_knowledge_reinforcement(uid),
        })

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    async def handle_habit_completed(self, event: HabitCompleted) -> None:
        """Handle habit completion - update knowledge substance."""
        self.logger.info(f"Habit completed: {event.habit_uid}")
        if self.relationships:
            await self._update_knowledge_substance(event.habit_uid)

    async def handle_streak_broken(self, event: HabitStreakBroken) -> None:
        """Handle streak break - analyze and log."""
        self.logger.warning(f"Streak broken for {event.habit_uid}: {event.streak_length} days")

    # =========================================================================
    # DOMAIN-SPECIFIC METHODS
    # =========================================================================

    async def analyze_streak_patterns(
        self, user_uid: str, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        """Analyze user's streak patterns across all habits."""
        habits = await self.backend.get_user_habits(user_uid)
        if habits.is_error:
            return habits

        patterns = {
            "strong_streaks": [],
            "at_risk": [],
            "broken": [],
            "recommendations": [],
        }

        for habit in habits.value:
            if habit.current_streak >= self._streak_thresholds["strong"]:
                patterns["strong_streaks"].append(habit.uid)
            elif habit.streak_at_risk:
                patterns["at_risk"].append(habit.uid)
            elif habit.streak_broken:
                patterns["broken"].append(habit.uid)

        # Generate recommendations
        if patterns["at_risk"]:
            patterns["recommendations"].append(
                f"Focus on {len(patterns['at_risk'])} habits at risk of streak break"
            )

        return Result.ok(patterns)

    async def get_knowledge_reinforcement_score(
        self, uid: str
    ) -> Result[float]:
        """Calculate how well this habit reinforces knowledge (0-10 scale)."""
        self._require_relationship_service("get_knowledge_reinforcement_score")

        ku_result = await self.relationships.get_related_uids(
            uid, "REINFORCES_KNOWLEDGE", direction="outgoing"
        )
        if ku_result.is_error:
            return Result.ok(0.0)

        ku_count = len(ku_result.value)
        # Score: 0-3 KUs = low, 4-7 = medium, 8+ = high
        score = min(10.0, ku_count * 1.25)
        return Result.ok(score)

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _avg_streak(self, habits: list[Habit]) -> float:
        if not habits:
            return 0.0
        return sum(h.current_streak for h in habits) / len(habits)

    def _completion_rate(self, habits: list[Habit], period_days: int) -> float:
        # Implementation
        pass

    def _analyze_streak(self, habit: Habit) -> dict:
        return {
            "current": habit.current_streak,
            "longest": habit.longest_streak,
            "status": self._streak_status(habit),
        }

    def _streak_status(self, habit: Habit) -> str:
        if habit.current_streak >= self._streak_thresholds["strong"]:
            return "strong"
        if habit.streak_at_risk:
            return "at_risk"
        return "healthy"

    def _generate_recommendations(self, habit: Habit) -> list[str]:
        recs = []
        if habit.streak_at_risk:
            recs.append("Complete this habit today to maintain your streak")
        if habit.current_streak >= self._streak_thresholds["strong"]:
            recs.append("Strong streak! Consider increasing difficulty")
        return recs

    async def _get_knowledge_reinforcement(self, uid: str) -> dict:
        if not self.relationships:
            return {"ku_count": 0, "ku_uids": []}

        result = await self.relationships.get_related_uids(
            uid, "REINFORCES_KNOWLEDGE", direction="outgoing"
        )
        return {
            "ku_count": len(result.value) if result.is_ok else 0,
            "ku_uids": result.value if result.is_ok else [],
        }

    async def _update_knowledge_substance(self, habit_uid: str) -> None:
        # Update substance for related knowledge units
        pass
```

---

## Pattern 2: Template Method Usage

Using `_analyze_entity_with_context()` for consistent analysis:

```python
class GoalsIntelligenceService(BaseAnalyticsService[GoalsOperations, Goal]):
    _service_name = "goals.analytics"

    async def get_goal_progress_dashboard(self, uid: str) -> Result[dict]:
        """Get comprehensive goal progress analysis."""
        return await self._analyze_entity_with_context(
            uid=uid,
            context_method="get_goal_cross_domain_context",
            context_type=GoalCrossContext,
            metrics_fn=self._calculate_goal_metrics,
            recommendations_fn=self._generate_goal_recommendations,
            min_confidence=0.7,
        )

    def _calculate_goal_metrics(
        self, goal: Goal, context: GoalCrossContext
    ) -> dict[str, Any]:
        """Calculate metrics from goal and context."""
        return {
            "progress_percentage": goal.progress * 100,
            "days_remaining": (goal.target_date - date.today()).days,
            "supporting_habits_count": len(context.supporting_habits),
            "blocking_tasks_count": len(context.blocking_tasks),
            "is_on_track": goal.is_on_track(),
            "momentum_score": self._calculate_momentum(goal, context),
        }

    def _generate_goal_recommendations(
        self,
        goal: Goal,
        context: GoalCrossContext,
        metrics: dict[str, Any]
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations = []

        if metrics["blocking_tasks_count"] > 0:
            recommendations.append(
                f"Complete {metrics['blocking_tasks_count']} blocking tasks to unblock progress"
            )

        if metrics["supporting_habits_count"] < 2:
            recommendations.append(
                "Add more supporting habits to sustain progress"
            )

        if not metrics["is_on_track"]:
            recommendations.append(
                "Consider adjusting timeline or breaking goal into smaller milestones"
            )

        return recommendations
```

---

## Pattern 3: Cross-Domain Intelligence

Querying relationships across domains:

```python
class TasksIntelligenceService(BaseAnalyticsService[TasksOperations, Task]):
    _service_name = "tasks.analytics"

    async def get_knowledge_application_opportunities(
        self, user_uid: str, ku_uid: str
    ) -> Result[dict[str, Any]]:
        """Find tasks where this knowledge can be applied."""
        self._require_relationship_service("get_knowledge_application_opportunities")

        # Find tasks that could use this knowledge
        tasks_result = await self.relationships.get_related_uids(
            ku_uid,
            "APPLIES_KNOWLEDGE",
            direction="incoming"
        )

        # Find tasks requiring this as prerequisite
        prereq_result = await self.relationships.get_related_uids(
            ku_uid,
            "REQUIRES_KNOWLEDGE",
            direction="incoming"
        )

        # Filter to user's tasks
        user_tasks = await self.backend.get_user_tasks(user_uid)
        user_task_uids = {t.uid for t in user_tasks.value} if user_tasks.is_ok else set()

        applicable = [
            uid for uid in tasks_result.value
            if uid in user_task_uids
        ] if tasks_result.is_ok else []

        prerequisite_for = [
            uid for uid in prereq_result.value
            if uid in user_task_uids
        ] if prereq_result.is_ok else []

        return Result.ok({
            "knowledge_uid": ku_uid,
            "applicable_tasks": applicable,
            "prerequisite_for_tasks": prerequisite_for,
            "recommendation": self._recommend_application(
                applicable, prerequisite_for
            ),
        })

    def _recommend_application(
        self, applicable: list[str], prerequisite_for: list[str]
    ) -> str:
        if prerequisite_for:
            return f"Master this knowledge to unblock {len(prerequisite_for)} tasks"
        if applicable:
            return f"Apply this knowledge to {len(applicable)} current tasks"
        return "Consider creating tasks to practice this knowledge"
```

---

## Pattern 4: Dual-Track Assessment

Using `_dual_track_assessment()` to compare user perception with system measurement:

```python
class PrinciplesIntelligenceService(BaseAnalyticsService[PrinciplesOperations, Principle]):
    _service_name = "principles.analytics"

    async def assess_alignment_dual_track(
        self,
        principle_uid: str,
        user_uid: str,
        user_level: AlignmentLevel,
        evidence: str,
        reflection: str | None = None,
    ) -> Result[DualTrackResult[AlignmentLevel]]:
        """Compare user's self-assessed alignment with system measurement."""
        return await self._dual_track_assessment(
            uid=principle_uid,
            user_uid=user_uid,
            user_level=user_level,
            user_evidence=evidence,
            user_reflection=reflection,
            system_calculator=self._calculate_system_alignment,
            level_scorer=self._alignment_level_to_score,
            entity_type=EntityType.PRINCIPLE.value,
            insight_generator=self._generate_alignment_insights,
            recommendation_generator=self._generate_alignment_recommendations,
        )

    async def _calculate_system_alignment(
        self, principle: Principle, user_uid: str
    ) -> tuple[AlignmentLevel, float, list[str]]:
        """Calculate alignment from user's actual behavior."""
        evidence = []

        # Check goals aligned with this principle
        goals_result = await self.relationships.get_related_uids(
            principle.uid, "ALIGNED_WITH_PRINCIPLE", direction="incoming"
        )
        goal_count = len(goals_result.value) if goals_result.is_ok else 0
        if goal_count > 0:
            evidence.append(f"{goal_count} goals aligned")

        # Check habits expressing this principle
        habits_result = await self.relationships.get_related_uids(
            principle.uid, "EXPRESSES_PRINCIPLE", direction="incoming"
        )
        habit_count = len(habits_result.value) if habits_result.is_ok else 0
        if habit_count > 0:
            evidence.append(f"{habit_count} habits express this value")

        # Calculate score
        score = min(1.0, (goal_count * 0.2) + (habit_count * 0.3))

        # Determine level
        if score >= 0.8:
            level = AlignmentLevel.STRONG
        elif score >= 0.5:
            level = AlignmentLevel.MODERATE
        elif score >= 0.2:
            level = AlignmentLevel.EMERGING
        else:
            level = AlignmentLevel.MINIMAL

        return level, score, evidence

    def _alignment_level_to_score(self, level: AlignmentLevel) -> float:
        """Convert alignment level enum to 0.0-1.0 score."""
        return {
            AlignmentLevel.STRONG: 0.9,
            AlignmentLevel.MODERATE: 0.6,
            AlignmentLevel.EMERGING: 0.3,
            AlignmentLevel.MINIMAL: 0.1,
        }.get(level, 0.5)
```

---

## Pattern 5: Using Shared Utilities

Leveraging shared intelligence utilities:

```python
from core.services.intelligence import (
    RecommendationEngine,
    MetricsCalculator,
    PatternAnalyzer,
    analyze_completion_trend,
)


class EventsIntelligenceService(BaseAnalyticsService[EventsOperations, Event]):
    _service_name = "events.analytics"

    async def analyze_event_patterns(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Analyze event completion patterns."""
        events = await self.backend.get_completed_events(user_uid, period_days)
        if events.is_error:
            return events

        # Use shared utilities
        trend = analyze_completion_trend(
            [e.completed_at for e in events.value if e.completed_at]
        )

        metrics = MetricsCalculator.calculate_event_metrics(events.value)

        patterns = PatternAnalyzer.find_patterns(
            [e.title for e in events.value]
        )

        # Build recommendations with fluent builder
        recommendations = (
            RecommendationEngine()
            .add_if(trend == "declining", "Schedule more regular events")
            .add_if(metrics["completion_rate"] < 0.7, "Consider fewer commitments")
            .add_if(len(patterns) > 5, f"Focus on {patterns[0]} events")
            .build()
        )

        return Result.ok({
            "trend": trend,
            "metrics": metrics,
            "patterns": patterns,
            "recommendations": recommendations,
        })
```

---

## Pattern 6: Curriculum Intelligence (Shared Content)

Intelligence for shared curriculum content (no user ownership):

```python
class LsIntelligenceService(BaseAnalyticsService[BackendOperations[Ls], Ls]):
    """Analytics for Learning Steps - shared content."""

    _service_name = "ls.analytics"

    async def is_ready(
        self, ls_uid: str, completed_step_uids: set[str]
    ) -> Result[bool]:
        """Check if learning step prerequisites are met."""
        self._require_relationship_service("is_ready")

        # Get prerequisite steps
        prereqs = await self.relationships.get_related_uids(
            ls_uid, "REQUIRES_STEP", direction="outgoing"
        )

        if prereqs.is_error:
            return Result.ok(True)  # No prerequisites = ready

        # All prerequisites must be completed
        ready = all(uid in completed_step_uids for uid in prereqs.value)
        return Result.ok(ready)

    async def calculate_guidance_strength(self, ls_uid: str) -> Result[float]:
        """Calculate how well this step provides guidance (0.0-1.0)."""
        self._require_relationship_service("calculate_guidance_strength")

        # 40% from principles, 60% from choices
        principles = await self.relationships.get_related_uids(
            ls_uid, "GUIDED_BY_PRINCIPLE", direction="outgoing"
        )
        choices = await self.relationships.get_related_uids(
            ls_uid, "OFFERS_CHOICE", direction="outgoing"
        )

        principle_score = min(1.0, len(principles.value) * 0.2) if principles.is_ok else 0.0
        choice_score = min(1.0, len(choices.value) * 0.15) if choices.is_ok else 0.0

        # Weighted combination
        score = (principle_score * 0.4) + (choice_score * 0.6)
        return Result.ok(score)

    async def get_practice_summary(self, ls_uid: str) -> Result[dict[str, Any]]:
        """Get practice opportunities summary."""
        self._require_relationship_service("get_practice_summary")

        habits = await self.relationships.get_related_uids(
            ls_uid, "BUILDS_HABIT", direction="outgoing"
        )
        tasks = await self.relationships.get_related_uids(
            ls_uid, "ASSIGNS_TASK", direction="outgoing"
        )
        events = await self.relationships.get_related_uids(
            ls_uid, "SCHEDULES_EVENT", direction="outgoing"
        )

        return Result.ok({
            "habits_count": len(habits.value) if habits.is_ok else 0,
            "tasks_count": len(tasks.value) if tasks.is_ok else 0,
            "events_count": len(events.value) if events.is_ok else 0,
            "completeness_score": self._practice_completeness_score(
                len(habits.value) if habits.is_ok else 0,
                len(tasks.value) if tasks.is_ok else 0,
                len(events.value) if events.is_ok else 0,
            ),
        })

    def _practice_completeness_score(
        self, habits: int, tasks: int, events: int
    ) -> float:
        """Each type contributes 1/3 to completeness."""
        score = 0.0
        if habits > 0:
            score += 0.333
        if tasks > 0:
            score += 0.333
        if events > 0:
            score += 0.334
        return score
```

---

## Pattern 7: Error Handling

Proper Result[T] error handling in analytics methods:

```python
async def analyze_with_fallbacks(
    self, uid: str
) -> Result[dict[str, Any]]:
    """Analyze with graceful degradation."""

    # Primary analysis requires graph intelligence
    if self.graph_intel:
        context_result = await self.graph_intel.get_context(uid)
        if context_result.is_ok:
            return Result.ok({
                "analysis": self._full_analysis(context_result.value),
                "mode": "full",
            })

    # Fallback to backend-only analysis
    entity_result = await self.backend.get(uid)
    if entity_result.is_error:
        return entity_result

    if not entity_result.value:
        return Result.fail(Errors.not_found("Entity", uid))

    return Result.ok({
        "analysis": self._basic_analysis(entity_result.value),
        "mode": "basic",
        "note": "Limited analysis - graph intelligence unavailable",
    })
```

---

## Anti-Pattern Examples

### Wrong: Accessing optional services without guards

```python
# WRONG
async def get_insights(self, uid: str):
    return await self.graph_intel.get_context(uid)  # Crashes if None!

# CORRECT
async def get_insights(self, uid: str) -> Result[dict]:
    self._require_graph_intelligence("get_insights")
    return await self.graph_intel.get_context(uid)
```

### Wrong: Raising exceptions instead of returning Result

```python
# WRONG
async def analyze(self, uid: str):
    if not uid:
        raise ValueError("UID required")

# CORRECT
async def analyze(self, uid: str) -> Result[dict]:
    if not uid:
        return Result.fail(Errors.validation("UID required", field="uid"))
```

### Wrong: Mixing sync/async inappropriately

```python
# WRONG - blocking call in async method
async def get_data(self):
    return self.expensive_sync_operation()  # Blocks event loop

# CORRECT - run in executor if needed
async def get_data(self):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, self.expensive_sync_operation)
```

---

## Note on AI Features

For AI-powered insights (LLM, embeddings), see the **[base-ai-service](../base-ai-service/SKILL.md)** skill. Analytics services intentionally have NO AI dependencies - the app runs at full capacity without LLM.

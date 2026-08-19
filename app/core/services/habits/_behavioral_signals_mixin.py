"""
Behavioral Signals Mixin — HabitsIntelligenceService
=====================================================

Performance analysis, knowledge reinforcement, and goal support methods:
  analyze_habit_performance, get_habit_knowledge_reinforcement,
  get_habit_goal_support, and their private helpers.

Part of habits_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import Any

from core.models.graph.path_aware_types import HabitCrossContext
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.services.intelligence import (
    MetricsCalculator,
    calculate_habit_integration_metrics,
    habit_recommendations,
)
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Result


class _BehavioralSignalsMixin:
    """
    Performance, knowledge reinforcement, and goal support methods for
    HabitsIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by HabitsIntelligenceService.__init__
    orchestrator: Any
    relationships: Any
    cross_domain_query: Any
    insight_store: Any
    logger: Any
    # Provided by BaseAnalyticsService via multiple inheritance on the composed service.
    _analyze_entity_with_typed_context: Any
    _to_domain_model: Any

    @requires_graph_intelligence("analyze_habit_performance")
    async def analyze_habit_performance(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Analyze habit with knowledge reinforcement and goal support

        Provides comprehensive performance analysis including:
        - Knowledge areas being reinforced through habit practice
        - Goals supported by this habit
        - Streak score and consistency metrics
        - Reinforcement effectiveness calculation
        - Performance insights and recommendations

        Args:
            uid: Habit UID

        Returns:
            Result containing performance analysis:
            {
                "habit": Habit,
                "performance": {
                    "knowledge_reinforced": List[Ku],
                    "supporting_goals": List[Goal],
                    "streak_score": float,
                    "reinforcement_effectiveness": float,
                    "consistency_score": float,
                    "total_knowledge_areas": int,
                    "total_goals_supported": int
                },
                "insights": {
                    "high_reinforcement": bool, # effectiveness > 5.0
                    "goal_aligned": bool, # supports goals
                    "knowledge_builder": bool # reinforces knowledge
                },
                "recommendations": {
                    "maintain_consistency": bool,
                    "expand_knowledge_links": bool,
                    "align_with_more_goals": bool
                },
                "graph_context": GraphContext,
                "performance_metrics": {
                    "query_time_ms": float,
                    "nodes_returned": int
                }
            }

        Example:
            ```python
            result = await habits_intel.analyze_habit_performance("habit_1")
            analysis = result.value

            perf = analysis["performance"]
            print(f"Streak: {perf['streak_score']}")
            print(f"Reinforces {perf['total_knowledge_areas']} knowledge areas")
            print(f"Supports {perf['total_goals_supported']} goals")

            if analysis["insights"]["high_reinforcement"]:
                print("This is a highly effective learning habit!")
            ```

        Refactoring:
        - Uses BaseAnalyticsService._analyze_entity_with_typed_context template
          (path-aware HabitCrossContext via the canonical typed reader).
        """
        # Use base class template over the CANONICAL typed (path-aware) reader.
        analysis_result = await self._analyze_entity_with_typed_context(
            uid,
            metrics_fn=calculate_habit_integration_metrics,
            recommendations_fn=habit_recommendations,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        habit = self._to_domain_model(analysis["entity"], HabitDTO, Habit)
        context: HabitCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Read UIDs off the path-aware entities.
        knowledge_reinforcement_uids = [k.uid for k in context.knowledge]
        supporting_goal_uids = [g.uid for g in context.goals]

        # Calculate performance metrics
        streak_score = habit.current_streak / habit.best_streak if habit.best_streak > 0 else 0.0
        consistency_score = habit.calculate_consistency_score()
        reinforcement_effectiveness = len(knowledge_reinforcement_uids) * consistency_score

        # Generate insights from metrics
        insights = {
            "high_reinforcement": reinforcement_effectiveness > 5.0,
            "goal_aligned": metrics["has_goal_connection"],
            "knowledge_builder": metrics["is_knowledge_builder"],
        }

        # Generate recommendations dict (convert list to dict for backward compatibility)
        recommendations = {
            "maintain_consistency": consistency_score < 0.7,
            "expand_knowledge_links": metrics["knowledge_reinforcement_count"] < 3,
            "align_with_more_goals": metrics["goal_support_count"] < 2,
        }

        return Result.ok(
            {
                "habit": habit,
                "performance": {
                    "knowledge_reinforcement_uids": knowledge_reinforcement_uids,
                    "supporting_goal_uids": supporting_goal_uids,
                    "streak_score": streak_score,
                    "reinforcement_effectiveness": reinforcement_effectiveness,
                    "consistency_score": consistency_score,
                    "total_knowledge_areas": metrics["knowledge_reinforcement_count"],
                    "total_goals_supported": metrics["goal_support_count"],
                },
                "insights": insights,
                "recommendations": recommendations,
                "metrics": metrics,  # Include standard metrics
            }
        )

    @requires_graph_intelligence("get_habit_knowledge_reinforcement")
    async def get_habit_knowledge_reinforcement(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get habit's knowledge practice tracking

        Analyzes how this habit reinforces knowledge through practice:
        - Knowledge units actively reinforced
        - Practice frequency and effectiveness
        - Knowledge mastery progression
        - Learning opportunities

        Args:
            uid: Habit UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing knowledge reinforcement analysis:
            {
                "habit": Habit,
                "knowledge_reinforcement": {
                    "reinforced_knowledge": List[Ku],
                    "practice_frequency": str, # from habit
                    "practice_effectiveness_score": float,
                    "mastery_progression": List[Dict],
                    "knowledge_coverage": float # 0-1
                },
                "learning_analysis": {
                    "primary_knowledge_areas": List[str],
                    "skill_development_rate": float,
                    "learning_consistency": float
                },
                "graph_context": GraphContext
            }

        Example:
            ```python
            result = await habits_intel.get_habit_knowledge_reinforcement("habit_1")
            analysis = result.value

            kr = analysis["knowledge_reinforcement"]
            print(f"Reinforces {len(kr['reinforced_knowledge'])} areas")
            print(f"Effectiveness: {kr['practice_effectiveness_score']}")
            ```

        Refactoring:
        - Uses BaseAnalyticsService._analyze_entity_with_typed_context template
          (path-aware HabitCrossContext via the canonical typed reader).
        """
        # Use base class template over the CANONICAL typed (path-aware) reader.
        analysis_result = await self._analyze_entity_with_typed_context(
            uid,
            metrics_fn=calculate_habit_integration_metrics,
            depth=depth,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        habit = self._to_domain_model(analysis["entity"], HabitDTO, Habit)
        context: HabitCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Read UIDs off the path-aware entities.
        knowledge_reinforcement_uids = [k.uid for k in context.knowledge]

        # Calculate practice effectiveness
        practice_effectiveness = self._calculate_practice_effectiveness(
            habit, len(knowledge_reinforcement_uids)
        )

        # Analyze mastery progression per knowledge UID
        mastery_progression = [
            {
                "knowledge_uid": ku_uid,
                "practice_count": habit.current_streak,
                "estimated_mastery": min(1.0, practice_effectiveness * 0.1),
            }
            for ku_uid in knowledge_reinforcement_uids
        ]

        # Calculate knowledge coverage
        knowledge_coverage = min(1.0, len(knowledge_reinforcement_uids) / 10.0)

        # Learning analysis
        consistency_score = habit.calculate_consistency_score()
        learning_analysis = {
            "knowledge_uids": knowledge_reinforcement_uids[:3],
            "skill_development_rate": practice_effectiveness / 10.0,
            "learning_consistency": consistency_score,
        }

        return Result.ok(
            {
                "habit": habit,
                "knowledge_reinforcement": {
                    "knowledge_reinforcement_uids": knowledge_reinforcement_uids,
                    "practice_frequency": habit.recurrence_pattern or "daily",
                    "practice_effectiveness_score": practice_effectiveness,
                    "mastery_progression": mastery_progression,
                    "knowledge_coverage": knowledge_coverage,
                },
                "learning_analysis": learning_analysis,
                "metrics": metrics,  # Include standard metrics
            }
        )

    @requires_graph_intelligence("get_habit_goal_support")
    async def get_habit_goal_support(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get habit's goal contribution analysis

        Analyzes how this habit supports user's goals:
        - Goals directly supported
        - Contribution strength to each goal
        - Goal alignment score
        - Progress impact on goal completion

        Args:
            uid: Habit UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing goal support analysis:
            {
                "habit": Habit,
                "goal_support": {
                    "supported_goals": List[Goal],
                    "goal_contributions": List[Dict], # per-goal contribution
                    "alignment_score": float, # 0-10
                    "total_goals_supported": int,
                    "primary_goal": Optional[Goal]
                },
                "impact_analysis": {
                    "high_impact": bool, # alignment > 7.0
                    "goal_aligned": bool, # supports goals
                    "consistency_matters": bool # high contribution
                },
                "recommendations": {
                    "increase_frequency": bool,
                    "link_more_goals": bool,
                    "maintain_consistency": bool
                },
                "graph_context": GraphContext
            }

        Example:
            ```python
            result = await habits_intel.get_habit_goal_support("habit_1")
            analysis = result.value

            gs = analysis["goal_support"]
            print(f"Supports {gs['total_goals_supported']} goals")
            print(f"Alignment: {gs['alignment_score']}/10")

            for contrib in gs["goal_contributions"]:
                print(f" {contrib['goal_title']}: {contrib['contribution_strength']}")
            ```

        Refactoring:
        - Uses BaseAnalyticsService._analyze_entity_with_typed_context template
          (path-aware HabitCrossContext via the canonical typed reader).
        """
        # Use base class template over the CANONICAL typed (path-aware) reader.
        analysis_result = await self._analyze_entity_with_typed_context(
            uid,
            metrics_fn=calculate_habit_integration_metrics,
            recommendations_fn=habit_recommendations,
            depth=depth,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        habit = self._to_domain_model(analysis["entity"], HabitDTO, Habit)
        context: HabitCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Read UIDs off the path-aware entities.
        supporting_goal_uids = [g.uid for g in context.goals]

        # Calculate goal contributions
        consistency_score = habit.calculate_consistency_score()
        goal_contributions = [
            {
                "goal_uid": goal_uid,
                "contribution_strength": consistency_score * 2.0,  # 0-2 scale
                "estimated_impact": "high"
                if consistency_score > 0.7
                else "medium"
                if consistency_score > 0.4
                else "low",
            }
            for goal_uid in supporting_goal_uids
        ]

        # Calculate alignment score
        alignment_score = min(10.0, len(supporting_goal_uids) * 2.0 * consistency_score)

        # Identify primary goal UID (if any)
        primary_goal_uid = supporting_goal_uids[0] if supporting_goal_uids else None

        # Impact analysis from metrics
        impact_analysis = {
            "high_impact": alignment_score > 7.0,
            "goal_aligned": metrics["has_goal_connection"],
            "consistency_matters": consistency_score > 0.7,
        }

        # Recommendations dict
        recommendations = {
            "increase_frequency": consistency_score < 0.5,
            "link_more_goals": metrics["goal_support_count"] < 2,
            "maintain_consistency": consistency_score >= 0.7,
        }

        return Result.ok(
            {
                "habit": habit,
                "goal_support": {
                    "supporting_goal_uids": supporting_goal_uids,
                    "goal_contributions": goal_contributions,
                    "alignment_score": alignment_score,
                    "total_goals_supported": metrics["goal_support_count"],
                    "primary_goal_uid": primary_goal_uid,
                },
                "impact_analysis": impact_analysis,
                "recommendations": recommendations,
                "metrics": metrics,  # Include standard metrics
            }
        )

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    def _calculate_practice_effectiveness(self, habit: Habit, knowledge_count: int) -> float:
        """Calculate practice effectiveness score for knowledge reinforcement.

        Uses MetricsCalculator for consistent calculations.

        Considers:
        - Habit consistency score
        - Number of knowledge areas covered
        - Streak count (if available)

        Args:
            habit: Habit domain model
            knowledge_count: Number of knowledge areas reinforced

        Returns:
            Effectiveness score (0-10 scale)
        """
        consistency = habit.calculate_consistency_score()
        streak = habit.current_streak if habit.current_streak > 0 else 1

        # Base effectiveness from consistency (0-5 points)
        base_score = consistency * 5.0

        # Bonus for knowledge coverage (0-3 points, capped)
        knowledge_bonus = MetricsCalculator.clamp(knowledge_count * 0.5, max_val=3.0)

        # Bonus for streak (0-2 points, capped)
        streak_bonus = MetricsCalculator.clamp((streak / 30.0) * 2.0, max_val=2.0)

        return base_score + knowledge_bonus + streak_bonus

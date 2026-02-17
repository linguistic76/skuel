"""
Path-Aware Intelligence Helper - Reusable Path Analysis Utilities
===================================================================

Phase 4: Path Intelligence - Generic helper for all intelligence services.

Provides reusable methods for:
- Parsing path-aware entities from dict representations
- Filtering by path strength
- Calculating cascade impact
- Generating path-strength-based recommendations
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.graph.path_aware_types import (
        PathAwareChoice,
        PathAwareEvent,
        PathAwareGoal,
        PathAwareHabit,
        PathAwareKnowledge,
        PathAwarePrinciple,
        PathAwareTask,
    )


class PathAwareIntelligenceHelper:
    """
    Reusable helper for path-aware intelligence analysis.

    All intelligence services can use this helper to:
    1. Parse path-aware entities from backend dicts
    2. Filter entities by path strength
    3. Calculate cascade impact scores
    4. Generate recommendations based on path metadata

    Usage:
        ```python
        class ChoicesIntelligenceService(BaseAnalyticsService):
            def __init__(self, ...):
                self.path_helper = PathAwareIntelligenceHelper()

            async def analyze_choice_impact(self, choice_uid: str):
                # Parse path-aware context
                goals = [self.path_helper.parse_goal(g) for g in context_dict["goals"]]

                # Filter by strength
                strong_goals = self.path_helper.filter_by_strength(goals, min_strength=0.8)

                # Calculate cascade impact
                impact = self.path_helper.calculate_cascade_impact(goals, knowledge, principles)
        ```
    """

    # ========================================================================
    # PATH-AWARE PARSING
    # ========================================================================

    @staticmethod
    def parse_goal(goal_dict: dict) -> "PathAwareGoal":
        """Parse path-aware goal from dict representation."""
        from core.models.graph.path_aware_types import PathAwareGoal

        return PathAwareGoal(
            uid=goal_dict["uid"],
            title=goal_dict["title"],
            distance=goal_dict["distance"],
            path_strength=goal_dict["path_strength"],
            via_relationships=goal_dict["via_relationships"],
        )

    @staticmethod
    def parse_task(task_dict: dict) -> "PathAwareTask":
        """Parse path-aware task from dict representation."""
        from core.models.graph.path_aware_types import PathAwareTask

        return PathAwareTask(
            uid=task_dict["uid"],
            title=task_dict["title"],
            distance=task_dict["distance"],
            path_strength=task_dict["path_strength"],
            via_relationships=task_dict["via_relationships"],
        )

    @staticmethod
    def parse_habit(habit_dict: dict) -> "PathAwareHabit":
        """Parse path-aware habit from dict representation."""
        from core.models.graph.path_aware_types import PathAwareHabit

        return PathAwareHabit(
            uid=habit_dict["uid"],
            title=habit_dict["title"],
            distance=habit_dict["distance"],
            path_strength=habit_dict["path_strength"],
            via_relationships=habit_dict["via_relationships"],
        )

    @staticmethod
    def parse_event(event_dict: dict) -> "PathAwareEvent":
        """Parse path-aware event from dict representation."""
        from core.models.graph.path_aware_types import PathAwareEvent

        return PathAwareEvent(
            uid=event_dict["uid"],
            title=event_dict["title"],
            distance=event_dict["distance"],
            path_strength=event_dict["path_strength"],
            via_relationships=event_dict["via_relationships"],
        )

    @staticmethod
    def parse_principle(principle_dict: dict) -> "PathAwarePrinciple":
        """Parse path-aware principle from dict representation."""
        from core.models.graph.path_aware_types import PathAwarePrinciple

        return PathAwarePrinciple(
            uid=principle_dict["uid"],
            title=principle_dict["title"],
            distance=principle_dict["distance"],
            path_strength=principle_dict["path_strength"],
            via_relationships=principle_dict["via_relationships"],
        )

    @staticmethod
    def parse_choice(choice_dict: dict) -> "PathAwareChoice":
        """Parse path-aware choice from dict representation."""
        from core.models.graph.path_aware_types import PathAwareChoice

        return PathAwareChoice(
            uid=choice_dict["uid"],
            title=choice_dict["title"],
            distance=choice_dict["distance"],
            path_strength=choice_dict["path_strength"],
            via_relationships=choice_dict["via_relationships"],
        )

    @staticmethod
    def parse_knowledge(knowledge_dict: dict) -> "PathAwareKnowledge":
        """Parse path-aware knowledge from dict representation."""
        from core.models.graph.path_aware_types import PathAwareKnowledge

        return PathAwareKnowledge(
            uid=knowledge_dict["uid"],
            title=knowledge_dict["title"],
            distance=knowledge_dict["distance"],
            path_strength=knowledge_dict["path_strength"],
            via_relationships=knowledge_dict["via_relationships"],
        )

    # ========================================================================
    # PATH-STRENGTH FILTERING
    # ========================================================================

    @staticmethod
    def filter_by_strength(entities: list, min_strength: float = 0.8) -> list:
        """
        Filter entities by minimum path strength threshold.

        Args:
            entities: List of path-aware entities
            min_strength: Minimum path_strength value (0.0-1.0)

        Returns:
            Filtered list containing only entities with path_strength >= min_strength
        """
        return [e for e in entities if e.path_strength >= min_strength]

    @staticmethod
    def filter_direct_connections(entities: list) -> list:
        """
        Get only direct connections (distance = 1).

        Args:
            entities: List of path-aware entities

        Returns:
            Filtered list containing only entities with distance == 1
        """
        return [e for e in entities if e.distance == 1]

    @staticmethod
    def filter_by_max_distance(entities: list, max_distance: int) -> list:
        """
        Filter entities by maximum distance threshold.

        Args:
            entities: List of path-aware entities
            max_distance: Maximum distance (hops) allowed

        Returns:
            Filtered list containing only entities with distance <= max_distance
        """
        return [e for e in entities if e.distance <= max_distance]

    # ========================================================================
    # CASCADE IMPACT ANALYSIS
    # ========================================================================

    @staticmethod
    def calculate_cascade_impact(
        goals: list | None = None,
        tasks: list | None = None,
        habits: list | None = None,
        knowledge: list | None = None,
        principles: list | None = None,
        events: list | None = None,
    ) -> dict[str, Any]:
        """
        Calculate cascade impact using path-aware metadata.

        Computes impact scores weighted by:
        - Path strength (confidence cascade)
        - Distance (direct connections weighted higher)
        - Domain importance (principles > knowledge > goals > tasks)

        Args:
            goals: List of PathAwareGoal entities
            tasks: List of PathAwareTask entities
            habits: List of PathAwareHabit entities
            knowledge: List of PathAwareKnowledge entities
            principles: List of PathAwarePrinciple entities
            events: List of PathAwareEvent entities

        Returns:
            Dict containing:
            - total_impact: Overall weighted impact score
            - direct_impact: Impact from direct connections only
            - indirect_impact: Impact from multi-hop connections
            - domain_impacts: Breakdown by domain
            - impact_distribution: Entity counts by domain
        """
        goals = goals or []
        tasks = tasks or []
        habits = habits or []
        knowledge = knowledge or []
        principles = principles or []
        events = events or []

        # Separate direct vs indirect connections
        direct_goals = [g for g in goals if g.distance == 1]
        indirect_goals = [g for g in goals if g.distance > 1]

        direct_tasks = [t for t in tasks if t.distance == 1]
        indirect_tasks = [t for t in tasks if t.distance > 1]

        direct_habits = [h for h in habits if h.distance == 1]
        indirect_habits = [h for h in habits if h.distance > 1]

        # Calculate weighted impacts
        # Direct connections: full weight
        # Indirect connections: 50% weight penalty
        goals_direct = sum(g.path_strength for g in direct_goals)
        goals_indirect = sum(g.path_strength * 0.5 for g in indirect_goals)

        tasks_direct = sum(t.path_strength for t in direct_tasks)
        tasks_indirect = sum(t.path_strength * 0.5 for t in indirect_tasks)

        habits_direct = sum(h.path_strength for h in direct_habits)
        habits_indirect = sum(h.path_strength * 0.5 for h in indirect_habits)

        # Knowledge: weighted by distance
        knowledge_impact = sum(
            k.path_strength * (2.0 if k.distance == 1 else 1.0) for k in knowledge
        )

        # Principles: highly weighted (foundational)
        principle_impact = sum(p.path_strength * 3.0 for p in principles)

        # Events: moderate weight
        events_impact = sum(e.path_strength * (1.5 if e.distance == 1 else 0.75) for e in events)

        # Total impacts
        direct_impact = goals_direct + tasks_direct + habits_direct
        indirect_impact = goals_indirect + tasks_indirect + habits_indirect

        total_impact = (
            direct_impact + indirect_impact + knowledge_impact + principle_impact + events_impact
        )

        return {
            "total_impact": total_impact,
            "direct_impact": direct_impact,
            "indirect_impact": indirect_impact,
            "domain_impacts": {
                "goals": goals_direct + goals_indirect,
                "tasks": tasks_direct + tasks_indirect,
                "habits": habits_direct + habits_indirect,
                "knowledge": knowledge_impact,
                "principles": principle_impact,
                "events": events_impact,
            },
            "impact_distribution": {
                "goals": len(goals),
                "tasks": len(tasks),
                "habits": len(habits),
                "knowledge": len(knowledge),
                "principles": len(principles),
                "events": len(events),
            },
        }

    # ========================================================================
    # PATH-STRENGTH RECOMMENDATIONS
    # ========================================================================

    @staticmethod
    def generate_recommendations(
        goals: list | None = None,
        tasks: list | None = None,
        habits: list | None = None,
        knowledge: list | None = None,
        principles: list | None = None,
        weak_threshold: float = 0.6,
        deep_cascade_threshold: int = 3,
    ) -> list[str]:
        """
        Generate recommendations based on path strength analysis.

        Identifies potential issues:
        - Weak connections (low path_strength)
        - Missing direct relationships
        - Deep cascades (too many hops)
        - Imbalanced connection patterns

        Args:
            goals: List of PathAwareGoal entities
            tasks: List of PathAwareTask entities
            habits: List of PathAwareHabit entities
            knowledge: List of PathAwareKnowledge entities
            principles: List of PathAwarePrinciple entities
            weak_threshold: Threshold below which connections are considered weak
            deep_cascade_threshold: Distance above which cascades are considered deep

        Returns:
            List of recommendation strings
        """
        goals = goals or []
        tasks = tasks or []
        habits = habits or []
        knowledge = knowledge or []
        principles = principles or []

        recommendations = []

        # Check for weak connections
        weak_goals = [g for g in goals if g.path_strength < weak_threshold]
        if weak_goals:
            recommendations.append(
                f"Consider strengthening {len(weak_goals)} goal connections (low path confidence)"
            )

        weak_principles = [p for p in principles if p.path_strength < weak_threshold]
        if weak_principles:
            recommendations.append(
                f"Clarify alignment with {len(weak_principles)} principles (weak connection)"
            )

        weak_knowledge = [k for k in knowledge if k.path_strength < weak_threshold]
        if weak_knowledge:
            recommendations.append(
                f"Review {len(weak_knowledge)} knowledge connections (low confidence)"
            )

        # Check for missing direct connections
        direct_goals = [g for g in goals if g.distance == 1]
        if not direct_goals and goals:
            recommendations.append(
                "No direct goal connections - consider explicitly linking to goals"
            )

        direct_principles = [p for p in principles if p.distance == 1]
        if not direct_principles and principles:
            recommendations.append(
                "No direct principle connections - consider explicitly aligning with principles"
            )

        # Check for deep cascades
        max_goal_distance = max((g.distance for g in goals), default=0)
        if max_goal_distance >= deep_cascade_threshold:
            recommendations.append(
                f"Deep cascade detected ({max_goal_distance} hops to goals) - verify relationship chain"
            )

        max_task_distance = max((t.distance for t in tasks), default=0)
        if max_task_distance >= deep_cascade_threshold:
            recommendations.append(
                f"Deep task cascade ({max_task_distance} hops) - consider simplifying dependencies"
            )

        # Check for connection imbalance
        if len(goals) > 0 and len(tasks) == 0 and len(habits) == 0:
            recommendations.append(
                "Goals defined but no supporting tasks/habits - add concrete actions"
            )

        if len(principles) > 0 and len(goals) == 0:
            recommendations.append(
                "Principles defined but no aligned goals - translate values into objectives"
            )

        return recommendations

"""
PathAwareAnalyzer - Reusable Path Analysis Utilities
=====================================================

Path Intelligence - Generic analyzer for all intelligence services.

Provides reusable methods for:
- Calculating cascade impact
- Generating path-strength-based recommendations
"""

from typing import Any


class PathAwareAnalyzer:
    """
    Reusable helper for path-aware intelligence analysis.

    All intelligence services can use this helper to:
    1. Calculate cascade impact scores
    2. Generate recommendations based on path metadata

    Path-aware entities themselves are constructed by the models' ``from_dict`` /
    ``ChoiceCrossContext.from_categorized`` via the typed cross-domain reader
    (``get_cross_domain_context_typed``) — not here.

    Usage:
        ```python
        # ctx is a typed path-aware context (e.g. from get_cross_domain_context_typed):
        impact = PathAwareAnalyzer.calculate_cascade_impact(
            goals=ctx.supporting_goals,
            knowledge=ctx.knowledge,
            principles=ctx.principles,
        )
        ```
    """

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

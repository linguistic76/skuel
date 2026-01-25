"""
GraphEntity Protocol - Unified Interface for Relationship Reasoning
====================================================================

This protocol enables any entity (Goal, Habit, Task, Choice, Principle) to:
1. Explain WHY it exists (reasoning for creation)
2. Show WHAT shaped it (upstream influences)
3. Show WHAT it shapes (downstream impacts)

This creates a queryable reasoning graph across the entire system.

Includes GraphEntityBase ABC for default implementation of get_relationship_summary().
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphEntity(Protocol):
    """
    Protocol for entities that can explain their existence and relationships.

    Any domain entity implementing this protocol can participate in the
    reasoning graph, making the system comprehensible and queryable.

    Example Usage:
        def analyze_entity(entity: GraphEntity):
            print(entity.explain_existence())
            print(f"Shaped by: {entity.get_upstream_influences()}")
            print(f"Shapes: {entity.get_downstream_impacts()}")
    """

    @property
    def uid(self) -> str:
        """Unique identifier for this entity."""
        ...

    @property
    def title(self) -> str:
        """Human-readable title/name for this entity."""
        ...

    def explain_existence(self) -> str:
        """
        WHY does this entity exist? One-sentence reasoning.

        Returns a human-readable explanation that captures:
        - What choice/decision created this entity
        - What principles guide this entity
        - What system supports this entity

        Example:
            "Establish daily meditation practice. Born from: Chose to
             prioritize mental health. Guided by: small steps principle.
             Supported by system with 2 essential habits"

        Returns:
            str: One-sentence explanation of existence
        """
        ...

    def get_upstream_influences(self) -> list[dict[str, Any]]:
        """
        WHAT shaped me? Entities that influenced the creation of this entity.

        Returns entities that had a causal/guiding influence on this entity:
        - Choices that created this entity (derivations)
        - Principles that guide this entity (guidances)
        - Goals that spawned this entity (parent relationships)
        - Knowledge that prerequisite this entity

        Each dict contains:
            - uid: Entity UID
            - entity_type: "choice", "principle", "goal", "knowledge", etc.
            - relationship_type: "derives_from", "guided_by", "spawned_by", "requires"
            - reasoning: HOW/WHY this entity influenced (if available)
            - strength: 0-1 scale of influence strength (if available)

        Example:
            [
                {
                    "uid": "choice:mental-health-priority",
                    "entity_type": "choice",
                    "relationship_type": "derives_from",
                    "reasoning": "Chose to prioritize mental health",
                    "confidence": 0.9
                },
                {
                    "uid": "principle:small-steps",
                    "entity_type": "principle",
                    "relationship_type": "guided_by",
                    "manifestation": "By starting with just 2 minutes",
                    "strength": 1.0
                }
            ]

        Returns:
            List[Dict]: Upstream influencing entities with relationship details
        """
        ...

    def get_downstream_impacts(self) -> list[dict[str, Any]]:
        """
        WHAT do I shape? Entities that this entity influences/creates.

        Returns entities that are shaped by this entity:
        - Goals derived from this choice
        - Habits created to support this goal
        - Tasks spawned from this goal
        - Sub-goals created under this goal

        Each dict contains:
            - uid: Entity UID
            - entity_type: "goal", "habit", "task", etc.
            - relationship_type: "creates", "supports", "spawns", "enables"
            - reasoning: WHY this entity impacts (if available)
            - strength: 0-1 scale of impact strength (if available)

        Example:
            [
                {
                    "uid": "habit:daily-2min-meditation",
                    "entity_type": "habit",
                    "relationship_type": "essential_support",
                    "reasoning": "Essential habit for goal achievement"
                },
                {
                    "uid": "task:log-first-session",
                    "entity_type": "task",
                    "relationship_type": "spawned_from",
                    "reasoning": "First milestone task"
                }
            ]

        Returns:
            List[Dict]: Downstream impacted entities with relationship details
        """
        ...

    def get_relationship_summary(self) -> dict[str, Any]:
        """
        Get comprehensive relationship context summary.

        Combines explanation, upstream influences, and downstream impacts
        into a complete picture of this entity's place in the reasoning graph.

        Returns:
            Dict: {
                'explanation': str,  # From explain_existence()
                'upstream': List[Dict],  # From get_upstream_influences()
                'downstream': List[Dict],  # From get_downstream_impacts()
                'upstream_count': int,
                'downstream_count': int
            }
        """
        ...


@runtime_checkable
class HasGuidances(Protocol):
    """
    Protocol for entities that have principle guidances.

    Entities implementing this can be guided by principles with
    explicit manifestations and strength ratings.
    """

    @property
    def guidances(self) -> tuple[Any, ...]:
        """Tuple of Guidance objects showing HOW principles guide this entity."""
        ...

    def get_strong_guidances(self) -> list[Any]:
        """Get guidances with strength >= 0.7."""
        ...

    def get_guidance_manifestations(self) -> list[str]:
        """Get list of HOW manifestations from guidances."""
        ...


@runtime_checkable
class HasDerivation(Protocol):
    """
    Protocol for entities that have a choice derivation.

    Entities implementing this were created by an explicit choice
    with reasoning and confidence rating.
    """

    @property
    def derivation(self) -> Any | None:
        """Optional Derivation object showing WHY a choice created this entity."""
        ...

    def has_clear_derivation(self) -> bool:
        """Check if this entity has explicit reasoning for its creation."""
        ...


@runtime_checkable
class HasHabitSystem(Protocol):
    """
    Protocol for entities supported by a habit system.

    Entities implementing this have habits at different essentiality
    levels (essential, critical, supporting, optional).
    """

    def has_habit_system(self) -> bool:
        """Check if this entity has any supporting habits."""
        ...

    def get_all_habit_uids(self) -> list[str]:
        """Get all habit UIDs across all essentiality levels."""
        ...

    def calculate_system_strength(
        self, habit_success_rates: dict[str, float] | None = None
    ) -> float:
        """Calculate 0-1 strength score of the habit system."""
        ...


# Type alias for entities that implement full relationship context
GraphEntityWithContext = GraphEntity


# ============================================================================
# GraphEntityBase - Default Implementation (merged from graph_entity_base.py)
# ============================================================================


class GraphEntityBase(ABC):
    """
    Base implementation for GraphEntity protocol.

    Provides default implementation of get_relationship_summary() that works
    for all domains by delegating to abstract methods.

    Subclasses must implement:
    - explain_existence() -> str
    - get_upstream_influences() -> list[dict]
    - get_downstream_impacts() -> list[dict]
    - _get_domain_metrics() -> dict (domain-specific metrics)
    """

    @abstractmethod
    def explain_existence(self) -> str:
        """WHY does this entity exist? One-sentence reasoning."""
        ...

    @abstractmethod
    def get_upstream_influences(self) -> list[dict[str, Any]]:
        """WHAT shaped this entity? Upstream influences."""
        ...

    @abstractmethod
    def get_downstream_impacts(self) -> list[dict[str, Any]]:
        """WHAT does this entity shape? Downstream impacts."""
        ...

    @abstractmethod
    def _get_domain_metrics(self) -> dict[str, Any]:
        """
        Domain-specific metrics.

        Each domain implements this to provide metrics relevant to that domain.
        E.g., Goal provides goal_metrics, Knowledge provides knowledge_metrics.
        """
        ...

    def get_relationship_summary(self) -> dict[str, Any]:
        """
        Get comprehensive relationship context.

        DEFAULT IMPLEMENTATION - works for all domains.
        Subclasses should NOT override this unless truly necessary.

        Returns:
            Dict containing:
            - explanation: Why this entity exists
            - upstream: What shaped it
            - downstream: What it shapes
            - upstream_count: Number of upstream influences
            - downstream_count: Number of downstream impacts
            - metrics: Domain-specific metrics
        """
        return {
            "explanation": self.explain_existence(),
            "upstream": self.get_upstream_influences(),
            "downstream": self.get_downstream_impacts(),
            "upstream_count": len(self.get_upstream_influences()),
            "downstream_count": len(self.get_downstream_impacts()),
            "metrics": self._get_domain_metrics(),
        }


__all__ = [
    "GraphEntity",
    "GraphEntityBase",
    "GraphEntityWithContext",
    "HasDerivation",
    "HasGuidances",
    "HasHabitSystem",
]

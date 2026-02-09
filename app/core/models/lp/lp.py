"""
Learning Domain Model (Tier 3 - Core)
=====================================

Immutable domain model for learning paths and steps.
Contains business logic for learning progression.

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for learning path traversal
- Phase 2: Domain Intelligence models for learning analytics
- Phase 3: GraphContext for path visualization
- Phase 4: Cross-domain practice opportunities
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .lp_dto import LpDTO

from core.constants import GraphDepth
from core.models.enums import Domain

# Import Ls from authoritative source (ls module)
# Ls (Learning Step) is a cluster of Knowledge Units (ku:*)
from core.models.ls import Ls
from core.models.query import QueryIntent

# Phase 1: Query Infrastructure
from core.models.query.graph_traversal import build_graph_context_query


class LpType(str, Enum):
    """Types of learning paths."""

    STRUCTURED = "structured"  # Pre-defined sequence
    ADAPTIVE = "adaptive"  # Adjusts based on progress
    EXPLORATORY = "exploratory"  # Open-ended discovery
    REMEDIAL = "remedial"  # Address gaps
    ACCELERATED = "accelerated"  # Fast track


@dataclass(frozen=True)
class Lp:
    """
    Immutable domain model for a Learning Path.

    Contains business logic for learning progression and path management.

    Naming Convention (matches Ku, Ls):
    - Class name 'Lp' matches module path 'core.models.lp' and UID prefix 'lp'
    - Follows SKUEL's three-tier curriculum architecture: Ku, Ls, Lp
    """

    # Identity
    uid: str
    name: str
    goal: str  # What the learner will achieve
    domain: Domain

    # Configuration
    path_type: LpType = LpType.STRUCTURED
    difficulty: str = "intermediate"

    # Steps (immutable) - composed of Ls entities
    steps: tuple["Ls", ...] = ()

    # Metadata
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    created_by: str | None = None

    # Requirements and outcomes
    # Graph relationship: (lp)-[:REQUIRES_KNOWLEDGE]->(ku)
    outcomes: tuple[str, ...] = ()  # Learning outcomes (text strings, not UIDs)

    # Time estimates
    estimated_hours: float = 0.0

    # Milestone Events (curriculum calendar integration) - GRAPH-NATIVE
    # Graph relationship: (lp)-[:HAS_MILESTONE_EVENT]->(event)
    checkpoint_week_intervals: tuple[
        int, ...
    ] = ()  # Weeks for checkpoint reviews (e.g., (2, 4, 6))

    # Motivational Integration (goals and principles drive curriculum) - GRAPH-NATIVE
    # Graph relationship: (lp)-[:ALIGNED_WITH_GOAL]->(goal)
    # Graph relationship: (lp)-[:EMBODIES_PRINCIPLE]->(principle)

    # Rich context storage
    metadata: dict[str, Any] = None  # type: ignore[assignment]  # Rich context storage (graph neighborhoods, etc.)

    def __post_init__(self) -> None:
        """Set defaults and calculate derived fields."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

        # Calculate total estimated hours if not set
        if self.estimated_hours == 0.0 and self.steps:
            total_hours = sum(step.estimated_hours for step in self.steps)
            object.__setattr__(self, "estimated_hours", total_hours)

    # ==========================================================================
    # CONVERSIONS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: "LpDTO") -> "Lp":
        """
        Create immutable Lp from mutable DTO.

        All 14 business fields are copied — lossless round-trip with to_dto().
        Steps are NOT transferred (populated separately from graph relationships).
        """
        return cls(
            uid=dto.uid,
            name=dto.name,
            goal=dto.goal,
            domain=dto.domain,
            path_type=dto.path_type if isinstance(dto.path_type, LpType) else LpType(dto.path_type),
            difficulty=dto.difficulty,
            steps=(),  # Steps come from HAS_STEP relationships, not DTO
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            created_by=dto.created_by,
            outcomes=tuple(dto.outcomes),
            estimated_hours=dto.estimated_hours,
            checkpoint_week_intervals=tuple(dto.checkpoint_week_intervals),
            metadata=dto.metadata or {},
        )

    def to_dto(self) -> "LpDTO":
        """
        Convert to mutable DTO for updates.

        All 14 business fields are copied — lossless round-trip with from_dto().
        Steps are NOT transferred (relationship data, not node property).
        """
        from .lp_dto import LpDTO

        return LpDTO(
            uid=self.uid,
            name=self.name,
            goal=self.goal,
            domain=self.domain,
            path_type=self.path_type,
            difficulty=self.difficulty,
            created_at=self.created_at,
            updated_at=self.updated_at,
            created_by=self.created_by,
            outcomes=list(self.outcomes),
            estimated_hours=self.estimated_hours,
            checkpoint_week_intervals=list(self.checkpoint_week_intervals),
            metadata=dict(self.metadata) if self.metadata else {},
        )

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # LP implements KnowledgeCarrier and CurriculumCarrier.
    # LP IS curriculum - it always returns full relevance.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        LP IS curriculum - always returns 1.0.

        Returns:
            1.0 (maximum relevance - LP is a curriculum path)
        """
        return 1.0

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity carries.

        LP aggregates knowledge from all steps (LS entities).
        Converts the set from get_all_knowledge_uids() to tuple.

        Returns:
            tuple of ku-prefixed UIDs from all steps
        """
        return tuple(self.get_all_knowledge_uids())

    # ==========================================================================
    # BUSINESS LOGIC METHODS
    # ==========================================================================

    def get_next_step(self, completed_step_uids: set[str]) -> Ls | None:
        """
        Get the next uncompleted step in the path.

        Note: Readiness check not performed - requires graph query via
        LsRelationshipService.is_ready() at service layer.
        """
        for step in self.steps:
            if step.uid not in completed_step_uids:
                return step
        return None

    def calculate_progress(self) -> float:
        """Calculate overall path progress (0.0-1.0)."""
        if not self.steps:
            return 0.0

        completed_count = sum(1 for step in self.steps if step.completed)
        return completed_count / len(self.steps)

    def calculate_mastery(self) -> float:
        """Calculate average mastery across all steps."""
        if not self.steps:
            return 0.0

        total_mastery = sum(step.current_mastery for step in self.steps)
        return total_mastery / len(self.steps)

    def get_completed_steps(self) -> tuple[Ls, ...]:
        """Get all completed steps."""
        return tuple(step for step in self.steps if step.completed)

    def get_remaining_steps(self) -> tuple[Ls, ...]:
        """Get all incomplete steps."""
        return tuple(step for step in self.steps if not step.completed)

    def is_complete(self) -> bool:
        """Check if all steps are completed."""
        return all(step.completed for step in self.steps)

    def is_mastered(self) -> bool:
        """Check if all steps meet mastery threshold."""
        return all(step.is_mastered() for step in self.steps)

    def estimate_remaining_hours(self) -> float:
        """Estimate hours needed to complete path."""
        return sum(step.estimated_hours for step in self.steps if not step.completed)

    def is_adaptive(self) -> bool:
        """Check if this is an adaptive path."""
        return self.path_type == LpType.ADAPTIVE

    def is_remedial(self) -> bool:
        """Check if this is a remedial path."""
        return self.path_type == LpType.REMEDIAL

    # ==========================================================================
    # KNOWLEDGE AGGREGATION (lp aggregates ls, which aggregate ku)
    # ==========================================================================

    def get_all_knowledge_uids(self) -> set[str]:
        """
        Get all knowledge UIDs across all learning steps in this path.

        Returns:
            Set of all ku: UIDs used in this learning path
        """
        all_uids: set[str] = set()
        for step in self.steps:
            all_uids.update(step.primary_knowledge_uids)
            all_uids.update(step.supporting_knowledge_uids)
        return all_uids

    def get_primary_knowledge_uids(self) -> set[str]:
        """Get only primary (core) knowledge UIDs from all steps."""
        all_uids: set[str] = set()
        for step in self.steps:
            all_uids.update(step.primary_knowledge_uids)
        return all_uids

    def get_supporting_knowledge_uids(self) -> set[str]:
        """Get only supporting (optional) knowledge UIDs from all steps."""
        all_uids: set[str] = set()
        for step in self.steps:
            all_uids.update(step.supporting_knowledge_uids)
        return all_uids

    def knowledge_count(self) -> int:
        """Count total unique knowledge units in this path."""
        return len(self.get_all_knowledge_uids())

    def knowledge_complexity_score(self) -> float:
        """
        Calculate overall knowledge complexity of this learning path.

        Aggregates effort scores from all steps.

        Returns:
            Average complexity score (1-10 scale)
        """
        if not self.steps:
            return 0.0
        total_effort = sum(step.get_effort_score() for step in self.steps)
        return total_effort / len(self.steps)

    def practice_coverage_score(self) -> float:
        """
        Calculate how well this path provides practice opportunities.

        Returns:
            Average practice completeness across all steps (0.0-1.0)
        """
        if not self.steps:
            return 0.0
        total_practice = sum(step.practice_completeness_score() for step in self.steps)
        return total_practice / len(self.steps)

    def get_knowledge_scope_summary(self) -> dict:
        """
        Get comprehensive summary of knowledge scope in this path.

        Returns:
            Dictionary with knowledge metrics and breakdown
        """
        return {
            "total_unique_knowledge_units": self.knowledge_count(),
            "primary_knowledge_count": len(self.get_primary_knowledge_uids()),
            "supporting_knowledge_count": len(self.get_supporting_knowledge_uids()),
            "total_steps": len(self.steps),
            "knowledge_per_step_avg": self.knowledge_count() / len(self.steps) if self.steps else 0,
            "complexity_score": self.knowledge_complexity_score(),
            "practice_coverage": self.practice_coverage_score(),
            "estimated_hours": self.estimated_hours,
        }

    # ==========================================================================
    # MILESTONE EVENTS (curriculum calendar integration)
    # ==========================================================================

    def has_milestone_events(self) -> bool:
        """
        Check if path has milestone events scheduled.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual count.
        Query: COUNT (lp)-[:HAS_MILESTONE_EVENT]->() > 0
        Service: LearningPathRelationshipService.has_milestone_events(lp_uid)
        """
        return False  # Placeholder - use service layer

    def has_checkpoint_schedule(self) -> bool:
        """Check if path has checkpoint review schedule."""
        return len(self.checkpoint_week_intervals) > 0

    def get_checkpoint_count(self) -> int:
        """Get number of checkpoint reviews scheduled."""
        return len(self.checkpoint_week_intervals)

    def should_have_checkpoint_at_week(self, week: int) -> bool:
        """Check if a checkpoint review is scheduled for given week."""
        return week in self.checkpoint_week_intervals

    def get_next_checkpoint_week(self, current_week: int) -> int | None:
        """Get the next checkpoint week after current week."""
        future_checkpoints = [w for w in self.checkpoint_week_intervals if w > current_week]
        return min(future_checkpoints) if future_checkpoints else None

    def calculate_curriculum_weeks(self) -> int:
        """
        Calculate total curriculum weeks based on estimated hours.

        Assumes 10 hours per week of study time.
        """
        if self.estimated_hours == 0:
            return 0
        return max(1, int(self.estimated_hours / 10))

    def suggest_checkpoint_schedule(self, weeks_interval: int = 2) -> tuple[int, ...]:
        """
        Suggest checkpoint review schedule for this path.

        Args:
            weeks_interval: Interval between checkpoints (default: every 2 weeks)

        Returns:
            Suggested week numbers for checkpoints
        """
        total_weeks = self.calculate_curriculum_weeks()
        if total_weeks <= weeks_interval:
            return ()  # Too short for checkpoints

        checkpoints = []
        current = weeks_interval
        while current < total_weeks:
            checkpoints.append(current)
            current += weeks_interval

        return tuple(checkpoints)

    def get_milestone_summary(self) -> dict:
        """
        Get summary of milestone and checkpoint configuration.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for milestone events.
        Query: MATCH (lp)-[:HAS_MILESTONE_EVENT]->(event) RETURN event.uid
        Service: LearningPathRelationshipService.get_milestone_events(lp_uid)
        """
        return {
            "has_milestones": self.has_milestone_events(),
            "milestone_event_count": 0,  # Placeholder - use service layer
            "milestone_events": [],  # Placeholder - use service layer
            "has_checkpoints": self.has_checkpoint_schedule(),
            "checkpoint_count": self.get_checkpoint_count(),
            "checkpoint_weeks": list(self.checkpoint_week_intervals),
            "total_curriculum_weeks": self.calculate_curriculum_weeks(),
            "suggested_checkpoints": list(self.suggest_checkpoint_schedule()),
        }

    # ==========================================================================
    # MOTIVATIONAL INTEGRATION (goals & principles drive curriculum)
    # ==========================================================================

    def supports_goals(self) -> bool:
        """
        Check if path explicitly supports user goals.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual count.
        Query: COUNT (lp)-[:ALIGNED_WITH_GOAL]->() > 0
        Service: LearningPathRelationshipService.supports_goals(lp_uid)
        """
        return False  # Placeholder - use service layer

    def embodies_principles(self) -> bool:
        """
        Check if path teaches/practices specific principles.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual count.
        Query: COUNT (lp)-[:EMBODIES_PRINCIPLE]->() > 0
        Service: LearningPathRelationshipService.embodies_principles(lp_uid)
        """
        return False  # Placeholder - use service layer

    def is_goal_driven(self) -> bool:
        """Check if path is motivated by specific goals."""
        return self.supports_goals()

    def is_principle_driven(self) -> bool:
        """Check if path is motivated by specific principles."""
        return self.embodies_principles()

    def has_motivational_alignment(self) -> bool:
        """Check if path has clear motivational alignment (goals or principles)."""
        return self.supports_goals() or self.embodies_principles()

    def get_motivational_context(self) -> dict:
        """
        Get motivational context for this learning path.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for aligned goals and principles.
        Query: MATCH (lp)-[:ALIGNED_WITH_GOAL]->(g), (lp)-[:EMBODIES_PRINCIPLE]->(p)
        Service: LearningPathRelationshipService.get_motivational_context(lp_uid)

        Returns:
            Dictionary with goals and principles alignment
        """
        return {
            "supports_goals": self.supports_goals(),
            "aligned_goals": [],  # Placeholder - use service layer
            "goal_count": 0,  # Placeholder - use service layer
            "embodies_principles": self.embodies_principles(),
            "embodied_principles": [],  # Placeholder - use service layer
            "principle_count": 0,  # Placeholder - use service layer
            "has_motivational_alignment": self.has_motivational_alignment(),
            "motivational_strength": self.calculate_motivational_strength(),
        }

    def calculate_motivational_strength(self) -> float:
        """
        Calculate motivational strength of this path (0-1).

        GRAPH-NATIVE PLACEHOLDER: Use service layer for aligned goals/principles count.
        Query: MATCH (lp)-[:ALIGNED_WITH_GOAL]->(g) RETURN count(g)
        Query: MATCH (lp)-[:EMBODIES_PRINCIPLE]->(p) RETURN count(p)
        Service: LearningPathRelationshipService.calculate_motivational_strength(lp_uid)

        Paths with clear goal and principle alignment are more motivating.
        """
        return 0.0  # Placeholder - use service layer

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_path_query(self, depth: int | None = None) -> str:
        """
        Build pure Cypher query for complete learning path

        Uses QueryIntent.HIERARCHICAL to follow the structured learning
        path relationships between knowledge units.

        Args:
            depth: Maximum depth (defaults to number of steps)

        Returns:
            Pure Cypher query string
        """
        if depth is None:
            depth = len(self.steps) if self.steps else 5

        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.HIERARCHICAL, depth=depth
        )

    def build_prerequisite_query(self, depth: int = 5) -> str:
        """
        Build pure Cypher query for all prerequisites

        Finds all knowledge that must be mastered before starting this path.

        Args:
            depth: Maximum prerequisite depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PREREQUISITE, depth=depth
        )

    def build_practice_query(self) -> str:
        """
        Build pure Cypher query for practice opportunities

        Finds tasks and events for practicing knowledge in this path.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PRACTICE, depth=GraphDepth.NEIGHBORHOOD
        )

    def get_path_query_intent(self) -> QueryIntent:
        """
        Get appropriate QueryIntent for this learning path.

        Business rules:
        - STRUCTURED paths → HIERARCHICAL (follow sequence)
        - ADAPTIVE paths → RELATIONSHIP (explore connections)
        - EXPLORATORY paths → EXPLORATORY (discover)
        - REMEDIAL paths → PREREQUISITE (fill gaps)
        - ACCELERATED paths → SPECIFIC (targeted learning)

        Returns:
            Recommended QueryIntent for this path type
        """
        intent_mapping = {
            LpType.STRUCTURED: QueryIntent.HIERARCHICAL,
            LpType.ADAPTIVE: QueryIntent.RELATIONSHIP,
            LpType.EXPLORATORY: QueryIntent.EXPLORATORY,
            LpType.REMEDIAL: QueryIntent.PREREQUISITE,
            LpType.ACCELERATED: QueryIntent.SPECIFIC,
        }
        return intent_mapping.get(self.path_type, QueryIntent.HIERARCHICAL)

    # ==========================================================================
    # PHASE 2: GRAPHENTITY PROTOCOL IMPLEMENTATION
    # ==========================================================================

    def explain_existence(self) -> str:
        """
        WHY does this learning path exist? One-sentence reasoning.

        Returns:
            Human-readable explanation of learning path's purpose and context
        """
        parts = [self.name]

        # Learning goal
        parts.append(f"Goal: {self.goal}")

        # Path type and domain
        parts.append(f"{self.path_type.value} path in {self.domain.value}")

        # Scope
        if self.steps:
            parts.append(f"{len(self.steps)} step(s), ~{self.estimated_hours}h total")

        # Progress indicator
        if self.is_complete():
            parts.append("Completed")
        else:
            progress_pct = int(self.calculate_progress() * 100)
            if progress_pct > 0:
                parts.append(f"{progress_pct}% complete")

        # Aligned goals (GRAPH-NATIVE PLACEHOLDER)
        # Query: COUNT (lp)-[:ALIGNED_WITH_GOAL]->()
        # Use service layer: LearningPathRelationshipService.get_aligned_goals(lp_uid)

        # Embodied principles (GRAPH-NATIVE PLACEHOLDER)
        # Query: COUNT (lp)-[:EMBODIES_PRINCIPLE]->()
        # Use service layer: LearningPathRelationshipService.get_embodied_principles(lp_uid)

        return ". ".join(parts)

    def get_upstream_influences(self) -> list[dict]:
        """
        WHAT shaped this learning path? Entities that influenced its creation.

        Returns:
            List of dicts representing upstream influences:
            - Aligned goals that need this path
            - Embodied principles taught in path
            - Prerequisite knowledge assumed
            - Domain context
        """
        influences = []

        # GRAPH-NATIVE PLACEHOLDER: Use service layer for aligned goals, principles, prerequisites
        # 1. Aligned goals (why this path exists)
        # Query: MATCH (lp)-[:ALIGNED_WITH_GOAL]->(g) RETURN g.uid
        # Service: LearningPathRelationshipService.get_aligned_goals(lp_uid)

        # 2. Embodied principles (values taught in path)
        # Query: MATCH (lp)-[:EMBODIES_PRINCIPLE]->(p) RETURN p.uid
        # Service: LearningPathRelationshipService.get_embodied_principles(lp_uid)

        # 3. Prerequisite knowledge (assumed starting point)
        # Query: MATCH (lp)-[:REQUIRES_KNOWLEDGE]->(ku) RETURN ku.uid
        # Service: LearningPathRelationshipService.get_prerequisites(lp_uid)

        # 4. Domain context
        influences.append(
            {
                "uid": f"domain:{self.domain.value}",
                "entity_type": "domain",
                "relationship_type": "categorized_by",
                "reasoning": f"Learning path belongs to {self.domain.value} domain",
                "strength": 1.0,
            }
        )

        # 5. Path type influence
        influences.append(
            {
                "uid": f"path_type:{self.path_type.value}",
                "entity_type": "path_type",
                "relationship_type": "structured_as",
                "reasoning": f"Path follows {self.path_type.value} learning approach",
                "strength": 0.8,
            }
        )

        return influences

    def get_downstream_impacts(self) -> list[dict]:
        """
        WHAT does this learning path shape? Entities influenced by this path.

        Returns:
            List of dicts representing downstream impacts:
            - Learning steps in sequence
            - Knowledge outcomes
            - Milestone events
            - Goals advanced by completing path
        """
        impacts = []

        # 1. Learning steps (sequential components)
        impacts.extend(
            [
                {
                    "uid": step.uid,
                    "entity_type": "learning_step",
                    "relationship_type": "contains",
                    "reasoning": f"Step #{step.sequence if step.sequence else '?'} in learning sequence",
                    "strength": 1.0,
                    "sequence": step.sequence,
                    "completed": step.completed,
                    "mastery": step.current_mastery,
                }
                for step in self.steps
            ]
        )

        # 2. Knowledge outcomes (what learner will know)
        impacts.extend(
            [
                {
                    "uid": f"outcome:{self.uid}:{outcome[:20]}",
                    "entity_type": "learning_outcome",
                    "relationship_type": "produces",
                    "reasoning": f"Learning outcome: {outcome}",
                    "strength": 1.0,
                }
                for outcome in self.outcomes
            ]
        )

        # GRAPH-NATIVE PLACEHOLDER: Use service layer for milestone events and aligned goals
        # 3. Milestone events (checkpoints and celebrations)
        # Query: MATCH (lp)-[:HAS_MILESTONE_EVENT]->(e) RETURN e.uid
        # Service: LearningPathRelationshipService.get_milestone_events(lp_uid)

        # 4. Goals advanced by path completion
        # Query: MATCH (lp)-[:ALIGNED_WITH_GOAL]->(g) RETURN g.uid
        # Service: LearningPathRelationshipService.get_aligned_goals(lp_uid)

        # 5. Checkpoint intervals (temporal milestones)
        impacts.extend(
            [
                {
                    "uid": f"checkpoint:{self.uid}:week{week_num}",
                    "entity_type": "checkpoint",
                    "relationship_type": "creates",
                    "reasoning": f"Week {week_num} checkpoint review",
                    "strength": 0.7,
                    "week": week_num,
                }
                for week_num in self.checkpoint_week_intervals
            ]
        )

        return impacts

    def get_relationship_summary(self) -> dict:
        """
        Get comprehensive relationship context for this learning path.

        Returns:
            Dict containing:
            - explanation: Why this path exists
            - upstream: What shaped it
            - downstream: What it shapes
            - upstream_count: Number of upstream influences
            - downstream_count: Number of downstream impacts
            - path_metrics: Progress, mastery, completion status
        """
        return {
            "explanation": self.explain_existence(),
            "upstream": self.get_upstream_influences(),
            "downstream": self.get_downstream_impacts(),
            "upstream_count": len(self.get_upstream_influences()),
            "downstream_count": len(self.get_downstream_impacts()),
            "path_metrics": {
                "name": self.name,
                "goal": self.goal,
                "domain": self.domain.value,
                "path_type": self.path_type.value,
                "difficulty": self.difficulty,
                "total_steps": len(self.steps),
                "completed_steps": len(self.get_completed_steps()),
                "remaining_steps": len(self.get_remaining_steps()),
                "progress_percentage": self.calculate_progress() * 100,
                "average_mastery": self.calculate_mastery(),
                "is_complete": self.is_complete(),
                "is_mastered": self.is_mastered(),
                "estimated_hours": self.estimated_hours,
                "remaining_hours": self.estimate_remaining_hours(),
                "has_prerequisites": False,  # Placeholder - use service layer
                "prerequisite_count": 0,  # Placeholder - use service layer
                "outcome_count": len(self.outcomes),
                "aligned_goal_count": 0,  # Placeholder - use service layer
                "embodied_principle_count": 0,  # Placeholder - use service layer
                "milestone_event_count": 0,  # Placeholder - use service layer
                "checkpoint_count": len(self.checkpoint_week_intervals),
            },
        }


# Backward compatibility alias
LearningPath = Lp

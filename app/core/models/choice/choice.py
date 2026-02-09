"""
Choice Domain Model (Tier 3 - Core)
====================================

Immutable domain model for choices and decision-making.
Contains business logic for choice evaluation and decision optimization.

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for decision context and impact analysis
- Phase 3: GraphContext for cross-domain choice intelligence
- Phase 4: QueryIntent selection for choice-specific patterns
"""

from __future__ import annotations

from core.constants import GraphDepth

__version__ = "2.1"  # Updated for Phase 1-4 integration

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from operator import itemgetter
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.enums import Domain, Priority
from core.models.mixins import StatusChecksMixin
from core.models.query import QueryIntent

# Phase 1: Query Infrastructure
from core.models.query.graph_traversal import build_graph_context_query

if TYPE_CHECKING:
    from core.models.choice.choice_dto import ChoiceDTO


class ChoiceStatus(str, Enum):
    """Status of a choice/decision."""

    PENDING = "pending"  # Choice not yet made
    DECIDED = "decided"  # Choice made
    IMPLEMENTED = "implemented"  # Choice put into action
    EVALUATED = "evaluated"  # Outcome assessed
    ARCHIVED = "archived"  # Historical record


class ChoiceType(str, Enum):
    """Types of choices."""

    BINARY = "binary"  # Yes/No choice
    MULTIPLE = "multiple"  # Select from options
    RANKING = "ranking"  # Order preferences
    ALLOCATION = "allocation"  # Distribute resources
    STRATEGIC = "strategic"  # Long-term direction
    OPERATIONAL = "operational"  # Day-to-day decisions


@dataclass(frozen=True)
class ChoiceOption:
    """
    An individual option within a choice.

    Represents one possible path of action.
    """

    # Identity
    uid: str
    title: str
    description: str

    # Evaluation
    feasibility_score: float = 0.5  # 0-1 scale
    risk_level: float = 0.5  # 0-1 scale (higher = riskier)
    potential_impact: float = 0.5  # 0-1 scale
    resource_requirement: float = 0.5  # 0-1 scale

    # Metadata
    estimated_duration: int | None = None  # Minutes/hours
    dependencies: tuple[str, ...] = ()  # Other choice/task UIDs
    tags: tuple[str, ...] = ()

    def calculate_option_score(self, user_preferences: dict[str, float]) -> float:
        """Calculate weighted score based on user preferences."""
        weights = {
            "feasibility": user_preferences.get("feasibility_weight", 0.3),
            "impact": user_preferences.get("impact_weight", 0.4),
            "risk": user_preferences.get("risk_weight", 0.2),
            "resources": user_preferences.get("resource_weight", 0.1),
        }

        # Risk is inverse (lower risk = better)
        risk_score = 1.0 - self.risk_level

        return (
            self.feasibility_score * weights["feasibility"]
            + self.potential_impact * weights["impact"]
            + risk_score * weights["risk"]
            + (1.0 - self.resource_requirement) * weights["resources"]
        )

    def is_feasible(self, threshold: float = 0.6) -> bool:
        """Check if option meets feasibility threshold."""
        return self.feasibility_score >= threshold


@dataclass(frozen=True)
class Choice(StatusChecksMixin):
    """
    Immutable domain model for a choice/decision.

    Contains business logic for choice evaluation and outcome tracking.

    RELATIONSHIP ARCHITECTURE:

    Choices exist as decision nodes that both receive influence and create impact:
    - Upstream: Principles (alignment), Knowledge (informed by), Goals (motivated by)
    - Downstream: Goals (derivation), Habits (inspired creation), Tasks (action items)

    Use ChoiceService to query these relationships - domain models define structure,
    services provide graph-native operations.
    """

    # Identity
    uid: str
    title: str
    description: str
    user_uid: str

    # Choice Configuration
    choice_type: ChoiceType = ChoiceType.MULTIPLE
    status: ChoiceStatus = ChoiceStatus.PENDING
    priority: Priority = Priority.MEDIUM
    domain: Domain = Domain.PERSONAL

    # Options and Decision
    options: tuple[ChoiceOption, ...] = ()  # Empty tuple, not nested ((),)
    selected_option_uid: str | None = None
    decision_rationale: str | None = None

    # Context
    decision_criteria: tuple[str, ...] = ()  # What factors matter,
    constraints: tuple[str, ...] = ()  # Limitations to consider
    stakeholders: tuple[str, ...] = ()  # Who is affected

    # Curriculum Integration (NEW - choice as inspiration engine) - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (choice)-[:INFORMED_BY_KNOWLEDGE]->(ku)
    # Graph relationship: (choice)-[:OPENS_LEARNING_PATH]->(lp)
    # Graph relationship: (choice)-[:REQUIRES_KNOWLEDGE_FOR_DECISION]->(ku)
    # Graph relationship: (choice)-[:ALIGNED_WITH_PRINCIPLE]->(principle)

    # Inspiration & Possibility
    inspiration_type: str | None = (
        None  # 'career_path', 'life_direction', 'skill_acquisition', 'project_idea'
    )
    expands_possibilities: bool = False  # True if choice opens new opportunities,
    vision_statement: str | None = None  # Future vision this choice enables

    # Timing
    decision_deadline: datetime | None = None  # type: ignore[assignment]
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    decided_at: datetime | None = None  # type: ignore[assignment]

    # Outcome Tracking
    satisfaction_score: int | None = None  # 1-5 scale post-decision,
    actual_outcome: str | None = None
    lessons_learned: tuple[str, ...] = ()
    metadata: dict[str, Any] = None  # type: ignore[assignment]  # Rich context storage (graph neighborhoods, etc.)

    # StatusChecksMixin configuration
    # Choice uses ChoiceStatus - DECIDED, IMPLEMENTED, EVALUATED are all "completed" states
    _completed_statuses: ClassVar[tuple[ChoiceStatus, ...]] = (
        ChoiceStatus.DECIDED,
        ChoiceStatus.IMPLEMENTED,
        ChoiceStatus.EVALUATED,
    )
    _cancelled_statuses: ClassVar[tuple[ChoiceStatus, ...]] = ()  # No cancelled state
    _terminal_statuses: ClassVar[tuple[ChoiceStatus, ...]] = (
        ChoiceStatus.EVALUATED,
        ChoiceStatus.ARCHIVED,
    )
    _active_statuses: ClassVar[tuple[ChoiceStatus, ...]] = (
        ChoiceStatus.PENDING,
        ChoiceStatus.DECIDED,
        ChoiceStatus.IMPLEMENTED,
    )

    def __post_init__(self) -> None:
        """Set defaults and validate."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # Choice implements KnowledgeCarrier and ActivityCarrier.
    # Choice is INFORMED BY knowledge - relevance based on knowledge connections.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        Choice relevance based on knowledge connections for informed decisions.

        Returns:
            0.0-1.0 based on knowledge integration
        """
        score = 0.0

        # Strategic choice (likely knowledge-informed)
        if self.choice_type == ChoiceType.STRATEGIC:
            score = 0.5

        # Expands possibilities (opens learning paths)
        if self.expands_possibilities:
            score = max(score, 0.6)

        # Has vision statement (long-term knowledge impact)
        if self.vision_statement:
            score = max(score, 0.4)

        # Inspiration type suggests curriculum integration
        if self.inspiration_type in (
            "career_path",
            "skill_acquisition",
            "life_direction",
        ):
            score = max(score, 0.7)

        return score

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity is informed by.

        Choice knowledge is stored as graph relationships.
        This is a GRAPH-NATIVE placeholder - actual data requires service layer.

        Use service.relationships.get_choice_knowledge(choice_uid) for real data.

        Returns:
            Empty tuple (placeholder - actual KU UIDs via graph query)
        """
        # GRAPH-NATIVE: Real implementation requires service layer query
        # Query: MATCH (choice)-[:INFORMED_BY_KNOWLEDGE]->(ku) RETURN ku.uid
        return ()

    def learning_impact_score(self) -> float:
        """
        Calculate learning impact when this choice is decided.

        Choices contribute to KU substance through informed decision-making.

        Returns:
            Impact score 0.0-1.0
        """
        score = 0.0

        # Strategic choices have high knowledge impact
        if self.choice_type == ChoiceType.STRATEGIC:
            score += 0.3

        # Opens new possibilities
        if self.expands_possibilities:
            score += 0.3

        # Evaluated outcome (learning from decisions)
        if self.status == ChoiceStatus.EVALUATED:
            score += 0.2

        # Has lessons learned
        if self.lessons_learned:
            score += len(self.lessons_learned) * 0.05  # Max 0.2

        return min(1.0, score)

    # ==========================================================================
    # DTO CONVERSION - THREE-TIER ARCHITECTURE
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: ChoiceDTO) -> Choice:
        """
        Create immutable Choice from mutable ChoiceDTO.

        This method maintains consistency with the three-tier architecture
        pattern used across all SKUEL domains.

        Args:
            dto: ChoiceDTO instance (mutable, from database/API layer)

        Returns:
            Immutable Choice domain model

        Note:
            Internally delegates to choice_dto_to_domain converter function.
            This class method exists to satisfy DomainModelProtocol for
            type-safe generic operations (UniversalNeo4jBackend, BaseService).

        Example:
            dto = ChoiceDTO.from_dict(data)
            choice = Choice.from_dto(dto)
        """
        from core.models.choice.choice_converters import choice_dto_to_domain

        return choice_dto_to_domain(dto)

    def to_dto(self) -> ChoiceDTO:
        """
        Convert immutable Choice to mutable ChoiceDTO.

        Used for database operations and API serialization.

        Returns:
            Mutable ChoiceDTO instance

        Note:
            Internally delegates to choice_domain_to_dto converter function.
            This instance method exists to satisfy DomainModelProtocol for
            type-safe generic operations.

            Graph-native fields (informed_by_knowledge_uids, opens_learning_paths,
            etc.) are NOT included in the domain model - they must be populated
            by service layer via graph queries.

        Example:
            choice = Choice(...)
            dto = choice.to_dto()  # Can modify DTO fields
        """
        from core.models.choice.choice_converters import choice_domain_to_dto

        return choice_domain_to_dto(self)

    # ==========================================================================
    # Business Logic Methods
    # ==========================================================================
    # is_completed(), is_cancelled(), is_terminal() provided by StatusChecksMixin
    # Note: is_completed() returns True for DECIDED, IMPLEMENTED, EVALUATED per config

    def is_pending(self) -> bool:
        """Check if choice is still pending."""
        return self.status == ChoiceStatus.PENDING

    def is_decided(self) -> bool:
        """Check if choice has been made. Alias for is_completed()."""
        return self.is_completed()

    def is_overdue(self) -> bool:
        """Check if choice is past its deadline."""
        return (
            self.decision_deadline is not None
            and datetime.now() > self.decision_deadline
            and not self.is_decided()
        )

    def get_selected_option(self) -> ChoiceOption | None:
        """Get the selected option if decision made."""
        if not self.selected_option_uid:
            return None

        for option in self.options:
            if option.uid == self.selected_option_uid:
                return option
        return None

    def get_available_options(self) -> tuple[ChoiceOption, ...]:
        """Get all available options."""
        return self.options

    def get_feasible_options(self, threshold: float = 0.6) -> tuple[ChoiceOption, ...]:
        """Get only feasible options above threshold."""
        return tuple(option for option in self.options if option.is_feasible(threshold))

    def rank_options(self, user_preferences: dict[str, float]) -> list[ChoiceOption]:
        """Rank options by calculated scores."""
        options_with_scores = [
            (option, option.calculate_option_score(user_preferences)) for option in self.options
        ]
        options_with_scores.sort(key=itemgetter(1), reverse=True)
        return [option for option, score in options_with_scores]

    def calculate_decision_complexity(self) -> float:
        """Calculate complexity score based on multiple factors."""
        option_count_factor = min(1.0, len(self.options) / 10.0)
        criteria_count_factor = min(1.0, len(self.decision_criteria) / 5.0)
        stakeholder_factor = min(1.0, len(self.stakeholders) / 3.0)
        constraint_factor = min(1.0, len(self.constraints) / 5.0)

        return (
            option_count_factor + criteria_count_factor + stakeholder_factor + constraint_factor
        ) / 4.0

    def time_until_deadline(self) -> int | None:
        """Get minutes until deadline, None if no deadline."""
        if self.decision_deadline is None:
            return None

        delta = self.decision_deadline - datetime.now()
        return max(0, int(delta.total_seconds() / 60))

    def has_high_stakes(self) -> bool:
        """Determine if this is a high-stakes decision."""
        return (
            self.priority == Priority.HIGH
            or len(self.stakeholders) > 2
            or self.calculate_decision_complexity() > 0.7
        )

    def get_decision_quality_score(self) -> float | None:
        """Calculate decision quality based on outcome and satisfaction."""
        if self.satisfaction_score is None:
            return None

        # Base score from satisfaction (1-5 scale converted to 0-1)
        satisfaction_normalized = (self.satisfaction_score - 1) / 4.0

        # Adjust for lessons learned (indicates growth)
        learning_bonus = min(0.2, len(self.lessons_learned) * 0.05)

        # Complexity adjustment (harder decisions get slight bonus)
        complexity_bonus = self.calculate_decision_complexity() * 0.1

        return min(1.0, satisfaction_normalized + learning_bonus + complexity_bonus)

    def needs_follow_up(self) -> bool:
        """Check if choice needs follow-up evaluation."""
        return self.status == ChoiceStatus.IMPLEMENTED and self.satisfaction_score is None

    # ==========================================================================
    # INSPIRATION ENGINE (SKUEL Mission: Inspire, Motivate, Educate)
    # ==========================================================================

    def is_inspirational_choice(self) -> bool:
        """
        Check if choice is designed to inspire and open possibilities.

        GRAPH-NATIVE: opens_learning_paths requires service layer query.
        Use: backend.count_related(uid, "OPENS_LEARNING_PATH", "outgoing") > 0
        """
        return (
            self.inspiration_type is not None or self.expands_possibilities
            # Missing: opens_learning_paths check (requires graph query)
        )

    def is_curriculum_informed(self) -> bool:
        """
        Check if choice is informed by curriculum knowledge.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "INFORMED_BY_KNOWLEDGE", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def requires_learning_to_decide(self) -> bool:
        """
        Check if user needs to learn before making informed choice.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "REQUIRES_KNOWLEDGE_FOR_DECISION", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def opens_new_possibilities(self) -> bool:
        """
        Check if choice explicitly opens new life/career paths.

        GRAPH-NATIVE: opens_learning_paths requires service layer query.
        Use: backend.count_related(uid, "OPENS_LEARNING_PATH", "outgoing") > 0
        """
        return self.expands_possibilities  # Partial check - missing graph query

    def is_principle_aligned(self) -> bool:
        """
        Check if choice is guided by user's principles.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "ALIGNED_WITH_PRINCIPLE", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def is_life_direction_choice(self) -> bool:
        """Check if choice affects life direction."""
        return self.inspiration_type == "life_direction"

    def is_career_path_choice(self) -> bool:
        """Check if choice affects career direction."""
        return self.inspiration_type == "career_path"

    def is_skill_acquisition_choice(self) -> bool:
        """Check if choice is about learning new skills."""
        return self.inspiration_type == "skill_acquisition"

    def get_curriculum_context(self) -> dict:
        """
        Get complete curriculum context for this choice.

        GRAPH-NATIVE: UID lists require service layer queries.
        Use: backend.get_related_uids(uid, relationship_type, "outgoing")

        Returns:
            Dictionary with knowledge and learning path information (UID lists as empty placeholders)
        """
        return {
            "is_curriculum_informed": False,  # Requires graph query
            "informed_by_knowledge": [],  # GRAPH QUERY: get_related_uids(uid, "INFORMED_BY_KNOWLEDGE", "outgoing")
            "knowledge_required_count": 0,  # Requires graph query
            "required_knowledge": [],  # GRAPH QUERY: get_related_uids(uid, "REQUIRES_KNOWLEDGE_FOR_DECISION", "outgoing")
            "opens_learning_paths": [],  # GRAPH QUERY: get_related_uids(uid, "OPENS_LEARNING_PATH", "outgoing")
            "paths_opened_count": 0,  # Requires graph query
            "aligned_principles": [],  # GRAPH QUERY: get_related_uids(uid, "ALIGNED_WITH_PRINCIPLE", "outgoing")
            "requires_learning": False,  # Requires graph query
            "opens_possibilities": self.expands_possibilities,  # Partial - node property only
        }

    def get_inspiration_context(self) -> dict:
        """
        Get inspiration context - how this choice inspires the user.

        GRAPH-NATIVE: UID lists and relationship counts require service layer queries.

        Returns:
            Dictionary with inspiration information (partial - from node properties only)
        """
        return {
            "is_inspirational": self.is_inspirational_choice(),  # Partial - missing graph data
            "inspiration_type": self.inspiration_type,
            "expands_possibilities": self.expands_possibilities,
            "vision_statement": self.vision_statement,
            "opens_learning_paths": [],  # GRAPH QUERY: get_related_uids(uid, "OPENS_LEARNING_PATH", "outgoing")
            "paths_count": 0,  # GRAPH QUERY: count_related(uid, "OPENS_LEARNING_PATH", "outgoing")
            "is_principle_aligned": False,  # GRAPH QUERY: count_related(uid, "ALIGNED_WITH_PRINCIPLE", "outgoing") > 0
            "inspiration_strength": 0.0,  # Requires graph query for full calculation
        }

    def calculate_inspiration_strength(self) -> float:
        """
        Calculate how inspiring this choice is (0-1).

        GRAPH-NATIVE: Learning paths and principle alignment require service layer queries.
        Service layer must enrich with graph relationship counts for full 0.0-1.0 range.

        Returns:
            Partial score from node properties only (0.0-0.45 range)
        """
        score = 0.0

        # NOTE: Opens learning paths (40%) requires graph query
        # Service layer must add: count_related(uid, "OPENS_LEARNING_PATH") * 0.15

        # Has vision statement (25%)
        if self.vision_statement:
            score += 0.25

        # Expands possibilities (20%)
        if self.expands_possibilities:
            score += 0.2

        # NOTE: Principle-aligned (15%) requires graph query
        # Service layer must add: 0.15 if count_related(uid, "ALIGNED_WITH_PRINCIPLE") > 0

        return min(1.0, score)

    def suggest_learning_before_deciding(self) -> list[str]:
        """
        Suggest what user should learn before making this choice.

        GRAPH-NATIVE: All knowledge and learning path counts require service layer queries.
        Service layer must enrich with actual relationship counts.

        Returns:
            List of learning recommendations (placeholder - requires service enrichment)
        """
        # NOTE: Service layer must query:
        # - count_related(uid, "REQUIRES_KNOWLEDGE_FOR_DECISION", "outgoing")
        # - count_related(uid, "OPENS_LEARNING_PATH", "outgoing")
        # - count_related(uid, "INFORMED_BY_KNOWLEDGE", "outgoing")

        return ["Choice is ready to be made - service layer should enrich with graph data"]

    def create_vision_from_choice(self) -> str:
        """
        Generate vision statement showing future possibilities.

        Returns:
            Vision statement or placeholder
        """
        if self.vision_statement:
            return self.vision_statement

        # Generate based on choice type
        if self.is_career_path_choice():
            return f"Choosing {self.title} could open career opportunities in new directions"
        elif self.is_skill_acquisition_choice():
            return f"Learning through {self.title} expands your capabilities"
        elif self.is_life_direction_choice():
            return f"{self.title} shapes your life's trajectory"
        else:
            return f"{self.title} opens new possibilities"

    # ==========================================================================
    # GOAL CREATION (INSPIRE → MOTIVATE bridge)
    # ==========================================================================

    def suggest_goal_from_option(self, option_uid: str) -> dict[str, Any] | None:
        """
        Suggest a goal based on selected choice option.

        This is the critical INSPIRE → MOTIVATE bridge. When a user selects
        an option from an inspirational choice, this method generates a
        goal recommendation with complete curriculum backing.

        Args:
            option_uid: UID of the selected option

        Returns:
            Dictionary with goal suggestion data, or None if option not found
        """
        # Find the selected option
        selected_option = None
        for option in self.options:
            if option.uid == option_uid:
                selected_option = option
                break

        if not selected_option:
            return None

        # Build goal suggestion
        goal_title = f"{selected_option.title}"
        if self.inspiration_type == "career_path":
            goal_title = f"Pursue {selected_option.title} career path"
        elif self.inspiration_type == "skill_acquisition":
            goal_title = f"Master {selected_option.title}"
        elif self.inspiration_type == "life_direction":
            goal_title = f"Embrace {selected_option.title} lifestyle"

        # Determine goal type from inspiration type
        from core.models.goal.goal import GoalTimeframe, GoalType

        goal_type_mapping = {
            "career_path": GoalType.PROJECT,
            "skill_acquisition": GoalType.MASTERY,
            "life_direction": GoalType.OUTCOME,
            "project_idea": GoalType.PROJECT,
        }
        goal_type = goal_type_mapping.get(self.inspiration_type, GoalType.LEARNING)

        # Determine timeframe based on complexity
        timeframe = GoalTimeframe.QUARTERLY
        if selected_option.estimated_duration:
            if selected_option.estimated_duration > 1000:  # >1000 hours
                timeframe = GoalTimeframe.YEARLY
            elif selected_option.estimated_duration > 500:
                timeframe = GoalTimeframe.QUARTERLY
            else:
                timeframe = GoalTimeframe.MONTHLY

        # GRAPH-NATIVE: UID lists must be populated by service layer
        # Service should call get_related_uids() for each relationship type
        return {
            "title": goal_title,
            "description": selected_option.description,
            "vision_statement": self.vision_statement or self.create_vision_from_choice(),
            "goal_type": goal_type,
            "timeframe": timeframe,
            "inspired_by_choice_uid": self.uid,
            "selected_choice_option_uid": option_uid,
            "aligned_learning_path_uids": [],  # GRAPH QUERY: get_related_uids(uid, "OPENS_LEARNING_PATH", "outgoing")
            "required_knowledge_uids": [],  # GRAPH QUERY: get_related_uids(uid, "REQUIRES_KNOWLEDGE_FOR_DECISION", "outgoing")
            "guiding_principle_uids": [],  # GRAPH QUERY: get_related_uids(uid, "ALIGNED_WITH_PRINCIPLE", "outgoing")
            "why_important": f"Inspired by choice: {self.title}",
            "success_criteria": f"Successfully complete learning path and achieve {selected_option.title}",
            "inspiration_strength": self.calculate_inspiration_strength(),  # Partial score
            "curriculum_driven": True,
        }

    def suggest_goals_from_all_options(self) -> list[dict[str, Any]]:
        """
        Generate goal suggestions for all options in this choice.

        Useful for presenting users with "what if" scenarios:
        "If you choose option A, here's the goal path..."
        "If you choose option B, here's the goal path..."

        Returns:
            List of goal suggestion dictionaries
        """
        suggestions = []
        for option in self.options:
            suggestion = self.suggest_goal_from_option(option.uid)
            if suggestion:
                suggestions.append(suggestion)
        return suggestions

    def generate_insights(self) -> dict[str, Any]:
        """Generate insights from this choice for learning."""
        return {
            "decision_speed": self._calculate_decision_speed(),
            "option_utilization": len(self.options),
            "criteria_thoroughness": len(self.decision_criteria),
            "complexity_level": self.calculate_decision_complexity(),
            "outcome_quality": self.get_decision_quality_score(),
            "learning_generated": len(self.lessons_learned) > 0,
            "stakeholder_consideration": len(self.stakeholders) > 0,
        }

    def _calculate_decision_speed(self) -> float | None:
        """Calculate how quickly decision was made (days)."""
        if not self.decided_at:
            return None

        delta = self.decided_at - self.created_at
        return delta.total_seconds() / (24 * 3600)  # Convert to days

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_decision_context_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for decision context

        Finds goals, principles, and knowledge relevant to this choice.

        Args:
            depth: Maximum context depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.RELATIONSHIP, depth=depth
        )

    def build_impact_analysis_query(self) -> str:
        """
        Build pure Cypher query for impact analysis

        Finds tasks, goals, and habits affected by this choice.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.HIERARCHICAL, depth=GraphDepth.NEIGHBORHOOD
        )

    def build_knowledge_requirements_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for knowledge requirements

        Finds knowledge needed to make an informed decision.

        Args:
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PREREQUISITE, depth=depth
        )

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Get suggested QueryIntent based on choice characteristics.

        Business rules (December 2025 - PRINCIPLE_ALIGNMENT priority):
        - Default → PRINCIPLE_ALIGNMENT (most choices benefit from principle context)
        - Strategic choices → PRINCIPLE_ALIGNMENT (principles guide strategy)
        - Binary choices → PRINCIPLE_ALIGNMENT (principles clarify binary decisions)
        - Allocation choices → AGGREGATION (resource distribution needs stats)

        The PRINCIPLE_ALIGNMENT intent emphasizes:
        - Principles guiding this choice
        - Knowledge informing the decision
        - Goals supported or conflicted

        Returns:
            Recommended QueryIntent for this choice
        """
        # Allocation choices need aggregation for resource analysis
        if self.choice_type == ChoiceType.ALLOCATION:
            return QueryIntent.AGGREGATION

        # All other choice types benefit from principle alignment context
        # This includes STRATEGIC, BINARY, MULTIPLE, RANKING, OPERATIONAL
        return QueryIntent.PRINCIPLE_ALIGNMENT

    # ==========================================================================
    # GRAPHENTITY PROTOCOL IMPLEMENTATION (Phase 2)
    # ==========================================================================

    def explain_existence(self) -> str:
        """
        WHY does this choice exist? One-sentence reasoning.

        GRAPH-NATIVE: Principle alignment requires service layer query.

        Returns:
            str: Explanation of choice's existence and context (partial)
        """
        parts = [self.title]  # Fixed: self.question undefined - using self.title

        # Add status context
        if self.status == ChoiceStatus.DECIDED and self.selected_option_uid:
            selected = next((o for o in self.options if o.uid == self.selected_option_uid), None)
            if selected:
                parts.append(f"Decided: {selected.title}")

        # Add outcome if evaluated
        if self.actual_outcome:
            parts.append(f"Outcome: {self.actual_outcome}")

        # NOTE: Principle alignment requires graph query
        # Service layer should add: count_related(uid, "ALIGNED_WITH_PRINCIPLE", "outgoing")

        # NOTE: self.confidence_level undefined in model - skipped
        # NOTE: Future enhancement - add confidence tracking

        return ". ".join(parts)

    def get_upstream_influences(self) -> list[dict]:
        """
        WHAT shaped this choice? (Scaffolding method - see ChoiceService for implementation)

        Returns:
            Upstream entities (principles, goals, knowledge, parent choices)

        GRAPH-NATIVE IMPLEMENTATION:
        This requires graph queries and must be called via service layer:

            result = await choice_service.get_upstream_influences(choice.uid)

        Service will query:
        - backend.get_related_uids(uid, "ALIGNED_WITH_PRINCIPLE", "outgoing")
        - backend.get_related_uids(uid, "INFORMED_BY_KNOWLEDGE", "outgoing")
        - backend.get_related_uids(uid, "REQUIRES_KNOWLEDGE_FOR_DECISION", "outgoing")
        - backend.get_related_uids(uid, "MOTIVATED_BY_GOAL", "incoming")

        Future enhancements:
        - Add parent Choice relationships (for derived choices)
        - Add Events that triggered this choice
        - Track decision context and environmental factors

        NOTE: This method exists for API discoverability and documentation.
        It intentionally returns [] to indicate service layer is required.
        """
        return []  # Service layer implementation required

    def get_downstream_impacts(self) -> list[dict]:
        """
        WHAT does this choice shape? (Scaffolding method - see ChoiceService for implementation)

        Returns:
            Downstream entities (goals, habits, tasks derived from choice)

        GRAPH-NATIVE IMPLEMENTATION:
        This requires graph queries and must be called via service layer:

            result = await choice_service.get_downstream_impacts(choice.uid)

        Service will query (reverse lookup patterns):
        - backend.get_related_uids(uid, "DERIVES_FROM_CHOICE", "incoming") for goals
        - backend.get_related_uids(uid, "INSPIRED_BY_CHOICE", "incoming") for habits
        - backend.get_related_uids(uid, "CREATED_FROM_CHOICE", "incoming") for tasks
        - backend.get_related_uids(uid, "ENABLES_CHOICE", "outgoing") for dependent choices

        Future enhancements:
        - Track goals created from this choice (via Derivation)
        - Track habits created from this choice
        - Track tasks created from this choice
        - Track future choices this enables
        - Implement full Derivation tracking system

        NOTE: This method exists for API discoverability and documentation.
        It intentionally returns [] to indicate service layer is required.
        """
        return []  # Service layer implementation required

    def get_relationship_summary(self) -> dict:
        """
        Get comprehensive relationship context for this choice.

        GRAPH-NATIVE: Relationship counts require service layer queries.

        Returns:
            Dict with explanation, upstream influences, and downstream impacts (partial)
        """
        return {
            "explanation": self.explain_existence(),  # Partial
            "upstream": self.get_upstream_influences(),  # Empty - service should enrich
            "downstream": self.get_downstream_impacts(),  # Empty
            "upstream_count": 0,  # Service should query graph relationships
            "downstream_count": 0,  # Service should query graph relationships
            "decision_context": {
                "status": self.status.value,
                "type": self.choice_type.value,
                "options_count": len(self.options),
                "selected": self.selected_option_uid,
                "confidence": None,  # NOTE: self.confidence_level undefined in model
                "reversible": None,  # NOTE: self.is_reversible undefined in model
            },
        }

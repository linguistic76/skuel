"""
Goal Domain Model (Tier 3 - Core)
==================================

Immutable domain model with business logic for goals.
Goals represent desired outcomes that guide learning and habit formation.

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for supporting activities and knowledge requirements
- Phase 3: GraphContext for cross-domain goal intelligence
- Phase 4: QueryIntent selection for goal-specific patterns
"""

from __future__ import annotations

from core.constants import GraphDepth

__version__ = "2.1"  # Updated for Phase 1-4 integration


from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.enums import Domain, GoalStatus, Priority
from core.models.mixins import StatusChecksMixin
from core.models.query import QueryIntent

# Phase 1: Query Infrastructure
from core.models.query.graph_traversal import build_graph_context_query

if TYPE_CHECKING:
    from core.models.goal.goal_relationships import GoalRelationships


# Goal-specific enums (not in shared_enums to avoid circular imports)
class GoalType(str, Enum):
    """Types of goals aligned with learning objectives"""

    OUTCOME = "outcome"  # Result-focused (achieve X)
    PROCESS = "process"  # Activity-focused (do Y consistently)
    LEARNING = "learning"  # Knowledge/skill acquisition
    PROJECT = "project"  # Complete a specific project
    MILESTONE = "milestone"  # Reach a specific milestone
    MASTERY = "mastery"  # Master a domain/skill


class GoalTimeframe(str, Enum):
    """Goal time horizons for planning"""

    DAILY = "daily"  # Micro-goals
    WEEKLY = "weekly"  # Short-term
    MONTHLY = "monthly"  # Near-term
    QUARTERLY = "quarterly"  # Medium-term
    YEARLY = "yearly"  # Long-term
    MULTI_YEAR = "multi_year"  # Strategic


class MeasurementType(str, Enum):
    """How goal progress is measured"""

    BINARY = "binary"  # Done/Not Done
    PERCENTAGE = "percentage"  # 0-100%
    NUMERIC = "numeric"  # Specific number
    MILESTONE = "milestone"  # Checkpoints
    HABIT_BASED = "habit_based"  # Based on habit consistency
    KNOWLEDGE_BASED = "knowledge_based"  # Based on knowledge mastery
    TASK_BASED = "task_based"  # Based on task completion (Phase 4)
    MIXED = "mixed"  # Multiple measurement factors combined (Phase 4)


class HabitEssentiality(str, Enum):
    """
    Classification of habit importance to goal achievement.

    Based on James Clear's Atomic Habits philosophy:
    "You do not rise to the level of your goals.
     You fall to the level of your systems."

    This enum helps identify which habits form the ESSENTIAL SYSTEM
    that the goal depends on.
    """

    ESSENTIAL = "essential"  # Goal is impossible without this habit
    CRITICAL = "critical"  # Goal is very difficult without this habit
    SUPPORTING = "supporting"  # Goal is easier with this habit
    OPTIONAL = "optional"  # Habit is tangentially helpful


@dataclass(frozen=True)
class Milestone:
    """A checkpoint on the way to achieving a goal"""

    uid: str
    title: str
    description: str | None
    target_date: date
    target_value: float | None = (None,)
    achieved_date: date | None = None  # type: ignore[assignment]
    is_completed: bool = False

    # Learning integration
    required_knowledge_uids: tuple[str, ...] = ()  # Knowledge needed for this milestone,
    unlocked_knowledge_uids: tuple[str, ...] = ()  # Knowledge unlocked by achieving


@dataclass(frozen=True)
class Goal(StatusChecksMixin):
    """
    Immutable domain model representing a goal.

    Goals are the 'why' behind learning and habits - they provide direction
    and motivation for knowledge acquisition and behavior change.
    """

    # Identity
    uid: str
    user_uid: str  # REQUIRED - goal ownership
    title: str
    description: str | None = None
    vision_statement: str | None = None  # Long-term vision this supports

    # Classification
    goal_type: GoalType = GoalType.OUTCOME
    domain: Domain = Domain.KNOWLEDGE  # Aligned with Knowledge domains,
    timeframe: GoalTimeframe = GoalTimeframe.QUARTERLY

    # Measurement
    measurement_type: MeasurementType = MeasurementType.PERCENTAGE
    target_value: float | None = None
    current_value: float = 0.0
    unit_of_measurement: str | None = None  # e.g., "pages", "pounds", "hours"

    # Timeline
    start_date: date | None = None  # type: ignore[assignment]
    target_date: date | None = None  # type: ignore[assignment]
    achieved_date: date | None = None  # type: ignore[assignment]

    # Learning Integration - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (goal)-[:REQUIRES_KNOWLEDGE]->(ku)
    # Graph relationship: (goal)-[:GUIDED_BY_PRINCIPLE]->(principle)
    parent_goal_uid: str | None = None  # Parent goal if this is a sub-goal
    # Graph relationship: (goal)-[:HAS_SUBGOAL]->(subgoal)

    # Atomic Habits Integration (James Clear philosophy) - GRAPH-NATIVE
    # "You do not rise to the level of your goals. You fall to the level of your systems."
    # Graph relationship: (goal)-[:REQUIRES_HABIT {essentiality: "essential|critical|supporting|optional"}]->(habit)
    # Single relationship type with essentiality property distinguishes habit importance levels

    # Identity-Based Habits (James Clear: focus on who you become, not what you achieve)
    target_identity: str | None = None  # "I am a writer" not "I want to write a book",
    identity_evidence_required: int = 0  # # of habit completions to reinforce identity

    # Curriculum Spine Integration (NEW - goal ↔ lp ↔ ls bridge) - GRAPH-NATIVE
    source_learning_path_uid: str | None = None  # lp: UID if goal comes from completing a path
    # Graph relationship: (goal)-[:ALIGNED_WITH_PATH]->(lp)
    # Graph relationship: (goal)-[:REQUIRES_PATH_COMPLETION]->(lp)
    curriculum_driven: bool = False  # True if goal is curriculum-originated

    # Choice Integration (INSPIRE → MOTIVATE bridge)
    inspired_by_choice_uid: str | None = None  # choice: UID that inspired this goal,
    selected_choice_option_uid: str | None = None  # Which option was chosen from the choice

    # Milestones
    milestones: tuple[Milestone, ...] = ()

    # Progress Tracking
    progress_percentage: float = 0.0
    last_progress_update: datetime | None = None  # type: ignore[assignment]
    progress_history: tuple[dict, ...] = ()  # Historical progress snapshots

    # Motivation & Context
    why_important: str | None = None  # Personal importance,
    success_criteria: str | None = None  # Clear definition of success,
    potential_obstacles: tuple[str, ...] = ()
    strategies: tuple[str, ...] = ()  # Strategies to achieve

    # Status
    status: GoalStatus = GoalStatus.PLANNED
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = None  # type: ignore[assignment]  # Rich context storage (graph neighborhoods, etc.)

    # =========================================================================
    # NEO4J GENAI PLUGIN INTEGRATION (January 2026)
    # Vector embeddings for semantic search and similarity matching
    # =========================================================================
    embedding: tuple[float, ...] | None = None  # 1536-dimensional vector for semantic search
    embedding_model: str | None = None  # Model used (e.g., "text-embedding-3-small")
    embedding_updated_at: datetime | None = None  # type: ignore[assignment]  # When embedding was generated

    # StatusChecksMixin configuration
    # Goal uses GoalStatus with ACHIEVED as completed state
    _completed_statuses: ClassVar[tuple[GoalStatus, ...]] = (GoalStatus.ACHIEVED,)
    _cancelled_statuses: ClassVar[tuple[GoalStatus, ...]] = (GoalStatus.CANCELLED,)
    _terminal_statuses: ClassVar[tuple[GoalStatus, ...]] = (
        GoalStatus.ACHIEVED,
        GoalStatus.CANCELLED,
    )
    _active_statuses: ClassVar[tuple[GoalStatus, ...]] = (
        GoalStatus.PLANNED,
        GoalStatus.ACTIVE,
        GoalStatus.PAUSED,
    )

    def __post_init__(self) -> None:
        """Set defaults for datetime and metadata fields."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # Goal implements KnowledgeCarrier and ActivityCarrier.
    # Goal is INFORMED BY and REQUIRES knowledge - relevance based on learning.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        Goal relevance based on curriculum and learning integration.

        Returns:
            0.0-1.0 based on learning integration
        """
        score = 0.0

        # Learning or Mastery goal type (highest relevance)
        if self.goal_type in (GoalType.LEARNING, GoalType.MASTERY):
            score = 0.9

        # Curriculum-driven goal
        if self.curriculum_driven:
            score = max(score, 0.8)

        # From learning path
        if self.source_learning_path_uid:
            score = max(score, 0.7)

        # Knowledge-based measurement
        if self.measurement_type == MeasurementType.KNOWLEDGE_BASED:
            score = max(score, 0.8)

        # Knowledge domain
        if self.domain == Domain.KNOWLEDGE:
            score = max(score, 0.5)

        return score

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity requires.

        Goal knowledge is stored as graph relationships.
        This is a GRAPH-NATIVE placeholder - actual data requires service layer.

        Use service.relationships.get_goal_knowledge(goal_uid) for real data.

        Returns:
            Empty tuple (placeholder - actual KU UIDs via graph query)
        """
        # GRAPH-NATIVE: Real implementation requires service layer query
        # Query: MATCH (goal)-[:REQUIRES_KNOWLEDGE]->(ku) RETURN ku.uid
        return ()

    def learning_impact_score(self) -> float:
        """
        Calculate learning impact when this goal is achieved.

        Goals don't directly increment KU substance counters,
        but achieving learning goals validates knowledge application.

        Returns:
            Impact score 0.0-1.0
        """
        score = 0.0

        # Learning/Mastery goal (high impact)
        if self.goal_type in (GoalType.LEARNING, GoalType.MASTERY):
            score += 0.5

        # Curriculum-driven
        if self.curriculum_driven:
            score += 0.3

        # Knowledge-based measurement
        if self.measurement_type == MeasurementType.KNOWLEDGE_BASED:
            score += 0.2

        return min(1.0, score)

    # ==========================================================================
    # STATUS CHECKS
    # ==========================================================================
    # is_completed(), is_cancelled(), is_terminal() provided by StatusChecksMixin
    # Note: is_completed() returns True for ACHIEVED status per _completed_statuses config

    def is_active(self) -> bool:
        """Check if goal is currently being pursued."""
        return self.status == GoalStatus.ACTIVE

    def is_achieved(self) -> bool:
        """Check if goal has been achieved. Alias for is_completed()."""
        return self.is_completed()

    def is_abandoned(self) -> bool:
        """Check if goal was abandoned. Alias for is_cancelled()."""
        return self.is_cancelled()

    def is_overdue(self) -> bool:
        """Check if goal is past its target date."""
        if not self.target_date or self.is_achieved():
            return False
        return date.today() > self.target_date

    def is_on_track(self) -> bool:
        """
        Check if goal progress is on pace for target date.

        Returns True if:
        - Goal is active AND
        - No target_date (no deadline = always on track if active) OR
        - Current progress >= expected progress based on time elapsed

        Returns:
            True if goal is on track, False otherwise
        """
        if not self.is_active():
            return False
        if not self.target_date:
            return True  # No deadline = always on track if active

        # Calculate expected progress based on time elapsed
        if not self.created_at:
            return True  # Can't calculate expected progress without start date

        total_days = (self.target_date - self.created_at.date()).days
        if total_days <= 0:
            # Deadline passed or same day - on track if progress >= 100
            return self.progress_percentage >= 100

        elapsed_days = (date.today() - self.created_at.date()).days
        expected_progress = (elapsed_days / total_days) * 100

        return self.progress_percentage >= expected_progress

    # ==========================================================================
    # PROGRESS CALCULATIONS
    # ==========================================================================

    def calculate_progress(self) -> float:
        """
        Calculate progress percentage based on measurement type.

        Returns:
            Progress as percentage (0-100)
        """
        if self.is_achieved():
            return 100.0

        if self.measurement_type == MeasurementType.PERCENTAGE:
            return min(self.progress_percentage, 100.0)

        elif self.measurement_type == MeasurementType.NUMERIC and self.target_value:
            if self.target_value > 0:
                return min((self.current_value / self.target_value) * 100, 100.0)

        elif self.measurement_type == MeasurementType.MILESTONE:
            if self.milestones:
                completed = sum(1 for m in self.milestones if m.is_completed)
                return (completed / len(self.milestones)) * 100

        elif self.measurement_type == MeasurementType.BINARY:
            return 100.0 if self.is_achieved() else 0.0

        return self.progress_percentage

    def get_days_remaining(self) -> int | None:
        """Calculate days remaining until target date."""
        if not self.target_date or self.is_achieved():
            return None
        delta = self.target_date - date.today()
        return max(0, delta.days)

    def get_required_daily_progress(self) -> float | None:
        """
        Calculate required daily progress to meet target.

        Returns:
            Required daily progress value, or None if not applicable
        """
        days_left = self.get_days_remaining()
        if not days_left or days_left == 0:
            return None

        if self.measurement_type == MeasurementType.NUMERIC and self.target_value:
            remaining = self.target_value - self.current_value
            return remaining / days_left

        elif self.measurement_type == MeasurementType.PERCENTAGE:
            remaining = 100.0 - self.progress_percentage
            return remaining / days_left

        return None

    def expected_progress_percentage(self) -> float:
        """
        Calculate expected progress percentage based on elapsed time.

        Returns:
            Expected progress percentage (0-100) based on time elapsed
        """
        if not self.target_date or not self.created_at:
            return 0.0

        # Calculate total duration and elapsed time
        total_duration = (self.target_date - self.created_at.date()).days
        if total_duration <= 0:
            return 100.0

        elapsed = (date.today() - self.created_at.date()).days
        expected = (elapsed / total_duration) * 100.0

        return min(100.0, max(0.0, expected))

    def days_remaining(self) -> int:
        """
        Get days remaining until target date.

        Returns:
            Days remaining (0 if overdue or no target_date)
        """
        days = self.get_days_remaining()
        return days if days is not None else 0

    # ==========================================================================
    # LEARNING INTEGRATION
    # ==========================================================================

    def is_learning_goal(self) -> bool:
        """
        Check if this is primarily a learning goal.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "REQUIRES_KNOWLEDGE", "outgoing") > 0
        """
        return (
            self.goal_type == GoalType.LEARNING or self.goal_type == GoalType.MASTERY
        )  # Partial check - missing REQUIRES_KNOWLEDGE relationship check

    def requires_knowledge(self) -> bool:
        """
        Check if this goal requires specific knowledge.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "REQUIRES_KNOWLEDGE", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    # ==========================================================================
    # CURRICULUM SPINE INTEGRATION (Goal ↔ lp ↔ ls bridge)
    # ==========================================================================

    def is_curriculum_goal(self, rels: GoalRelationships | None = None) -> bool:
        """
        Check if goal originated from or is supported by curriculum.

        Args:
            rels: Relationship data (optional) - if not provided, returns partial answer
        """
        has_aligned_paths = len(rels.aligned_learning_path_uids) > 0 if rels else False
        return (
            self.curriculum_driven or self.source_learning_path_uid is not None or has_aligned_paths
        )

    def is_from_learning_path(self) -> bool:
        """Check if goal comes from completing a learning path."""
        return self.source_learning_path_uid is not None

    def has_curriculum_alignment(self) -> bool:
        """
        Check if goal has aligned learning paths.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "ALIGNED_WITH_PATH", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def get_curriculum_context(self, rels: GoalRelationships | None = None) -> dict:
        """
        Get complete curriculum context for this goal.

        Args:
            rels: Relationship data (required for full context)

        Returns:
            Dictionary with curriculum linkage information
        """
        # Use relationship data if provided, otherwise empty lists
        aligned_paths = rels.aligned_learning_path_uids if rels else []
        required_paths = rels.requires_completion_of_paths if rels else []
        required_knowledge = rels.required_knowledge_uids if rels else []

        return {
            "is_curriculum_goal": self.is_curriculum_goal(rels),
            "curriculum_driven": self.curriculum_driven,
            "source_learning_path": self.source_learning_path_uid,
            "aligned_paths": list(aligned_paths),
            "required_paths": list(required_paths),
            "required_knowledge": list(required_knowledge),
            "is_learning_goal": self.is_learning_goal(),
            "total_curriculum_dependencies": (
                len(aligned_paths) + len(required_paths) + len(required_knowledge)
            ),
        }

    def curriculum_support_score(self, rels: GoalRelationships | None = None) -> float:
        """
        Calculate how well supported this goal is by curriculum (0-1).

        Args:
            rels: Relationship data (required for accurate score)

        Higher scores indicate stronger curriculum alignment.
        """
        score = 0.0

        # Curriculum driven (30%)
        if self.curriculum_driven:
            score += 0.3

        # Has aligned paths (30%)
        aligned_count = len(rels.aligned_learning_path_uids) if rels else 0
        if aligned_count > 0:
            score += min(0.3, aligned_count * 0.1)

        # Knowledge requirements defined (25%)
        knowledge_count = len(rels.required_knowledge_uids) if rels else 0
        if knowledge_count > 0:
            score += min(0.25, knowledge_count * 0.05)

        # Has source path (15%)
        if self.source_learning_path_uid:
            score += 0.15

        return min(1.0, score)

    def suggest_curriculum_paths(self, rels: GoalRelationships | None = None) -> list[str]:
        """
        Suggest which curriculum elements to prioritize for this goal.

        Args:
            rels: Relationship data (required for complete suggestions)

        Returns:
            List of suggestions
        """
        suggestions = []

        required_paths = rels.requires_completion_of_paths if rels else []
        if len(required_paths) > 0:
            suggestions.append(f"Complete required paths: {', '.join(required_paths)}")

        aligned_paths = rels.aligned_learning_path_uids if rels else []
        if len(aligned_paths) > 0:
            suggestions.append(f"Follow aligned paths: {', '.join(aligned_paths)}")

        required_knowledge = rels.required_knowledge_uids if rels else []
        if len(required_knowledge) > 0:
            suggestions.append(f"Learn {len(required_knowledge)} knowledge units")

        if not suggestions:
            suggestions.append("Consider creating a learning path to support this goal")

        return suggestions

    # ==========================================================================
    # CHOICE INTEGRATION (INSPIRE → MOTIVATE bridge)
    # ==========================================================================

    def is_choice_inspired(self) -> bool:
        """Check if goal originated from an inspirational choice."""
        return self.inspired_by_choice_uid is not None

    def has_selected_option(self) -> bool:
        """Check if goal is linked to a specific choice option."""
        return self.selected_choice_option_uid is not None

    def is_fully_inspired(self, rels: GoalRelationships | None = None) -> bool:
        """
        Check if goal has complete inspiration lineage.

        Args:
            rels: Relationship data (required for aligned paths check)

        Fully inspired goals have:
        - Source choice that inspired them
        - Selected option from that choice
        - Aligned learning paths to educate
        """
        has_aligned_paths = len(rels.aligned_learning_path_uids) > 0 if rels else False
        return self.is_choice_inspired() and self.has_selected_option() and has_aligned_paths

    def get_choice_origin_context(self, rels: GoalRelationships | None = None) -> dict:
        """
        Get complete context of choice that inspired this goal.

        Args:
            rels: Relationship data (required for learning paths)

        Returns:
            Dictionary with choice inspiration information
        """
        aligned_paths = rels.aligned_learning_path_uids if rels else []
        return {
            "inspired_by_choice": self.inspired_by_choice_uid,
            "selected_option": self.selected_choice_option_uid,
            "is_choice_inspired": self.is_choice_inspired(),
            "has_selected_option": self.has_selected_option(),
            "is_fully_inspired": self.is_fully_inspired(rels),
            "inspiration_to_motivation_complete": self.is_fully_inspired(rels),
            "learning_paths_from_choice": list(aligned_paths) if self.is_choice_inspired() else [],
        }

    def calculate_inspiration_motivation_strength(
        self, rels: GoalRelationships | None = None
    ) -> float:
        """
        Calculate strength of inspiration→motivation flow (0-1).

        Args:
            rels: Relationship data (required for curriculum backing score)

        Measures how well the goal converts inspiration (choice) into
        motivation (measurable progress) backed by education (curriculum).

        Returns:
            Score from 0-1 where 1.0 is perfectly aligned
        """
        score = 0.0

        # Has choice inspiration (30%)
        if self.is_choice_inspired():
            score += 0.3

        # Has selected option (20%)
        if self.has_selected_option():
            score += 0.2

        # Has curriculum backing (30%)
        aligned_count = len(rels.aligned_learning_path_uids) if rels else 0
        if aligned_count > 0:
            score += min(0.3, aligned_count * 0.1)

        # Has principle alignment (10%)
        principle_count = len(rels.guiding_principle_uids) if rels else 0
        if principle_count > 0:
            score += 0.1

        # Has clear success criteria (10%)
        if self.success_criteria:
            score += 0.1

        return min(1.0, score)

    def get_full_mission_flow_context(self, rels: GoalRelationships | None = None) -> dict:
        """
        Get complete INSPIRE → MOTIVATE → EDUCATE flow context.

        This is the signature SKUEL differentiation - showing how
        inspiration flows through motivation into education.

        Returns:
            Dictionary with complete mission flow information
        """
        return {
            # INSPIRE (Choice)
            "inspire": {
                "has_inspiration_source": self.is_choice_inspired(),
                "choice_uid": self.inspired_by_choice_uid,
                "option_selected": self.selected_choice_option_uid,
                "principle_aligned": len(rels.guiding_principle_uids) if rels else 0 > 0,
                "principles": list(rels.guiding_principle_uids) if rels else [],
            },
            # MOTIVATE (Goal - this object)
            "motivate": {
                "goal_uid": self.uid,
                "goal_type": self.goal_type.value,
                "is_measurable": self.measurement_type != MeasurementType.BINARY,
                "has_success_criteria": bool(self.success_criteria),
                "progress": self.progress_percentage,
                "status": self.status.value,
            },
            # EDUCATE (Curriculum)
            "educate": {
                "has_curriculum": (len(rels.aligned_learning_path_uids) if rels else 0) > 0,
                "learning_paths": list(rels.aligned_learning_path_uids if rels else []),
                "required_knowledge": list(rels.required_knowledge_uids if rels else []),
                "curriculum_support_score": self.curriculum_support_score(),
            },
            # FLOW METRICS
            "flow_metrics": {
                "complete_flow": self.is_fully_inspired(),
                "flow_strength": self.calculate_inspiration_motivation_strength(),
                "breaks_in_flow": self._identify_flow_breaks(),
            },
        }

    def _identify_flow_breaks(self, rels: GoalRelationships | None = None) -> list[str]:
        """Identify where the Inspire→Motivate→Educate flow breaks."""
        breaks = []

        if not self.is_choice_inspired():
            breaks.append("Missing inspiration source (no choice)")

        if self.is_choice_inspired() and not self.has_selected_option():
            breaks.append("Choice source exists but no option selected")

        if not self.success_criteria:
            breaks.append("No success criteria defined (weak motivation)")

        if (len(rels.aligned_learning_path_uids) if rels else 0) == 0:
            breaks.append("No learning paths (missing education component)")

        if (len(rels.guiding_principle_uids) if rels else 0) == 0:
            breaks.append("No guiding principles (missing values alignment)")

        return breaks

    # ==========================================================================
    # ATOMIC HABITS INTEGRATION (James Clear Philosophy)
    # ==========================================================================
    # "You do not rise to the level of your goals.
    #  You fall to the level of your systems."
    #
    # Goals set direction. Habits (systems) create progress.
    # This section implements the philosophy from "Atomic Habits"
    # ==========================================================================

    def has_habit_system(self) -> bool:
        """
        Check if goal has ANY habits defined.

        James Clear: Goals without systems are wishes.

        GRAPH-NATIVE: Service layer must query graph relationships.
        Use: backend.count_related(uid, "REQUIRES_HABIT", "outgoing") > 0
        """
        return False  # Placeholder - service queries backend.count_related()

    def has_essential_habits(self) -> bool:
        """
        Check if goal has essential habits (the core system).

        GRAPH-NATIVE: Service layer must query graph relationships with property filter.
        Use: backend.count_related(uid, "REQUIRES_HABIT", "outgoing",
                                    properties={"essentiality": "essential"}) > 0
        """
        return False  # Placeholder - service queries backend.count_related() with filter

    def calculate_system_strength(
        self,
        rels: GoalRelationships | None = None,
        habit_success_rates: dict[str, float] | None = None,
    ) -> float:
        """
        Calculate strength of the habit system supporting this goal.

        James Clear: "You don't rise to the level of your goals.
                      You fall to the level of your systems."

        This metric measures HOW STRONG the system (habits) is.
        Strong system = high probability of goal achievement.

        Args:
            habit_success_rates: Dict mapping habit_uid -> success_rate (0-1)
                                If None, only measures system design (not execution)

        Returns:
            Score from 0-1 where:
            - 0.0 = No system (goal is wishful thinking)
            - 0.3 = Weak system (few habits, poor design)
            - 0.7 = Good system (essential habits defined)
            - 1.0 = Robust system (all levels defined + high success rates)
        """
        if not self.has_habit_system():
            return 0.0  # No system = wishful thinking

        score = 0.0

        # System Design Strength (60% of total score)
        design_score = 0.0

        # Essential habits are most important (30%)
        essential_count = len(rels.essential_habit_uids) if rels else 0
        critical_count = len(rels.critical_habit_uids) if rels else 0
        optional_count = len(rels.optional_habit_uids) if rels else 0

        if essential_count > 0:
            design_score += 0.3
        elif critical_count > 0:
            design_score += 0.15  # Critical habits partially compensate

        # Critical habits add robustness (15%)
        if critical_count > 0:
            design_score += 0.15

        # Supporting habits add depth (10%)
        if (len(rels.supporting_habit_uids) if rels else 0) > 0:
            design_score += min(0.1, (len(rels.supporting_habit_uids) if rels else 0) * 0.03)

        # Optional habits show thoroughness (5%)
        if optional_count > 0:
            design_score += 0.05

        score += design_score

        # System Execution Strength (40% of total score)
        if habit_success_rates and rels:
            execution_score = 0.0
            # Calculate total from all habit categories
            total_habits = (
                len(rels.essential_habit_uids)
                + len(rels.critical_habit_uids)
                + len(rels.supporting_habit_uids)
                + len(rels.optional_habit_uids)
            )

            if total_habits > 0:
                # Weight by essentiality
                essential_avg = self._calculate_weighted_success_rate(
                    tuple(rels.essential_habit_uids), habit_success_rates, weight=0.5
                )
                critical_avg = self._calculate_weighted_success_rate(
                    tuple(rels.critical_habit_uids), habit_success_rates, weight=0.3
                )
                supporting_avg = self._calculate_weighted_success_rate(
                    tuple(rels.supporting_habit_uids), habit_success_rates, weight=0.15
                )
                optional_avg = self._calculate_weighted_success_rate(
                    tuple(rels.optional_habit_uids), habit_success_rates, weight=0.05
                )

                execution_score = essential_avg + critical_avg + supporting_avg + optional_avg
                score += execution_score * 0.4  # Execution is 40% of total

        return min(1.0, score)

    def _calculate_weighted_success_rate(
        self, habit_uids: tuple[str, ...], success_rates: dict[str, float], weight: float
    ) -> float:
        """Helper to calculate weighted average success rate for habit group."""
        if not habit_uids:
            return 0.0

        total_success = sum(success_rates.get(uid, 0.0) for uid in habit_uids)
        avg_success = total_success / len(habit_uids)
        return avg_success * weight

    def diagnose_system_health(
        self,
        rels: GoalRelationships | None = None,
        habit_success_rates: dict[str, float] | None = None,
    ) -> dict:
        """
        Diagnose the health of the habit system supporting this goal.

        Returns actionable insights about system strength and weaknesses.

        Returns:
            Dictionary with:
            - system_strength: 0-1 score
            - diagnosis: Human-readable assessment
            - warnings: List of critical issues
            - recommendations: List of improvements
        """
        strength = self.calculate_system_strength(
            rels=rels, habit_success_rates=habit_success_rates
        )
        warnings = []
        recommendations = []

        # Check for missing system
        if not self.has_habit_system():
            return {
                "system_strength": 0.0,
                "diagnosis": "CRITICAL: Goal has no habit system defined. This is wishful thinking, not a plan.",
                "warnings": ["No habits defined - goal achievement unlikely"],
                "recommendations": [
                    "Define at least 1 ESSENTIAL habit required for this goal",
                    "Use suggest_essential_habits() to get recommendations",
                ],
                "system_exists": False,
            }

        # Check for missing essential habits
        essential_count = len(rels.essential_habit_uids) if rels else 0
        if essential_count == 0:
            warnings.append("No ESSENTIAL habits defined - what's the core system?")
            recommendations.append("Identify the one habit you CANNOT achieve this goal without")

        # Check execution quality
        if habit_success_rates and rels:
            essential_rates = [habit_success_rates.get(uid, 0) for uid in rels.essential_habit_uids]
            if essential_rates and sum(essential_rates) / len(essential_rates) < 0.5:
                warnings.append(
                    "Essential habits have low success rates (<50%) - system is failing"
                )
                recommendations.append("Focus on making essential habits easier or more rewarding")

        # Generate diagnosis
        if strength >= 0.8:
            diagnosis = "EXCELLENT: Strong habit system. Goal achievement highly likely."
        elif strength >= 0.6:
            diagnosis = "GOOD: Solid habit system with room for improvement."
        elif strength >= 0.4:
            diagnosis = "MODERATE: Basic system exists but needs strengthening."
        elif strength >= 0.2:
            diagnosis = "WEAK: System is inadequate for goal achievement."
        else:
            diagnosis = "POOR: Minimal system - goal is at risk."

        # Add general recommendations
        if strength < 0.8:
            critical_count = len(rels.critical_habit_uids) if rels else 0
            if critical_count == 0:
                recommendations.append("Consider adding CRITICAL habits to support essential ones")
            if (len(rels.supporting_habit_uids) if rels else 0) < 2:
                recommendations.append("Add supporting habits to make the system more robust")

        # Calculate totals from rels
        essential_count = len(rels.essential_habit_uids) if rels else 0
        critical_count = len(rels.critical_habit_uids) if rels else 0
        supporting_count = len(rels.supporting_habit_uids) if rels else 0
        optional_count = len(rels.optional_habit_uids) if rels else 0
        total_habits = essential_count + critical_count + supporting_count + optional_count

        return {
            "system_strength": strength,
            "diagnosis": diagnosis,
            "warnings": warnings,
            "recommendations": recommendations,
            "system_exists": True,
            "habit_breakdown": {
                "essential": essential_count,
                "critical": critical_count,
                "supporting": supporting_count,
                "optional": optional_count,
                "total": total_habits,
            },
        }

    def calculate_habit_velocity(
        self, habit_completion_counts: dict[str, int], rels: GoalRelationships | None = None
    ) -> float:
        """
        Calculate rate of progress from habits toward goal.

        Habit velocity = how fast habits are moving you toward the goal.
        High velocity = consistent habit execution = goal progress.

        Args:
            habit_completion_counts: Dict mapping habit_uid -> total_completions

        Returns:
            Velocity score 0-10+ where:
            - 0 = No habit activity
            - 5 = Moderate consistent activity
            - 10+ = Exceptional momentum
        """
        if not habit_completion_counts:
            return 0.0

        # Weight completions by essentiality
        weighted_completions = 0.0

        if rels:
            for uid in rels.essential_habit_uids:
                weighted_completions += habit_completion_counts.get(uid, 0) * 3.0  # 3x weight

            for uid in rels.critical_habit_uids:
                weighted_completions += habit_completion_counts.get(uid, 0) * 2.0  # 2x weight

            for uid in rels.supporting_habit_uids:
                weighted_completions += habit_completion_counts.get(uid, 0) * 1.0  # 1x weight

            for uid in rels.optional_habit_uids:
                weighted_completions += habit_completion_counts.get(uid, 0) * 0.5  # 0.5x weight

        # Normalize to 0-10 scale (10 weighted completions = velocity of 5)
        velocity = weighted_completions / 2.0

        return round(velocity, 2)

    def suggest_essential_habits(
        self, rels: GoalRelationships | None = None
    ) -> list[dict[str, Any]]:
        """
        Suggest essential habits based on goal type and timeframe.

        Uses goal characteristics to recommend which habits would form
        a strong system for achievement.

        Returns:
            List of habit suggestions, each with:
            - name: Suggested habit name
            - essentiality: ESSENTIAL, CRITICAL, or SUPPORTING
            - frequency: How often to do it
            - why: Explanation of importance
            - estimated_duration: Minutes per session
        """
        suggestions = []

        # Goal type determines core habits
        if self.goal_type == GoalType.LEARNING:
            suggestions.append(
                {
                    "name": f"Daily study session for {self.title}",
                    "essentiality": HabitEssentiality.ESSENTIAL,
                    "frequency": "daily",
                    "why": "Learning requires consistent daily practice",
                    "estimated_duration": 30,
                }
            )
            suggestions.append(
                {
                    "name": f"Weekly review of {self.title}",
                    "essentiality": HabitEssentiality.CRITICAL,
                    "frequency": "weekly",
                    "why": "Spaced repetition strengthens retention",
                    "estimated_duration": 45,
                }
            )

        elif self.goal_type == GoalType.MASTERY:
            suggestions.append(
                {
                    "name": f"Deliberate practice: {self.title}",
                    "essentiality": HabitEssentiality.ESSENTIAL,
                    "frequency": "daily",
                    "why": "Mastery requires focused, deliberate practice",
                    "estimated_duration": 60,
                }
            )
            suggestions.append(
                {
                    "name": "Track progress and reflect",
                    "essentiality": HabitEssentiality.CRITICAL,
                    "frequency": "weekly",
                    "why": "Self-assessment guides improvement",
                    "estimated_duration": 20,
                }
            )

        elif self.goal_type == GoalType.PROJECT:
            suggestions.append(
                {
                    "name": f"Work on {self.title}",
                    "essentiality": HabitEssentiality.ESSENTIAL,
                    "frequency": "3x per week",
                    "why": "Projects need consistent time blocks",
                    "estimated_duration": 90,
                }
            )
            suggestions.append(
                {
                    "name": "Weekly project review and planning",
                    "essentiality": HabitEssentiality.CRITICAL,
                    "frequency": "weekly",
                    "why": "Planning prevents project drift",
                    "estimated_duration": 30,
                }
            )

        elif self.goal_type == GoalType.OUTCOME:
            suggestions.append(
                {
                    "name": f"Daily action toward {self.title}",
                    "essentiality": HabitEssentiality.ESSENTIAL,
                    "frequency": "daily",
                    "why": "Outcomes require consistent daily steps",
                    "estimated_duration": 20,
                }
            )

        # Timeframe adjusts frequency
        if self.timeframe in [GoalTimeframe.DAILY, GoalTimeframe.WEEKLY]:
            # Short-term goals need intense daily focus
            for suggestion in suggestions:
                if suggestion["frequency"] != "daily":
                    suggestion["essentiality"] = HabitEssentiality.CRITICAL

        # Add supporting habits based on curriculum
        if (len(rels.aligned_learning_path_uids) if rels else 0) > 0:
            suggestions.append(
                {
                    "name": "Complete learning path exercises",
                    "essentiality": HabitEssentiality.SUPPORTING,
                    "frequency": "2x per week",
                    "why": "Curriculum provides structured education",
                    "estimated_duration": 45,
                }
            )

        # Identity-based suggestion
        if self.target_identity:
            suggestions.append(
                {
                    "name": f"Daily identity reinforcement: {self.target_identity}",
                    "essentiality": HabitEssentiality.SUPPORTING,
                    "frequency": "daily",
                    "why": f"Each completion proves you are {self.target_identity}",
                    "estimated_duration": 5,
                }
            )

        return suggestions

    def is_identity_based(self) -> bool:
        """Check if goal uses identity-based motivation."""
        return self.target_identity is not None

    def calculate_identity_evidence(
        self, habit_completion_counts: dict[str, int], rels: GoalRelationships | None = None
    ) -> int:
        """
        Calculate total identity evidence accumulated.

        James Clear: "Every action is a vote for the person you want to become."

        Returns:
            Total # of habit completions that reinforce target identity
        """
        if not self.target_identity or not rels:
            return 0

        # All habit completions count as identity evidence
        all_habit_uids = (
            rels.essential_habit_uids
            + rels.critical_habit_uids
            + rels.supporting_habit_uids
            + rels.optional_habit_uids
        )
        return sum(habit_completion_counts.get(uid, 0) for uid in all_habit_uids)

    def has_sufficient_identity_evidence(self, habit_completion_counts: dict[str, int]) -> bool:
        """
        Check if enough identity evidence has been accumulated.

        James Clear suggests ~40-50 repetitions to form a habit/identity.
        """
        if not self.target_identity or self.identity_evidence_required == 0:
            return False

        evidence = self.calculate_identity_evidence(habit_completion_counts)
        return evidence >= self.identity_evidence_required

    def get_atomic_habits_summary(
        self,
        rels: GoalRelationships | None = None,
        habit_success_rates: dict[str, float] | None = None,
        habit_completion_counts: dict[str, int] | None = None,
    ) -> dict:
        """
        Get complete Atomic Habits analysis for this goal.

        This is the signature method showing how SKUEL implements
        James Clear's philosophy.

        Returns:
            Complete system analysis with actionable insights
        """
        # Calculate totals from rels
        essential_count = len(rels.essential_habit_uids) if rels else 0
        critical_count = len(rels.critical_habit_uids) if rels else 0
        supporting_count = len(rels.supporting_habit_uids) if rels else 0
        optional_count = len(rels.optional_habit_uids) if rels else 0
        total_habits = essential_count + critical_count + supporting_count + optional_count

        return {
            "philosophy": "You do not rise to the level of your goals. You fall to the level of your systems.",
            "system_design": {
                "has_system": self.has_habit_system(),
                "essential_habits": essential_count,
                "critical_habits": critical_count,
                "supporting_habits": supporting_count,
                "optional_habits": optional_count,
                "total_habits": total_habits,
            },
            "system_health": self.diagnose_system_health(
                rels=rels, habit_success_rates=habit_success_rates
            ),
            "system_strength": self.calculate_system_strength(
                rels=rels, habit_success_rates=habit_success_rates
            ),
            "habit_velocity": self.calculate_habit_velocity(
                habit_completion_counts or {}, rels=rels
            ),
            "identity_based": {
                "is_identity_based": self.is_identity_based(),
                "target_identity": self.target_identity,
                "evidence_accumulated": self.calculate_identity_evidence(
                    habit_completion_counts or {}, rels=rels
                ),
                "evidence_required": self.identity_evidence_required,
                "identity_established": self.has_sufficient_identity_evidence(
                    habit_completion_counts or {}
                ),
            },
            "recommendations": self.suggest_essential_habits(rels=rels)
            if not self.has_habit_system()
            else [],
        }

    # ==========================================================================
    # HIERARCHY
    # ==========================================================================

    def is_parent_goal(self, rels: GoalRelationships | None = None) -> bool:
        """Check if this goal has sub-goals."""
        return (len(rels.sub_goal_uids) if rels else 0) > 0

    def is_sub_goal(self) -> bool:
        """Check if this is a sub-goal of another goal."""
        return self.parent_goal_uid is not None

    def is_standalone(self) -> bool:
        """Check if this goal stands alone (no parent or children)."""
        return not self.is_parent_goal() and not self.is_sub_goal()

    # ==========================================================================
    # MILESTONE MANAGEMENT
    # ==========================================================================

    def get_next_milestone(self) -> Milestone | None:
        """Get the next uncompleted milestone."""
        for milestone in self.milestones:
            if not milestone.is_completed:
                return milestone
        return None

    def get_completed_milestones(self) -> list[Milestone]:
        """Get all completed milestones."""
        return [m for m in self.milestones if m.is_completed]

    def milestones_progress(self) -> float:
        """Calculate progress based on milestones."""
        if not self.milestones:
            return 0.0
        completed = len(self.get_completed_milestones())
        return (completed / len(self.milestones)) * 100

    # ==========================================================================
    # STRATEGIC ALIGNMENT
    # ==========================================================================

    def get_urgency_score(self) -> int:
        """
        Calculate urgency score based on timeframe and deadline.
        Higher score = more urgent (0-10 scale).
        """
        base_score = 5

        # Adjust for timeframe
        timeframe_scores = {
            GoalTimeframe.DAILY: 9,
            GoalTimeframe.WEEKLY: 7,
            GoalTimeframe.MONTHLY: 5,
            GoalTimeframe.QUARTERLY: 3,
            GoalTimeframe.YEARLY: 2,
            GoalTimeframe.MULTI_YEAR: 1,
        }
        base_score = timeframe_scores.get(self.timeframe, 5)

        # Adjust for deadline proximity
        days_left = self.get_days_remaining()
        if days_left is not None:
            if days_left <= 7:
                base_score += 3
            elif days_left <= 30:
                base_score += 2
            elif days_left <= 90:
                base_score += 1

        # Adjust for priority
        if self.priority == Priority.CRITICAL:
            base_score += 2
        elif self.priority == Priority.HIGH:
            base_score += 1

        return min(10, base_score)

    def get_importance_score(self, rels: GoalRelationships | None = None) -> int:
        """
        Calculate importance score based on connections and type.
        Higher score = more important (0-10 scale).
        """
        score = 5

        # Learning goals are important for growth
        if self.is_learning_goal():
            score += 2

        # Parent goals are strategic
        if self.is_parent_goal(rels):
            score += 1

        # Principle-driven goals are value-aligned
        principle_count = len(rels.guiding_principle_uids) if rels else 0
        if principle_count > 0:
            score += 1

        # Goals with many supporting elements are well-integrated
        total_connections = (
            (len(rels.required_knowledge_uids) if rels else 0)
            + (len(rels.supporting_habit_uids) if rels else 0)
            + principle_count
        )
        if total_connections >= 5:
            score += 1

        return min(10, score)

    # ==========================================================================
    # RELATIONSHIP COMPREHENSION (Phase 1: Making Connections Visible)
    # ==========================================================================

    def explain_existence(self, rels: GoalRelationships | None = None) -> str:
        """
        WHY does this goal exist? One-sentence reasoning.

        Makes the invisible reasoning behind goal creation visible and comprehensible.

        Returns:
            Human-readable explanation of why this goal exists, including:
            - What choice created it (if any)
            - Which principles guide it (if any)
            - How it fits in the larger system
        """
        parts = [f"{self.title}"]

        if self.inspired_by_choice_uid:
            parts.append(f"Inspired by choice: {self.inspired_by_choice_uid}")

        if rels and rels.guiding_principle_uids:
            parts.append(f"Guided by {len(rels.guiding_principle_uids)} principles")

        # Add system context
        if self.has_habit_system():
            essential_count = len(rels.essential_habit_uids) if rels else 0
            parts.append(f"Supported by system with {essential_count} essential habits")

        return ". ".join(parts)

    def get_relationship_summary(self, rels: GoalRelationships | None = None) -> dict:
        """
        Get comprehensive relationship context for this goal.

        Returns:
            Dictionary with:
            - explanation: One-sentence existence explanation
            - derivation: Choice reasoning (if exists)
            - guidances: List of principle manifestations
            - habit_system: System strength and composition
        """
        # Calculate totals from rels
        essential_count = len(rels.essential_habit_uids) if rels else 0
        critical_count = len(rels.critical_habit_uids) if rels else 0
        supporting_count = len(rels.supporting_habit_uids) if rels else 0
        optional_count = len(rels.optional_habit_uids) if rels else 0
        total_habits = essential_count + critical_count + supporting_count + optional_count

        return {
            "explanation": self.explain_existence(rels=rels),
            "habit_system": {
                "exists": self.has_habit_system(),
                "essential_count": essential_count,
                "critical_count": critical_count,
                "supporting_count": supporting_count,
                "total_count": total_habits,
            },
            "upstream_count": len(self.get_upstream_influences(rels=rels)),
            "downstream_count": len(self.get_downstream_impacts(rels=rels)),
        }

    # ==========================================================================
    # GRAPHENTITY PROTOCOL IMPLEMENTATION (Phase 2)
    # ==========================================================================

    def get_upstream_influences(self, rels: GoalRelationships | None = None) -> list[dict]:
        """
        WHAT shaped this goal? Entities that influenced its creation.

        Returns:
            List of upstream entities (choices, principles, parent goals, knowledge)
        """
        influences = []

        # 1. Choice that inspired this goal
        if self.inspired_by_choice_uid:
            influences.append(
                {
                    "uid": self.inspired_by_choice_uid,
                    "entity_type": "choice",
                    "relationship_type": "inspired_by",
                    "reasoning": None,
                    "strength": None,
                }
            )

        # 2. Guiding principles (from graph relationships)
        if rels:
            influences.extend(
                [
                    {
                        "uid": principle_uid,
                        "entity_type": "principle",
                        "relationship_type": "guided_by",
                        "reasoning": None,
                        "strength": None,
                    }
                    for principle_uid in rels.guiding_principle_uids
                ]
            )

        # 4. Parent goal (if sub-goal)
        if self.parent_goal_uid:
            influences.append(
                {
                    "uid": self.parent_goal_uid,
                    "entity_type": "goal",
                    "relationship_type": "spawned_by",
                    "reasoning": "Sub-goal of parent",
                    "strength": None,
                }
            )

        # 5. Required knowledge
        influences.extend(
            [
                {
                    "uid": knowledge_uid,
                    "entity_type": "knowledge",
                    "relationship_type": "requires",
                    "reasoning": "Prerequisite knowledge",
                    "strength": None,
                }
                for knowledge_uid in (rels.required_knowledge_uids if rels else [])
            ]
        )

        # 6. Learning path source
        if self.source_learning_path_uid:
            influences.append(
                {
                    "uid": self.source_learning_path_uid,
                    "entity_type": "learning_path",
                    "relationship_type": "curriculum_driven",
                    "reasoning": "Generated from learning path",
                    "strength": None,
                }
            )

        return influences

    def get_downstream_impacts(self, rels: GoalRelationships | None = None) -> list[dict]:
        """
        WHAT does this goal shape? Entities influenced by this goal.

        Returns:
            List of downstream entities (habits, tasks, sub-goals)
        """
        impacts = []

        # 1. Essential habits (strongest impact)
        if rels:
            impacts.extend(
                [
                    {
                        "uid": habit_uid,
                        "entity_type": "habit",
                        "relationship_type": "essential_support",
                        "reasoning": "Goal is impossible without this habit",
                        "essentiality": "essential",
                        "strength": 1.0,
                    }
                    for habit_uid in rels.essential_habit_uids
                ]
            )

            # 2. Critical habits
            impacts.extend(
                [
                    {
                        "uid": habit_uid,
                        "entity_type": "habit",
                        "relationship_type": "critical_support",
                        "reasoning": "Goal is very difficult without this habit",
                        "essentiality": "critical",
                        "strength": 0.8,
                    }
                    for habit_uid in rels.critical_habit_uids
                ]
            )

        # 3. Supporting habits (legacy + new)
        all_supporting = set(rels.supporting_habit_uids if rels else [])
        impacts.extend(
            [
                {
                    "uid": habit_uid,
                    "entity_type": "habit",
                    "relationship_type": "supporting",
                    "reasoning": "Habit makes goal easier to achieve",
                    "essentiality": "supporting",
                    "strength": 0.5,
                }
                for habit_uid in all_supporting
            ]
        )

        # 4. Optional habits
        if rels:
            impacts.extend(
                [
                    {
                        "uid": habit_uid,
                        "entity_type": "habit",
                        "relationship_type": "optional_support",
                        "reasoning": "Habit tangentially helps goal",
                        "essentiality": "optional",
                        "strength": 0.2,
                    }
                    for habit_uid in rels.optional_habit_uids
                ]
            )

        # 5. Sub-goals
        impacts.extend(
            [
                {
                    "uid": sub_goal_uid,
                    "entity_type": "goal",
                    "relationship_type": "spawns",
                    "reasoning": "Sub-goal created to achieve this goal",
                    "strength": None,
                }
                for sub_goal_uid in (rels.sub_goal_uids if rels else [])
            ]
        )

        # Note: Tasks would be added here if we had task UIDs
        # Future enhancement: Track tasks created for this goal

        return impacts

    # ==========================================================================
    # CONVERSIONS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: GoalDTO) -> Goal:
        """
        Create immutable Goal from mutable DTO.

        GRAPH-NATIVE: UID list fields are NOT transferred from DTO to domain model.
        Relationships exist only as Neo4j edges, queried via service layer.
        """
        # Convert milestone DTOs to immutable Milestones
        milestones = tuple(Milestone(**m) if isinstance(m, dict) else m for m in dto.milestones)

        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            title=dto.title,
            description=dto.description,
            vision_statement=dto.vision_statement,
            goal_type=dto.goal_type,
            domain=dto.domain,
            timeframe=dto.timeframe,
            measurement_type=dto.measurement_type,
            target_value=dto.target_value,
            current_value=dto.current_value,
            unit_of_measurement=dto.unit_of_measurement,
            start_date=dto.start_date,
            target_date=dto.target_date,
            achieved_date=dto.achieved_date,
            # UID list fields REMOVED - relationships stored as graph edges only
            parent_goal_uid=dto.parent_goal_uid,
            # sub_goal_uids REMOVED - use (goal)-[:HAS_SUBGOAL]->(subgoal)
            # essential/critical/supporting/optional_habit_uids REMOVED - use (goal)-[:REQUIRES_HABIT {essentiality}]->(habit)
            target_identity=getattr(dto, "target_identity", None),
            identity_evidence_required=getattr(dto, "identity_evidence_required", 0),
            source_learning_path_uid=getattr(dto, "source_learning_path_uid", None),
            # aligned_learning_path_uids REMOVED - use (goal)-[:ALIGNED_WITH_PATH]->(lp)
            # requires_completion_of_paths REMOVED - use (goal)-[:REQUIRES_PATH_COMPLETION]->(lp)
            curriculum_driven=getattr(dto, "curriculum_driven", False),
            inspired_by_choice_uid=getattr(dto, "inspired_by_choice_uid", None),
            selected_choice_option_uid=getattr(dto, "selected_choice_option_uid", None),
            milestones=milestones,
            progress_percentage=dto.progress_percentage,
            last_progress_update=dto.last_progress_update,
            progress_history=tuple(dto.progress_history),
            why_important=dto.why_important,
            success_criteria=dto.success_criteria,
            potential_obstacles=tuple(dto.potential_obstacles),
            strategies=tuple(dto.strategies),
            status=dto.status,
            priority=dto.priority,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            tags=tuple(dto.tags),
            metadata=dto.metadata,  # Copy metadata from DTO (rich context storage)
        )

    def to_dto(self) -> GoalDTO:
        """
        Convert to mutable DTO for updates.

        GRAPH-NATIVE: UID list fields set to empty lists.
        Service layer must populate from graph queries before API serialization.
        """

        # Convert milestones to dicts
        milestone_dicts = [
            {
                "uid": m.uid,
                "title": m.title,
                "description": m.description,
                "target_date": m.target_date,
                "target_value": m.target_value,
                "achieved_date": m.achieved_date,
                "is_completed": m.is_completed,
                "required_knowledge_uids": list(m.required_knowledge_uids),
                "unlocked_knowledge_uids": list(m.unlocked_knowledge_uids),
            }
            for m in self.milestones
        ]

        # GRAPH-NATIVE: Relationship UIDs removed from DTO (Phase 3B migration)
        # Query relationships via service.relationships:
        #   - required_knowledge_uids: get_related_uids(uid, "REQUIRES_KNOWLEDGE", "outgoing")
        #   - supporting_habit_uids: get_related_uids(uid, "REQUIRES_HABIT", properties={"essentiality": "supporting"})
        #   - guiding_principle_uids: get_related_uids(uid, "GUIDED_BY_PRINCIPLE", "outgoing")
        #   - sub_goal_uids: get_related_uids(uid, "HAS_SUBGOAL", "outgoing")
        #   - essential/critical/optional_habit_uids: get_related_uids(uid, "REQUIRES_HABIT", properties={"essentiality": "..."})
        #   - aligned_learning_path_uids: get_related_uids(uid, "ALIGNED_WITH_PATH", "outgoing")
        #   - requires_completion_of_paths: get_related_uids(uid, "REQUIRES_PATH_COMPLETION", "outgoing")
        #
        # See: /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md

        return GoalDTO(
            uid=self.uid,
            user_uid=self.user_uid,
            title=self.title,
            description=self.description,
            vision_statement=self.vision_statement,
            goal_type=self.goal_type,
            domain=self.domain,
            timeframe=self.timeframe,
            measurement_type=self.measurement_type,
            target_value=self.target_value,
            current_value=self.current_value,
            unit_of_measurement=self.unit_of_measurement,
            start_date=self.start_date,
            target_date=self.target_date,
            achieved_date=self.achieved_date,
            parent_goal_uid=self.parent_goal_uid,
            target_identity=self.target_identity,
            identity_evidence_required=self.identity_evidence_required,
            source_learning_path_uid=self.source_learning_path_uid,
            curriculum_driven=self.curriculum_driven,
            inspired_by_choice_uid=self.inspired_by_choice_uid,
            selected_choice_option_uid=self.selected_choice_option_uid,
            milestones=milestone_dicts,
            progress_percentage=self.progress_percentage,
            last_progress_update=self.last_progress_update,
            progress_history=list(self.progress_history),
            why_important=self.why_important,
            success_criteria=self.success_criteria,
            potential_obstacles=list(self.potential_obstacles),
            strategies=list(self.strategies),
            status=self.status,
            priority=self.priority,
            created_at=self.created_at,
            updated_at=self.updated_at,
            tags=list(self.tags),
            metadata=self.metadata,  # Copy metadata to DTO (rich context storage)
        )

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_supporting_activities_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for supporting activities

        Finds tasks, habits, and learning paths that support this goal.

        Args:
            depth: Maximum activity graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.HIERARCHICAL, depth=depth
        )

    def build_knowledge_requirements_query(self, depth: int = 3) -> str:
        """
        Build pure Cypher query for knowledge requirements

        Finds all knowledge needed to achieve this goal.

        Args:
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PREREQUISITE, depth=depth
        )

    def build_milestone_path_query(self) -> str:
        """
        Build pure Cypher query for milestone path

        Finds milestones and their knowledge requirements.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.HIERARCHICAL, depth=GraphDepth.NEIGHBORHOOD
        )

    def build_principle_alignment_query(self) -> str:
        """
        Build pure Cypher query for principle alignment

        Finds principles this goal embodies and alignment patterns.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.RELATIONSHIP, depth=GraphDepth.NEIGHBORHOOD
        )

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Get suggested QueryIntent based on goal characteristics.

        Business rules:
        - Learning goals → PREREQUISITE (knowledge requirements)
        - Mastery goals → PRACTICE (skill development)
        - Milestone goals → HIERARCHICAL (progress tracking)
        - Process goals → PRACTICE (habit reinforcement)
        - Outcome goals → GOAL_ACHIEVEMENT (comprehensive analysis)
        - Default → GOAL_ACHIEVEMENT (achievement path analysis)

        Returns:
            Recommended QueryIntent for this goal
        """
        if self.goal_type == GoalType.LEARNING:
            return QueryIntent.PREREQUISITE

        if self.goal_type == GoalType.MASTERY:
            return QueryIntent.PRACTICE

        if self.goal_type == GoalType.MILESTONE:
            return QueryIntent.HIERARCHICAL

        if self.goal_type == GoalType.PROCESS:
            return QueryIntent.PRACTICE

        # OUTCOME goals and default: use GOAL_ACHIEVEMENT for comprehensive analysis
        return QueryIntent.GOAL_ACHIEVEMENT


# Import GoalDTO after Goal class is defined to avoid circular import
from core.models.goal.goal_dto import GoalDTO  # noqa: E402

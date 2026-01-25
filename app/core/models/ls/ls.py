"""
LearningStep Domain Model (Tier 3 - Core)
==========================================

Immutable domain model for learning steps with business logic.

LearningStep represents a single step in a learning path/ journey.

Core Architecture:
- LearningStep (ls) is one of SKUEL's three core curriculum entities (ku, ls, lp)
- Can stand alone or be part of a LearningPath
- Acts as a curated bundle of knowledge with practice opportunities
- Links to principles, choices, habits, goals, tasks, and events

Phase 1-4 Integration (October 4, 2025):
- Phase 1: APOC query building for step context
- Phase 2: Domain Intelligence models for learning analytics
- Phase 3: GraphContext for cross-domain intelligence
- Phase 4: Practice opportunity discovery
"""

__version__ = "3.0"  # Standalone extraction with KnowledgeCluster merge

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth
from core.models.query import QueryIntent

# Phase 1: Query Infrastructure
from core.models.query.graph_traversal import build_graph_context_query
from core.models.shared_enums import Domain, Priority

if TYPE_CHECKING:
    from core.models.ls.ls_relationships import LsRelationships

    from .ls_dto import LearningStepDTO


class StepDifficulty(str, Enum):
    """Difficulty level of a learning step."""

    TRIVIAL = "trivial"  # < 30 minutes
    EASY = "easy"  # 30-60 minutes
    MODERATE = "moderate"  # 1-2 hours
    CHALLENGING = "challenging"  # 2-4 hours
    ADVANCED = "advanced"  # 4+ hours


class StepStatus(str, Enum):
    """Current status of a learning step."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MASTERED = "mastered"
    ARCHIVED = "archived"


class MasteryLevel(str, Enum):
    """Levels of mastery for learning steps."""

    NOVICE = "novice"
    BEGINNER = "beginner"
    COMPETENT = "competent"
    PROFICIENT = "proficient"
    EXPERT = "expert"


@dataclass(frozen=True)
class Ls:
    """
    Immutable domain model for a Learning Step.

    Ls merges the concepts of:
    - PathStep: A step in a learning path sequence
    - KnowledgeCluster: A curated bundle of knowledge units

    This creates a powerful, standalone curriculum entity that can:
    - Exist independently as a learning module
    - Be sequenced within an Lp (Learning Path)
    - Link to practice opportunities (habits, tasks, events)
    - Reference guiding principles and choices

    Naming Convention (matches Ku, Lp):
    - Class name 'Ls' matches module path 'core.models.ls' and UID prefix 'ls'
    - Follows SKUEL's three-tier curriculum architecture: Ku, Ls, Lp
    """

    # Identity
    uid: str  # Format: ls:path-name:step-id or ls:standalone-id
    title: str
    intent: str  # Learning objective / what learner will achieve
    description: str | None = None

    # Knowledge Content
    primary_knowledge_uids: tuple[str, ...] = ()  # Main knowledge units (ku:*)
    supporting_knowledge_uids: tuple[str, ...] = ()  # Supporting/optional knowledge

    # Path Integration (optional - can be standalone)
    learning_path_uid: str | None = None  # Parent path (lp:*) if part of sequence
    sequence: int | None = None  # Order in path (if sequenced)

    # Prerequisites & Dependencies - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (ls)-[:REQUIRES_STEP]->(ls)
    # Graph relationship: (ls)-[:REQUIRES_KNOWLEDGE]->(ku)

    # Learning Guidance - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (ls)-[:GUIDED_BY_PRINCIPLE]->(principle)
    # Graph relationship: (ls)-[:OFFERS_CHOICE]->(choice)

    # Practice Integration - GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (ls)-[:BUILDS_HABIT]->(habit)
    # Graph relationship: (ls)-[:ASSIGNS_TASK]->(task)
    # Graph relationship: (ls)-[:SCHEDULES_EVENT]->(event)

    # Mastery & Progress
    mastery_threshold: float = 0.7  # Required mastery level (0.0-1.0)
    current_mastery: float = 0.0  # Current progress (state - for display only)
    estimated_hours: float = 1.0
    difficulty: StepDifficulty = StepDifficulty.MODERATE

    # Status
    status: StepStatus = StepStatus.NOT_STARTED
    completed: bool = False
    completed_at: datetime | None = None  # type: ignore[assignment]

    # Domain & Priority
    domain: Domain = Domain.PERSONAL
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    notes: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = None  # type: ignore[assignment]  # Rich context storage (graph neighborhoods, etc.)

    def __post_init__(self) -> None:
        """Set defaults for datetime fields."""
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

    # ==========================================================================
    # KNOWLEDGE CARRIER PROTOCOL IMPLEMENTATION
    # ==========================================================================
    # LS implements KnowledgeCarrier and CurriculumCarrier.
    # LS IS curriculum - it always returns full relevance.

    def knowledge_relevance(self) -> float:
        """
        How relevant is knowledge to this entity? (0.0-1.0)

        LS IS curriculum - always returns 1.0.

        Returns:
            1.0 (maximum relevance - LS is a curriculum container)
        """
        return 1.0

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """
        Get all knowledge UIDs this entity carries.

        LS aggregates knowledge from primary and supporting KUs.
        Delegates to get_all_knowledge_uids().

        Returns:
            tuple of ku-prefixed UIDs (primary + supporting)
        """
        return self.get_all_knowledge_uids()

    # ==========================================================================
    # IDENTITY & CLASSIFICATION
    # ==========================================================================

    def is_standalone(self) -> bool:
        """Check if this step exists independently (not part of a path)."""
        return self.learning_path_uid is None

    def is_sequenced(self) -> bool:
        """Check if this step is part of a sequenced learning path."""
        return self.learning_path_uid is not None and self.sequence is not None

    def is_foundational(self) -> bool:
        """
        Check if this is a foundational step (no prerequisites).

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:REQUIRES_STEP]->() = 0 AND COUNT (ls)-[:REQUIRES_KNOWLEDGE]->() = 0
        Service: LsRelationshipService.is_foundational(ls_uid)
        """
        return True  # Placeholder - use service layer

    # ==========================================================================
    # KNOWLEDGE INTEGRATION
    # ==========================================================================

    def get_all_knowledge_uids(self) -> tuple[str, ...]:
        """Get all knowledge UIDs (primary + supporting)."""
        return self.primary_knowledge_uids + self.supporting_knowledge_uids

    def knowledge_count(self) -> int:
        """Count total knowledge units in this step."""
        return len(self.primary_knowledge_uids) + len(self.supporting_knowledge_uids)

    def has_knowledge(self, knowledge_uid: str) -> bool:
        """Check if step includes specific knowledge unit."""
        return knowledge_uid in self.get_all_knowledge_uids()

    def is_knowledge_rich(self) -> bool:
        """Check if step has substantial knowledge content."""
        return self.knowledge_count() >= 3

    # ==========================================================================
    # PRACTICE INTEGRATION
    # ==========================================================================

    def has_practice_opportunities(self) -> bool:
        """
        Check if step has linked practice (habits/tasks/events).

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:BUILDS_HABIT|ASSIGNS_TASK|SCHEDULES_EVENT]->() > 0
        Service: LsRelationshipService.has_practice_opportunities(ls_uid)
        """
        return False  # Placeholder - use service layer

    def practice_element_count(self) -> int:
        """
        Count total practice elements.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:BUILDS_HABIT|ASSIGNS_TASK|SCHEDULES_EVENT]->()
        Service: LsRelationshipService.practice_element_count(ls_uid)
        """
        return 0  # Placeholder - use service layer

    def get_practice_summary(self) -> dict:
        """
        Get summary of practice opportunities.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Service: LsRelationshipService.get_practice_summary(ls_uid)
        """
        return {
            "habits": 0,  # Placeholder - use service layer
            "tasks": 0,  # Placeholder - use service layer
            "events": 0,  # Placeholder - use service layer
            "total": 0,  # Placeholder - use service layer
        }

    def get_practice_tasks(self) -> tuple[str, ...]:
        """
        Get all task UIDs for practicing this learning step.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: MATCH (ls)-[:ASSIGNS_TASK]->(task) RETURN task.uid
        Service: LsRelationshipService.get_practice_tasks(ls_uid)
        """
        return ()  # Placeholder - use service layer

    def get_practice_habits(self) -> tuple[str, ...]:
        """
        Get all habit UIDs for reinforcing this learning step.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: MATCH (ls)-[:BUILDS_HABIT]->(habit) RETURN habit.uid
        Service: LsRelationshipService.get_practice_habits(ls_uid)
        """
        return ()  # Placeholder - use service layer

    def get_practice_events(self) -> tuple[str, ...]:
        """
        Get all event template UIDs for this learning step.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: MATCH (ls)-[:SCHEDULES_EVENT]->(event) RETURN event.uid
        Service: LsRelationshipService.get_practice_events(ls_uid)
        """
        return ()  # Placeholder - use service layer

    def requires_habit_practice(self) -> bool:
        """
        Check if step requires habit formation.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:BUILDS_HABIT]->() > 0
        Service: LsRelationshipService.requires_habit_practice(ls_uid)
        """
        return False  # Placeholder - use service layer

    def requires_task_practice(self) -> bool:
        """
        Check if step requires task completion.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:ASSIGNS_TASK]->() > 0
        Service: LsRelationshipService.requires_task_practice(ls_uid)
        """
        return False  # Placeholder - use service layer

    def has_complete_practice_suite(self) -> bool:
        """
        Check if step has all practice types (tasks, habits, events).

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: Check counts for all three relationship types
        Service: LsRelationshipService.has_complete_practice_suite(ls_uid)
        """
        return False  # Placeholder - use service layer

    def practice_completeness_score(self) -> float:
        """
        Calculate practice completeness (0.0-1.0).

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual calculation.
        Service: LsRelationshipService.practice_completeness_score(ls_uid)

        Full practice suite = 1.0, partial = proportional score.
        """
        return 0.0  # Placeholder - use service layer

    # ==========================================================================
    # GUIDANCE & DECISION-MAKING (INSPIRE via choices)
    # ==========================================================================

    def has_guidance(self) -> bool:
        """
        Check if step has principles or choices defined.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:GUIDED_BY_PRINCIPLE|OFFERS_CHOICE]->() > 0
        Service: LsRelationshipService.has_guidance(ls_uid)
        """
        return False  # Placeholder - use service layer

    def guidance_count(self) -> int:
        """
        Count guidance elements (principles + choices).

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:GUIDED_BY_PRINCIPLE|OFFERS_CHOICE]->()
        Service: LsRelationshipService.guidance_count(ls_uid)
        """
        return 0  # Placeholder - use service layer

    def presents_choices(self) -> bool:
        """
        Check if step presents inspirational choices to learner.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:OFFERS_CHOICE]->() > 0
        Service: LsRelationshipService.presents_choices(ls_uid)
        """
        return False  # Placeholder - use service layer

    def has_principles(self) -> bool:
        """
        Check if step has guiding principles.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:GUIDED_BY_PRINCIPLE]->() > 0
        Service: LsRelationshipService.has_principles(ls_uid)
        """
        return False  # Placeholder - use service layer

    def get_choice_uids(self) -> tuple[str, ...]:
        """
        Get all choices presented in this learning step.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: MATCH (ls)-[:OFFERS_CHOICE]->(choice) RETURN choice.uid
        Service: LsRelationshipService.get_choice_uids(ls_uid)
        """
        return ()  # Placeholder - use service layer

    def get_principle_uids(self) -> tuple[str, ...]:
        """
        Get all guiding principles for this step.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: MATCH (ls)-[:GUIDED_BY_PRINCIPLE]->(principle) RETURN principle.uid
        Service: LsRelationshipService.get_principle_uids(ls_uid)
        """
        return ()  # Placeholder - use service layer

    def is_inspirational_step(self) -> bool:
        """
        Check if step is designed to inspire (presents possibilities).

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:OFFERS_CHOICE]->() >= 2
        Service: LsRelationshipService.is_inspirational_step(ls_uid)

        Inspirational steps help learners discover what's possible,
        aligning with SKUEL's mission to Inspire, Motivate, Educate.
        """
        return False  # Placeholder - use service layer

    def get_inspiration_summary(self) -> dict:
        """
        Get summary of inspirational elements in this step.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Service: LsRelationshipService.get_inspiration_summary(ls_uid)

        Returns:
            Dictionary with choice and principle information
        """
        return {
            "presents_choices": False,  # Placeholder - use service layer
            "choice_count": 0,  # Placeholder - use service layer
            "choices": [],  # Placeholder - use service layer
            "has_principles": False,  # Placeholder - use service layer
            "principle_count": 0,  # Placeholder - use service layer
            "principles": [],  # Placeholder - use service layer
            "is_inspirational": False,  # Placeholder - use service layer
            "guidance_strength": 0.0,  # Placeholder - use service layer
        }

    def calculate_guidance_strength(self) -> float:
        """
        Calculate how well this step guides the learner (0-1).

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual calculation.
        Service: LsRelationshipService.calculate_guidance_strength(ls_uid)

        Higher scores indicate strong guidance through principles and choices.
        """
        return 0.0  # Placeholder - use service layer

    # ==========================================================================
    # PREREQUISITES & READINESS
    # ==========================================================================

    def has_prerequisites(self) -> bool:
        """
        Check if step has any prerequisites.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:REQUIRES_STEP|REQUIRES_KNOWLEDGE]->() > 0
        Service: LsRelationshipService.has_prerequisites(ls_uid)
        """
        return False  # Placeholder - use service layer

    def prerequisite_count(self) -> int:
        """
        Count total prerequisites.

        GRAPH-NATIVE PLACEHOLDER: Use service layer for actual query.
        Query: COUNT (ls)-[:REQUIRES_STEP|REQUIRES_KNOWLEDGE]->()
        Service: LsRelationshipService.prerequisite_count(ls_uid)
        """
        return 0  # Placeholder - use service layer

    # ==========================================================================
    # MASTERY & PROGRESS
    # ==========================================================================

    def is_mastered(self) -> bool:
        """Check if mastery threshold is met."""
        return self.current_mastery >= self.mastery_threshold

    def progress_percentage(self) -> float:
        """Calculate progress as percentage."""
        return min(100.0, (self.current_mastery / self.mastery_threshold) * 100)

    def is_in_progress(self) -> bool:
        """Check if step is currently being worked on."""
        return self.status == StepStatus.IN_PROGRESS

    def is_completed(self) -> bool:
        """Check if step is marked as completed."""
        return self.completed or self.status == StepStatus.COMPLETED

    # ==========================================================================
    # DIFFICULTY & EFFORT
    # ==========================================================================

    def get_effort_score(self) -> float:
        """
        Calculate effort score based on difficulty and estimated hours.

        Returns:
            Score from 1-10 indicating effort required
        """
        difficulty_scores = {
            StepDifficulty.TRIVIAL: 1,
            StepDifficulty.EASY: 2,
            StepDifficulty.MODERATE: 3,
            StepDifficulty.CHALLENGING: 4,
            StepDifficulty.ADVANCED: 5,
        }

        base_score = difficulty_scores.get(self.difficulty, 3)
        time_factor = min(2.0, self.estimated_hours / 2.0)  # Cap time multiplier at 2x

        return min(10.0, base_score * time_factor)

    def is_quick_win(self) -> bool:
        """Check if this is a quick win (easy + short)."""
        return self.difficulty == StepDifficulty.TRIVIAL and self.estimated_hours < 1.0

    # ==========================================================================
    # CONVERSIONS
    # ==========================================================================

    @classmethod
    def from_dto(cls, dto: "LearningStepDTO") -> "Ls":
        """
        Create immutable LearningStep from mutable DTO.

        GRAPH-NATIVE: UID list fields are NOT transferred from DTO to domain model.
        Relationships exist only as Neo4j edges, queried via service layer.
        """
        return cls(
            uid=dto.uid,
            title=dto.title,
            intent=dto.intent,
            description=dto.description,
            primary_knowledge_uids=tuple(dto.primary_knowledge_uids),
            supporting_knowledge_uids=tuple(dto.supporting_knowledge_uids),
            learning_path_uid=dto.learning_path_uid,
            sequence=dto.sequence,
            # UID list fields REMOVED - relationships stored as graph edges only:
            # prerequisite_step_uids REMOVED - use (ls)-[:REQUIRES_STEP]->(ls)
            # prerequisite_knowledge_uids REMOVED - use (ls)-[:REQUIRES_KNOWLEDGE]->(ku)
            # principle_uids REMOVED - use (ls)-[:GUIDED_BY_PRINCIPLE]->(principle)
            # choice_uids REMOVED - use (ls)-[:OFFERS_CHOICE]->(choice)
            # habit_uids REMOVED - use (ls)-[:BUILDS_HABIT]->(habit)
            # task_uids REMOVED - use (ls)-[:ASSIGNS_TASK]->(task)
            # event_template_uids REMOVED - use (ls)-[:SCHEDULES_EVENT]->(event)
            mastery_threshold=dto.mastery_threshold,
            current_mastery=dto.current_mastery,
            estimated_hours=dto.estimated_hours,
            difficulty=dto.difficulty,
            status=dto.status,
            completed=dto.completed,
            completed_at=dto.completed_at,
            domain=dto.domain,
            priority=dto.priority,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            notes=dto.notes,
            tags=tuple(dto.tags),
            metadata=getattr(dto, "metadata", {})
            or {},  # Copy metadata from DTO (rich context storage)
        )

    def to_dto(self) -> "LearningStepDTO":
        """
        Convert to mutable DTO for updates.

        Phase 3 Graph-Native: Relationship fields (prerequisite_step_uids, principle_uids,
        habit_uids, etc.) are NOT in DTO. Use LsRelationships.fetch() to get
        relationship data when needed.
        """
        from .ls_dto import LearningStepDTO

        return LearningStepDTO(
            uid=self.uid,
            title=self.title,
            intent=self.intent,
            description=self.description,
            primary_knowledge_uids=list(self.primary_knowledge_uids),
            supporting_knowledge_uids=list(self.supporting_knowledge_uids),
            learning_path_uid=self.learning_path_uid,
            sequence=self.sequence,
            # Phase 3: Relationship fields removed from DTO - fetch via LsRelationships
            mastery_threshold=self.mastery_threshold,
            current_mastery=self.current_mastery,
            estimated_hours=self.estimated_hours,
            difficulty=self.difficulty,
            status=self.status,
            completed=self.completed,
            completed_at=self.completed_at,
            domain=self.domain,
            priority=self.priority,
            created_at=self.created_at,
            updated_at=self.updated_at,
            notes=self.notes,
            tags=list(self.tags),
            metadata=self.metadata,  # Copy metadata to DTO (rich context storage)
        )

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_knowledge_context_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for knowledge context

        Finds all knowledge units and their relationships for this step.

        Args:
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.HIERARCHICAL, depth=depth
        )

    def build_practice_query(self) -> str:
        """
        Build pure Cypher query for practice opportunities

        Finds habits, tasks, and events linked to this step.

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PRACTICE, depth=GraphDepth.NEIGHBORHOOD
        )

    def build_prerequisite_query(self, depth: int = 3) -> str:
        """
        Build pure Cypher query for prerequisites

        Finds all prerequisite steps and knowledge.

        Args:
            depth: Maximum prerequisite depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.uid, intent=QueryIntent.PREREQUISITE, depth=depth
        )

    def get_suggested_query_intent(self, rels: "LsRelationships | None" = None) -> QueryIntent:
        """
        Get suggested QueryIntent based on step characteristics.

        Args:
            rels: Relationship data (required for prerequisite check)

        Business rules:
        - Steps with prerequisites → PREREQUISITE (understand foundation)
        - Steps with practice elements → PRACTICE (reinforcement)
        - Sequenced steps → HIERARCHICAL (path progression)
        - Standalone steps → EXPLORATORY (discovery)

        Returns:
            Recommended QueryIntent for this step
        """
        if (len(rels.prerequisite_step_uids) if rels else 0) > 0:
            return QueryIntent.PREREQUISITE

        if self.has_practice_opportunities():
            return QueryIntent.PRACTICE

        if self.is_sequenced():
            return QueryIntent.HIERARCHICAL

        return QueryIntent.EXPLORATORY

    # ==========================================================================
    # PHASE 2: GRAPHENTITY PROTOCOL IMPLEMENTATION
    # ==========================================================================

    def explain_existence(self) -> str:
        """
        WHY does this learning step exist? One-sentence reasoning.

        Returns:
            Human-readable explanation of learning step's purpose and context
        """
        parts = [self.title]

        # Learning objective
        parts.append(f"Intent: {self.intent}")

        # Path context
        if self.is_sequenced():
            parts.append(f"Step #{self.sequence} in path {self.learning_path_uid}")
        elif self.is_standalone():
            parts.append("Standalone learning module")

        # Knowledge scope
        knowledge_count = len(self.primary_knowledge_uids) + len(self.supporting_knowledge_uids)
        if knowledge_count > 0:
            parts.append(f"Covers {knowledge_count} knowledge unit(s)")

        # Practice integration (GRAPH-NATIVE PLACEHOLDER)
        # Query: COUNT (ls)-[:BUILDS_HABIT|ASSIGNS_TASK|SCHEDULES_EVENT]->()
        # Use service layer: LsRelationshipService.practice_element_count(ls_uid)

        # Difficulty and time
        parts.append(f"{self.difficulty.value} difficulty, ~{self.estimated_hours}h")

        # Progress indicator
        if self.completed:
            parts.append("Completed")
        elif self.current_mastery > 0:
            parts.append(f"{int(self.current_mastery * 100)}% mastery")

        return ". ".join(parts)

    def get_upstream_influences(self) -> list[dict]:
        """
        WHAT shaped this learning step? Entities that influenced its creation.

        Returns:
            List of dicts representing upstream influences:
            - Parent learning path
            - Prerequisite steps
            - Prerequisite knowledge
            - Guiding principles
            - Choices that led to this step
        """
        influences = []

        # 1. Parent learning path (if sequenced)
        if self.learning_path_uid:
            influences.append(
                {
                    "uid": self.learning_path_uid,
                    "entity_type": "learning_path",
                    "relationship_type": "part_of",
                    "reasoning": f"Step #{self.sequence} in learning path sequence",
                    "strength": 1.0,
                    "sequence": self.sequence,
                }
            )

        # GRAPH-NATIVE PLACEHOLDER: Use service layer for prerequisite steps, knowledge, principles, choices
        # 2. Prerequisite steps
        # Query: MATCH (ls)-[:REQUIRES_STEP]->(prereq_ls) RETURN prereq_ls.uid
        # Service: LsRelationshipService.get_prerequisite_steps(ls_uid)

        # 3. Prerequisite knowledge
        # Query: MATCH (ls)-[:REQUIRES_KNOWLEDGE]->(ku) RETURN ku.uid
        # Service: LsRelationshipService.get_prerequisite_knowledge(ls_uid)

        # 4. Guiding principles
        # Query: MATCH (ls)-[:GUIDED_BY_PRINCIPLE]->(p) RETURN p.uid
        # Service: LsRelationshipService.get_principle_uids(ls_uid)

        # 5. Choices offered in step
        # Query: MATCH (ls)-[:OFFERS_CHOICE]->(c) RETURN c.uid
        # Service: LsRelationshipService.get_choice_uids(ls_uid)

        # 6. Domain context
        influences.append(
            {
                "uid": f"domain:{self.domain.value}",
                "entity_type": "domain",
                "relationship_type": "categorized_by",
                "reasoning": f"Learning step belongs to {self.domain.value} domain",
                "strength": 1.0,
            }
        )

        return influences

    def get_downstream_impacts(self) -> list[dict]:
        """
        WHAT does this learning step shape? Entities influenced by this step.

        Returns:
            List of dicts representing downstream impacts:
            - Primary knowledge taught
            - Supporting knowledge provided
            - Habits built
            - Tasks assigned
            - Events scheduled
        """
        impacts = []

        # 1. Primary knowledge taught
        impacts.extend(
            [
                {
                    "uid": knowledge_uid,
                    "entity_type": "knowledge",
                    "relationship_type": "teaches",
                    "reasoning": "Core knowledge unit taught in this step",
                    "strength": 1.0,
                }
                for knowledge_uid in self.primary_knowledge_uids
            ]
        )

        # 2. Supporting knowledge provided
        impacts.extend(
            [
                {
                    "uid": knowledge_uid,
                    "entity_type": "knowledge",
                    "relationship_type": "provides",
                    "reasoning": "Supporting knowledge for deeper understanding",
                    "strength": 0.7,
                }
                for knowledge_uid in self.supporting_knowledge_uids
            ]
        )

        # GRAPH-NATIVE PLACEHOLDER: Use service layer for habits, tasks, event templates
        # 3. Habits to build
        # Query: MATCH (ls)-[:BUILDS_HABIT]->(h) RETURN h.uid
        # Service: LsRelationshipService.get_practice_habits(ls_uid)

        # 4. Tasks to complete
        # Query: MATCH (ls)-[:ASSIGNS_TASK]->(t) RETURN t.uid
        # Service: LsRelationshipService.get_practice_tasks(ls_uid)

        # 5. Event templates
        # Query: MATCH (ls)-[:SCHEDULES_EVENT]->(e) RETURN e.uid
        # Service: LsRelationshipService.get_practice_events(ls_uid)

        # 6. Dependent steps (steps that require this one)
        # Note: These are tracked in other LearningStep instances via prerequisite_step_uids
        impacts.append(
            {
                "uid": f"dependent_steps:{self.uid}",
                "entity_type": "step_dependency",
                "relationship_type": "enables",
                "reasoning": "Other steps that require this step as prerequisite",
                "strength": 1.0,
                "note": "Query other LearningSteps with this UID in prerequisite_step_uids",
            }
        )

        return impacts

    def get_relationship_summary(self) -> dict:
        """
        Get comprehensive relationship context for this learning step.

        Returns:
            Dict containing:
            - explanation: Why this step exists
            - upstream: What shaped it
            - downstream: What it shapes
            - upstream_count: Number of upstream influences
            - downstream_count: Number of downstream impacts
            - step_metrics: Progress, difficulty, practice integration
        """
        return {
            "explanation": self.explain_existence(),
            "upstream": self.get_upstream_influences(),
            "downstream": self.get_downstream_impacts(),
            "upstream_count": len(self.get_upstream_influences()),
            "downstream_count": len(self.get_downstream_impacts()),
            "step_metrics": {
                "intent": self.intent,
                "domain": self.domain.value,
                "difficulty": self.difficulty.value,
                "status": self.status.value,
                "is_standalone": self.is_standalone(),
                "is_sequenced": self.is_sequenced(),
                "sequence_number": self.sequence,
                "learning_path_uid": self.learning_path_uid,
                "estimated_hours": self.estimated_hours,
                "mastery_threshold": self.mastery_threshold,
                "current_mastery": self.current_mastery,
                "completed": self.completed,
                "is_foundational": self.is_foundational(),
                "total_knowledge_count": self.knowledge_count(),
                "has_practice_opportunities": self.has_practice_opportunities(),
                "practice_count": 0,  # Placeholder - use service layer
                "prerequisite_count": 0,  # Placeholder - use service layer
                "priority": self.priority.value,
                "tags": list(self.tags),
            },
        }


# Backward compatibility alias
LearningStep = Ls

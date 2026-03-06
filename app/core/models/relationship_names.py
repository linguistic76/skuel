"""
Relationship Names - Single Source of Truth for Neo4j Relationship Types
========================================================================

This enum defines ALL valid relationship type names used in Neo4j.
It is THE canonical source - RelationshipRegistry and protocols derive from this.

Design Philosophy:
- One enum to rule them all
- MyPy gets full compile-time verification
- IDE gets autocomplete
- Neo4j gets consistent relationship names

Usage:
    # In protocol methods - type-safe
    async def count_related(
        self, uid: str,
        relationship_type: RelationshipName,
        ...
    ) -> Result[int]:

    # When calling - IDE autocomplete
    await backend.count_related(uid, RelationshipName.REQUIRES_KNOWLEDGE)

    # In Cypher queries - use .value
    query = f"MATCH (a)-[:{rel.value}]->(b)"

Maintenance:
    When adding a new relationship:
    1. Add it to this enum (appropriate section)
    2. Add RelationshipSpec to RelationshipRegistry (if domain-specific validation needed)
    3. MyPy will guide you to update any affected code

See Also:
    - RelationshipRegistry: Domain-specific validation and metadata
    - SemanticRelationshipType: RDF-inspired precision (maps from this enum)
"""

from enum import Enum


class RelationshipName(str, Enum):
    """
    All valid Neo4j relationship type names.

    Organized by domain for discoverability. The string value matches
    the Neo4j relationship type exactly (UPPER_SNAKE_CASE).

    Being a str subclass means:
    - str(RelationshipName.X) works
    - Can be used directly in f-strings
    - .value gives the raw string for Cypher
    """

    # =========================================================================
    # KNOWLEDGE RELATIONSHIPS (ku:)
    # Relationships involving KnowledgeUnits
    # =========================================================================
    REQUIRES_PREREQUISITE = "REQUIRES_PREREQUISITE"
    RELATED_TO = "RELATED_TO"
    HAS_NARROWER = "HAS_NARROWER"
    HAS_BROADER = "HAS_BROADER"
    REQUIRES_KNOWLEDGE = "REQUIRES_KNOWLEDGE"
    APPLIES_KNOWLEDGE = "APPLIES_KNOWLEDGE"
    REINFORCES_KNOWLEDGE = "REINFORCES_KNOWLEDGE"
    PRACTICES_KNOWLEDGE = "PRACTICES_KNOWLEDGE"
    GROUNDED_IN_KNOWLEDGE = "GROUNDED_IN_KNOWLEDGE"
    GROUNDS_PRINCIPLE = "GROUNDS_PRINCIPLE"
    ENABLES_KNOWLEDGE = "ENABLES_KNOWLEDGE"
    ENABLES_GOAL = "ENABLES_GOAL"
    ENABLES_TASK = "ENABLES_TASK"
    INFORMS_CHOICE = "INFORMS_CHOICE"
    SUPPORTS_HABIT = "SUPPORTS_HABIT"
    COMPLETES_KNOWLEDGE = "COMPLETES_KNOWLEDGE"
    INFERRED_KNOWLEDGE = "INFERRED_KNOWLEDGE"
    GUIDED_BY_KNOWLEDGE = "GUIDED_BY_KNOWLEDGE"  # Goals guided by knowledge
    REINFORCED_BY_KNOWLEDGE = "REINFORCED_BY_KNOWLEDGE"  # Habits reinforced by knowledge
    BLOCKED_BY_KNOWLEDGE = "BLOCKED_BY_KNOWLEDGE"  # Tasks blocked by lack of knowledge

    # Article → Ku composition
    USES_KU = "USES_KU"  # (Article)-[:USES_KU]->(Ku) — article composes atomic Ku
    TRAINS_KU = "TRAINS_KU"  # (Ls)-[:TRAINS_KU]->(Ku) — learning step trains atomic Ku

    # =========================================================================
    # TASK RELATIONSHIPS
    # Task dependencies, contributions, and cross-domain links
    # =========================================================================
    # Parent-Child Composition (2026-01-30 - Hierarchical Relationships Pattern)
    HAS_SUBTASK = "HAS_SUBTASK"  # (parent)-[:HAS_SUBTASK {progress_weight, order}]->(child)
    SUBTASK_OF = (
        "SUBTASK_OF"  # (child)-[:SUBTASK_OF]->(parent) - Bidirectional for efficient queries
    )

    # Task Dependencies & Prerequisites
    DEPENDS_ON = "DEPENDS_ON"
    BLOCKS = "BLOCKS"
    BLOCKED_BY = "BLOCKED_BY"
    REQUIRES_TASK = "REQUIRES_TASK"  # Sequential prerequisite (different from parent-child!)

    # Task Contributions & Cross-Domain
    CONTRIBUTES_TO_GOAL = "CONTRIBUTES_TO_GOAL"
    FULFILLS_GOAL = "FULFILLS_GOAL"
    GENERATES_TASK = "GENERATES_TASK"
    EXECUTES_TASK = "EXECUTES_TASK"
    FUNDS_TASK = "FUNDS_TASK"
    TRIGGERS_ON_COMPLETION = "TRIGGERS_ON_COMPLETION"
    UNLOCKS_KNOWLEDGE = "UNLOCKS_KNOWLEDGE"
    COMPLETED_TASK = "COMPLETED_TASK"  # User completed a task
    ASSIGNED_TO = "ASSIGNED_TO"  # Task assigned to user

    # =========================================================================
    # GOAL RELATIONSHIPS
    # Goal hierarchy, dependencies, and guidance
    # =========================================================================
    SUBGOAL_OF = "SUBGOAL_OF"
    HAS_SUBGOAL = "HAS_SUBGOAL"
    HAS_CHILD = "HAS_CHILD"
    DEPENDS_ON_GOAL = "DEPENDS_ON_GOAL"
    GUIDED_BY_PRINCIPLE = "GUIDED_BY_PRINCIPLE"
    SUPPORTS_GOAL = "SUPPORTS_GOAL"
    CONFLICTS_WITH_GOAL = "CONFLICTS_WITH_GOAL"
    INSPIRES_GOAL = "INSPIRES_GOAL"
    CELEBRATED_BY_EVENT = "CELEBRATED_BY_EVENT"
    HAS_MILESTONE = "HAS_MILESTONE"
    MILESTONE_OF = "MILESTONE_OF"
    ALIGNED_WITH_PATH = "ALIGNED_WITH_PATH"
    MOTIVATED_BY_GOAL = "MOTIVATED_BY_GOAL"

    # =========================================================================
    # HABIT RELATIONSHIPS
    # Habit chains, prerequisites, and reinforcement
    # =========================================================================
    # Parent-Child Composition (2026-01-30 - Hierarchical Relationships Pattern)
    HAS_SUBHABIT = "HAS_SUBHABIT"  # (parent)-[:HAS_SUBHABIT {progress_weight, order}]->(child)
    SUBHABIT_OF = "SUBHABIT_OF"  # (child)-[:SUBHABIT_OF]->(parent) - Habit routines with sub-steps

    # Habit Prerequisites & Dependencies
    REQUIRES_PREREQUISITE_HABIT = "REQUIRES_PREREQUISITE_HABIT"
    ENABLES_HABIT = "ENABLES_HABIT"
    REQUIRES_HABIT = "REQUIRES_HABIT"

    # Habit Reinforcement & Impact
    REINFORCES_HABIT = "REINFORCES_HABIT"
    INSPIRES_HABIT = "INSPIRES_HABIT"
    IMPACTS_HABIT = "IMPACTS_HABIT"  # (choice)-[:IMPACTS_HABIT]->(habit)
    REINFORCES_STEP = "REINFORCES_STEP"
    EMBODIES_PRINCIPLE = "EMBODIES_PRINCIPLE"
    PRACTICED_AT_EVENT = "PRACTICED_AT_EVENT"

    # =========================================================================
    # EVENT RELATIONSHIPS
    # Event conflicts, execution, and practice
    # =========================================================================
    CONFLICTS_WITH = "CONFLICTS_WITH"
    FUNDS_EVENT = "FUNDS_EVENT"
    ATTENDS = "ATTENDS"

    # =========================================================================
    # PRINCIPLE RELATIONSHIPS
    # Principle support, conflicts, and guidance
    # =========================================================================
    SUPPORTS_PRINCIPLE = "SUPPORTS_PRINCIPLE"
    CONFLICTS_WITH_PRINCIPLE = "CONFLICTS_WITH_PRINCIPLE"
    GUIDES_GOAL = "GUIDES_GOAL"
    GUIDES_CHOICE = "GUIDES_CHOICE"  # (principle)-[:GUIDES_CHOICE]->(choice)
    ALIGNED_WITH_PRINCIPLE = "ALIGNED_WITH_PRINCIPLE"
    DEMONSTRATES_PRINCIPLE = (
        "DEMONSTRATES_PRINCIPLE"  # (event)-[:DEMONSTRATES_PRINCIPLE]->(principle)
    )

    # =========================================================================
    # PRINCIPLE REFLECTION RELATIONSHIPS
    # Reflection tracking and conflict detection
    # =========================================================================
    REFLECTS_ON = "REFLECTS_ON"  # (reflection)-[:REFLECTS_ON]->(principle)
    TRIGGERED_BY = "TRIGGERED_BY"  # (reflection)-[:TRIGGERED_BY]->(goal|habit|event|choice)
    REVEALS_CONFLICT = "REVEALS_CONFLICT"  # (reflection)-[:REVEALS_CONFLICT]->(principle)
    MADE_REFLECTION = "MADE_REFLECTION"  # (user)-[:MADE_REFLECTION]->(reflection)
    HAS_REFLECTION = "HAS_REFLECTION"  # (principle)-[:HAS_REFLECTION]->(reflection)

    # =========================================================================
    # CHOICE RELATIONSHIPS
    # Choice influences and outcomes
    # =========================================================================
    INFORMED_BY_PRINCIPLE = "INFORMED_BY_PRINCIPLE"
    INFORMED_BY_KNOWLEDGE = "INFORMED_BY_KNOWLEDGE"
    INSPIRED_BY_CHOICE = "INSPIRED_BY_CHOICE"
    IMPLEMENTS_CHOICE = "IMPLEMENTS_CHOICE"
    REQUIRES_KNOWLEDGE_FOR_DECISION = "REQUIRES_KNOWLEDGE_FOR_DECISION"
    OPENS_LEARNING_PATH = "OPENS_LEARNING_PATH"
    AFFECTS_GOAL = "AFFECTS_GOAL"
    TRIGGERS_CHOICE = "TRIGGERS_CHOICE"  # (event)-[:TRIGGERS_CHOICE]->(choice)

    # =========================================================================
    # USER/OWNERSHIP RELATIONSHIPS
    # User-to-entity ownership and progress
    # =========================================================================
    OWNS = "OWNS"  # (user)-[:OWNS]->(entity) - Universal ownership relationship
    HAS_TASK = "HAS_TASK"
    HAS_EVENT = "HAS_EVENT"
    HAS_HABIT = "HAS_HABIT"
    HAS_GOAL = "HAS_GOAL"
    HAS_PRINCIPLE = "HAS_PRINCIPLE"
    HAS_CHOICE = "HAS_CHOICE"
    HAS_KU = "HAS_KU"  # Unified ownership for Entity-migrated activity domains

    # =========================================================================
    # USER LEARNING PROGRESS RELATIONSHIPS
    # Track user interaction with knowledge units (pedagogical tracking)
    # State progression: NONE -> VIEWED -> IN_PROGRESS -> MASTERED
    # =========================================================================
    VIEWED = "VIEWED"  # (user)-[:VIEWED]->(ku) - User has seen/read this content
    IN_PROGRESS = "IN_PROGRESS"  # (user)-[:IN_PROGRESS]->(ku) - Actively learning
    MASTERED = "MASTERED"  # (user)-[:MASTERED]->(ku) - Knowledge acquired

    # =========================================================================
    # USER SOCIAL/PREFERENCE RELATIONSHIPS
    # User-specific relationships for social features and preferences
    # =========================================================================
    PINNED = "PINNED"  # (user)-[:PINNED {order: int}]->(entity) - User's pinned items
    FOLLOWS = "FOLLOWS"  # (user)-[:FOLLOWS]->(user) - Social following
    PURSUING_GOAL = "PURSUING_GOAL"  # (user)-[:PURSUING_GOAL]->(goal) - Active goals
    MEMBER_OF = "MEMBER_OF"  # (user)-[:MEMBER_OF]->(team) - Team membership
    SHARES_WITH = "SHARES_WITH"  # (user)-[:SHARES_WITH {shared_at, role}]->(assignment|event) - Content sharing

    # =========================================================================
    # FINANCE RELATIONSHIPS
    # Expense and budget connections
    # =========================================================================
    PART_OF_PROJECT = "PART_OF_PROJECT"

    # =========================================================================
    # LEARNING PATH RELATIONSHIPS
    # Learning path dependencies and completion requirements
    # =========================================================================
    REQUIRES_PATH_COMPLETION = "REQUIRES_PATH_COMPLETION"
    HAS_STEP = "HAS_STEP"  # (lp)-[:HAS_STEP]->(ls) - Learning path contains step

    # =========================================================================
    # CURRICULUM RELATIONSHIPS (January 2026 - Consolidation)
    # Learning Step, Learning Path, and Map of Content relationships
    # =========================================================================
    # Learning Step (LS) relationships
    CONTAINS_KNOWLEDGE = "CONTAINS_KNOWLEDGE"  # (ls)-[:CONTAINS_KNOWLEDGE]->(ku)
    REQUIRES_STEP = "REQUIRES_STEP"  # (ls)-[:REQUIRES_STEP]->(ls) - Step prerequisites
    BUILDS_HABIT = "BUILDS_HABIT"  # (ls)-[:BUILDS_HABIT]->(habit) - Practice pattern
    ASSIGNS_TASK = "ASSIGNS_TASK"  # (ls)-[:ASSIGNS_TASK]->(task) - Practice pattern
    SCHEDULES_EVENT = "SCHEDULES_EVENT"  # (ls)-[:SCHEDULES_EVENT]->(event) - Practice pattern

    # Learning Path (LP) relationships
    ALIGNED_WITH_GOAL = "ALIGNED_WITH_GOAL"  # (lp)-[:ALIGNED_WITH_GOAL]->(goal)
    HAS_MILESTONE_EVENT = "HAS_MILESTONE_EVENT"  # (lp)-[:HAS_MILESTONE_EVENT]->(event)

    # =========================================================================
    # MOC ORGANIZATIONAL RELATIONSHIPS (MOC = KU organizing KUs)
    # MOC is not a separate entity - it's a KU with ORGANIZES relationships.
    # A KU "is" a MOC when it has outgoing ORGANIZES relationships.
    # =========================================================================
    ORGANIZES = "ORGANIZES"  # (ku)-[:ORGANIZES {order: int}]->(ku) - KU organizing other KUs

    # =========================================================================
    # LIFE PATH RELATIONSHIPS (The Destination)
    # "Everything flows toward the life path"
    # =========================================================================
    ULTIMATE_PATH = "ULTIMATE_PATH"  # (user)-[:ULTIMATE_PATH]->(lp) - User's designated life path
    SERVES_LIFE_PATH = (
        "SERVES_LIFE_PATH"  # (entity)-[:SERVES_LIFE_PATH]->(lp) - Entity contributes to life path
    )

    # =========================================================================
    # EXERCISE/GROUP RELATIONSHIPS (ADR-040)
    # Teacher exercise workflow and group management
    # =========================================================================
    FOR_GROUP = "FOR_GROUP"  # (Exercise)-[:FOR_GROUP]->(Group)
    # (Entity)-[:FULFILLS_EXERCISE]->(Exercise) - Student submission
    FULFILLS_EXERCISE = "FULFILLS_EXERCISE"
    # (Entity)-[:SHARED_WITH_GROUP {shared_at, share_version}]->(Group) - Group-level sharing
    SHARED_WITH_GROUP = "SHARED_WITH_GROUP"

    # =========================================================================
    # CONTENT/PROCESSING RELATIONSHIPS
    # Transcription, journal processing, and content linking
    # =========================================================================
    TRANSCRIBED_FOR = "TRANSCRIBED_FOR"  # Transcription created for journal
    HAS_SCHEDULE = "HAS_SCHEDULE"  # (User)-[:HAS_SCHEDULE]->(ReportSchedule) - User's report generation schedule
    ASSESSMENT_OF = (
        "ASSESSMENT_OF"  # (Report)-[:ASSESSMENT_OF]->(User) - Teacher assessment targets student
    )
    FEEDBACK_FOR = (
        "FEEDBACK_FOR"  # (Entity)-[:FEEDBACK_FOR]->(Entity) - Teacher feedback targets submission
    )

    # =========================================================================
    # NOTIFICATION RELATIONSHIPS
    # In-app notification delivery
    # =========================================================================
    HAS_NOTIFICATION = "HAS_NOTIFICATION"  # (User)-[:HAS_NOTIFICATION]->(Notification)

    # =========================================================================
    # AUTHENTICATION RELATIONSHIPS
    # Graph-native session and auth event tracking
    # =========================================================================
    HAS_SESSION = "HAS_SESSION"  # (user)-[:HAS_SESSION]->(session)
    HAD_AUTH_EVENT = "HAD_AUTH_EVENT"  # (user)-[:HAD_AUTH_EVENT]->(auth_event)
    HAS_RESET_TOKEN = "HAS_RESET_TOKEN"  # (user)-[:HAS_RESET_TOKEN]->(reset_token)

    # =========================================================================
    # LATERAL RELATIONSHIPS (February 2026 - Unified from LateralRelationType)
    # Within-domain relationships between entities at same/related hierarchy levels.
    # These complement the cross-domain relationships above.
    # =========================================================================

    # Structural - Position in hierarchy
    SIBLING = "SIBLING"  # Same parent, same depth (symmetric)
    COUSIN = "COUSIN"  # Same depth, different parents, shared grandparent (symmetric)
    AUNT_UNCLE = "AUNT_UNCLE"  # Parent's sibling (asymmetric, inverse: NIECE_NEPHEW)
    NIECE_NEPHEW = "NIECE_NEPHEW"  # Inverse of AUNT_UNCLE

    # Dependency - Ordering and constraints
    # (BLOCKS, BLOCKED_BY, REQUIRES_PREREQUISITE already defined above)
    PREREQUISITE_FOR = "PREREQUISITE_FOR"  # Inverse of REQUIRES_PREREQUISITE (soft dependency)
    LATERAL_ENABLES = "ENABLES"  # Generic within-domain: completing X enables Y
    LATERAL_ENABLED_BY = "ENABLED_BY"  # Inverse of LATERAL_ENABLES

    # Semantic - Domain meaning beyond hierarchy
    # (RELATED_TO, CONFLICTS_WITH already defined above)
    SIMILAR_TO = "SIMILAR_TO"  # High semantic similarity (symmetric)
    COMPLEMENTARY_TO = "COMPLEMENTARY_TO"  # Synergistic pairing (symmetric)

    # Associative - Recommendations and alternatives
    ALTERNATIVE_TO = "ALTERNATIVE_TO"  # Mutually exclusive options (symmetric)
    RECOMMENDED_WITH = "RECOMMENDED_WITH"  # Often done together (symmetric)
    STACKS_WITH = "STACKS_WITH"  # Sequential combination / habit stacking

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    @classmethod
    def from_string(cls, value: str) -> "RelationshipName | None":
        """
        Convert a string to RelationshipName, returning None if invalid.

        Handles both the enum name and value (they're the same in this enum).

        Args:
            value: String to convert (e.g., "REQUIRES_KNOWLEDGE")

        Returns:
            RelationshipName or None if not found

        Example:
            >>> RelationshipName.from_string("REQUIRES_KNOWLEDGE")
            RelationshipName.REQUIRES_KNOWLEDGE
            >>> RelationshipName.from_string("invalid")
            None
        """
        try:
            return cls(value)
        except ValueError:
            return None

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """
        Check if a string is a valid relationship name.

        Args:
            value: String to check

        Returns:
            True if valid, False otherwise

        Example:
            >>> RelationshipName.is_valid("REQUIRES_KNOWLEDGE")
            True
            >>> RelationshipName.is_valid("INVALID_TYPE")
            False
        """
        return cls.from_string(value) is not None

    def is_knowledge_relationship(self) -> bool:
        """Check if this relationship involves knowledge units."""
        knowledge_types = {
            self.RELATED_TO,
            self.HAS_NARROWER,
            self.HAS_BROADER,
            self.REQUIRES_KNOWLEDGE,
            self.APPLIES_KNOWLEDGE,
            self.REINFORCES_KNOWLEDGE,
            self.PRACTICES_KNOWLEDGE,
            self.GROUNDED_IN_KNOWLEDGE,
            self.GROUNDS_PRINCIPLE,
            self.ENABLES_KNOWLEDGE,
        }
        return self in knowledge_types

    def is_blocking_relationship(self) -> bool:
        """Check if this relationship represents a blocking dependency."""
        blocking_types = {
            self.DEPENDS_ON,
            self.BLOCKS,
            self.DEPENDS_ON_GOAL,
            self.REQUIRES_PREREQUISITE_HABIT,
            self.REQUIRES_KNOWLEDGE,
        }
        return self in blocking_types

    def is_ownership_relationship(self) -> bool:
        """Check if this is a user ownership relationship."""
        ownership_types = {
            self.HAS_TASK,
            self.HAS_EVENT,
            self.HAS_HABIT,
            self.HAS_GOAL,
            self.HAS_PRINCIPLE,
            self.HAS_CHOICE,
        }
        return self in ownership_types

    def is_learning_progress_relationship(self) -> bool:
        """Check if this is a user learning progress relationship.

        These relationships track the user's pedagogical journey through
        knowledge content: VIEWED -> IN_PROGRESS -> MASTERED.
        """
        progress_types = {
            self.VIEWED,
            self.IN_PROGRESS,
            self.MASTERED,
        }
        return self in progress_types

    def is_life_path_relationship(self) -> bool:
        """Check if this is a life path relationship.

        These relationships connect the user and their activities to
        their designated life path - "Everything flows toward the life path."
        """
        life_path_types = {
            self.ULTIMATE_PATH,
            self.SERVES_LIFE_PATH,
        }
        return self in life_path_types

    def is_parent_child_relationship(self) -> bool:
        """Check if this is a parent-child composition relationship.

        These relationships represent decomposition where a parent entity
        is composed of child entities. Used for:
        - Task decomposition (task with subtasks)
        - Goal milestone breakdown (goal with subgoals)
        - Habit routines (habit with sub-steps)

        See: /docs/patterns/HIERARCHICAL_RELATIONSHIPS_PATTERN.md
        """
        parent_child_types = {
            self.HAS_SUBTASK,
            self.SUBTASK_OF,
            self.HAS_SUBGOAL,
            self.SUBGOAL_OF,
            self.HAS_SUBHABIT,
            self.SUBHABIT_OF,
        }
        return self in parent_child_types

    def is_prerequisite_relationship(self) -> bool:
        """Check if this is a prerequisite/sequential dependency relationship.

        These relationships enforce ordering (must complete A before B).
        Different from parent-child which represents composition.

        See: /docs/patterns/HIERARCHICAL_RELATIONSHIPS_PATTERN.md
        """
        prerequisite_types = {
            self.REQUIRES_TASK,
            self.DEPENDS_ON_GOAL,
            self.REQUIRES_HABIT,
            self.REQUIRES_PREREQUISITE_HABIT,
            self.REQUIRES_KNOWLEDGE,
            self.REQUIRES_STEP,
        }
        return self in prerequisite_types

    # =========================================================================
    # LATERAL RELATIONSHIP HELPER METHODS
    # =========================================================================

    def is_lateral_relationship(self) -> bool:
        """Check if this is a lateral (within-domain) relationship type."""
        return self in _LATERAL_TYPES

    def is_symmetric_lateral(self) -> bool:
        """Check if this lateral relationship is symmetric (same type both ways)."""
        return self in _SYMMETRIC_LATERAL_TYPES

    def get_lateral_inverse(self) -> "RelationshipName | None":
        """Get inverse for asymmetric lateral relationships. None if symmetric."""
        return _LATERAL_INVERSES.get(self)

    def lateral_requires_same_parent(self) -> bool:
        """Check if lateral relationship requires entities to share same parent."""
        return self in {self.SIBLING, self.BLOCKS, self.STACKS_WITH}

    def lateral_requires_same_depth(self) -> bool:
        """Check if lateral relationship requires entities at same depth."""
        return self in {self.SIBLING, self.COUSIN, self.RELATED_TO, self.ALTERNATIVE_TO}

    def get_lateral_category(self) -> str | None:
        """Get category for lateral relationship types.

        Returns:
            "structural", "dependency", "semantic", "associative", or None if not lateral.
        """
        if self in {self.SIBLING, self.COUSIN, self.AUNT_UNCLE, self.NIECE_NEPHEW}:
            return "structural"
        if self in {
            self.BLOCKS,
            self.BLOCKED_BY,
            self.PREREQUISITE_FOR,
            self.REQUIRES_PREREQUISITE,
            self.LATERAL_ENABLES,
            self.LATERAL_ENABLED_BY,
        }:
            return "dependency"
        if self in {
            self.RELATED_TO,
            self.SIMILAR_TO,
            self.COMPLEMENTARY_TO,
            self.CONFLICTS_WITH,
        }:
            return "semantic"
        if self in {self.ALTERNATIVE_TO, self.RECOMMENDED_WITH, self.STACKS_WITH}:
            return "associative"
        return None


# Module-level constants (computed once at import time, not per-call)

_LATERAL_TYPES = frozenset(
    {
        RelationshipName.SIBLING,
        RelationshipName.COUSIN,
        RelationshipName.AUNT_UNCLE,
        RelationshipName.NIECE_NEPHEW,
        RelationshipName.BLOCKS,
        RelationshipName.BLOCKED_BY,
        RelationshipName.PREREQUISITE_FOR,
        RelationshipName.REQUIRES_PREREQUISITE,
        RelationshipName.LATERAL_ENABLES,
        RelationshipName.LATERAL_ENABLED_BY,
        RelationshipName.RELATED_TO,
        RelationshipName.SIMILAR_TO,
        RelationshipName.COMPLEMENTARY_TO,
        RelationshipName.CONFLICTS_WITH,
        RelationshipName.ALTERNATIVE_TO,
        RelationshipName.RECOMMENDED_WITH,
        RelationshipName.STACKS_WITH,
    }
)

_SYMMETRIC_LATERAL_TYPES = frozenset(
    {
        RelationshipName.SIBLING,
        RelationshipName.COUSIN,
        RelationshipName.RELATED_TO,
        RelationshipName.SIMILAR_TO,
        RelationshipName.COMPLEMENTARY_TO,
        RelationshipName.CONFLICTS_WITH,
        RelationshipName.ALTERNATIVE_TO,
        RelationshipName.RECOMMENDED_WITH,
    }
)

_LATERAL_INVERSES: dict[RelationshipName, RelationshipName] = {
    RelationshipName.BLOCKS: RelationshipName.BLOCKED_BY,
    RelationshipName.BLOCKED_BY: RelationshipName.BLOCKS,
    RelationshipName.PREREQUISITE_FOR: RelationshipName.REQUIRES_PREREQUISITE,
    RelationshipName.REQUIRES_PREREQUISITE: RelationshipName.PREREQUISITE_FOR,
    RelationshipName.LATERAL_ENABLES: RelationshipName.LATERAL_ENABLED_BY,
    RelationshipName.LATERAL_ENABLED_BY: RelationshipName.LATERAL_ENABLES,
    RelationshipName.AUNT_UNCLE: RelationshipName.NIECE_NEPHEW,
    RelationshipName.NIECE_NEPHEW: RelationshipName.AUNT_UNCLE,
}

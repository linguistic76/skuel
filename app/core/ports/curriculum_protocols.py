"""
Curriculum Protocols - Consistent Protocol Hierarchy for KU, LS, LP
====================================================================

*Last updated: 2026-02-27*

This module provides a CONSISTENT protocol hierarchy for the four
curriculum domains (KU, LS, LP, Exercise), parallel to BackendOperations
for Activity domains.

Any Ku can organize other Kus via ORGANIZES relationships (emergent identity).
Organization methods are part of LessonOperations protocol.

Design Principle: "Curriculum domains follow the same patterns as Activity domains"
-------------------------------------------------------------------------------

The Four Curriculum Domains:
    - KU (Point topology): Atomic knowledge unit
    - LS (Edge topology): Sequential step aggregating KUs
    - LP (Path topology): Complete learning sequence of LSs
    - Exercise (Template): LLM instruction template for student submissions

Protocol Hierarchy:
    - CurriculumOperations[T]: Base protocol inheriting BackendOperations
    - LessonOperations: Extends CurriculumOperations[Lesson] with KU-specific methods
    - LsOperations: Extends CurriculumOperations[LearningStep] with LS-specific methods
    - LpOperations: Extends CurriculumOperations[LearningPath] with LP-specific methods
    - ExerciseOperations: Standalone protocol for Exercise instruction templates

Protocol Hierarchy
------------------
    CurriculumOperations[T] ← Base for all curriculum domains
        ├── Inherits: BackendOperations[T] (CRUD, relationships, traversal)
        ├── Inherits: GraphRelationshipOperations (get_related_uids, count_related)
        │
        └── Curriculum-Specific Methods:
            ├── get_with_content() → Result[T]
            ├── get_with_context() → Result[T]
            ├── get_prerequisites() → Result[list[T]]
            └── get_hierarchy() → Result[dict]

Domain-Specific Protocols:
    LessonOperations(CurriculumOperations[Lesson], Protocol):
        ├── get_enables() → Result[list[Lesson]]
        ├── get_semantic_links() → Result[list[str]]
        └── get_substance_score() → Result[float]

    LsOperations(CurriculumOperations[LearningStep], Protocol):
        ├── get_knowledge_uids() → Result[list[str]]
        ├── get_path_steps() → Result[list[LearningStep]]
        └── get_practice_summary() → Result[dict]

    LpOperations(CurriculumOperations[LearningPath], Protocol):
        ├── get_next_step() → Result[LearningStep | None]
        ├── calculate_progress() → Result[float]

Return Type Consistency
-----------------------
ALL methods return Result[T] - no raw dicts, no None returns for not-found.
This aligns with Activity domain patterns per CLAUDE.md.

Usage
-----
    from core.ports import CurriculumOperations, LessonOperations

    class LessonCoreService(BaseService[LessonOperations, Lesson]):
        @property
        def entity_label(self) -> str:
            return "Entity"

See Also
--------
- /core/ports/base_protocols.py - BackendOperations hierarchy
- /core/ports/domain_protocols.py - Activity domain protocols
- /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md - Curriculum architecture
- /docs/domains/moc.md - MOC architecture (KU-based since January 2026)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .base_protocols import BackendOperations, GraphRelationshipOperations

if TYPE_CHECKING:
    from datetime import date

    from core.models.lesson.lesson import Lesson
    from core.models.exercises.exercise import Exercise
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.learning_step import LearningStep
    from core.utils.result_simplified import Result


# =============================================================================
# CURRICULUM BASE PROTOCOL
# =============================================================================


@runtime_checkable
class CurriculumOperations[T](BackendOperations[T], GraphRelationshipOperations, Protocol):
    """
    Base protocol for all curriculum domain backends (KU, LS, LP).

    Inherits:
        - BackendOperations[T]: Full CRUD, relationships, traversal, search
        - GraphRelationshipOperations: get_related_uids(), count_related()

    Adds curriculum-specific methods that all three domains share:
        - get_with_content(): Fetch entity with full content
        - get_with_context(): Fetch entity with graph neighborhood
        - get_prerequisites(): Fetch prerequisite entities
        - get_hierarchy(): Fetch hierarchical structure

    Type Parameter:
        T: The domain model (Curriculum, LearningStep, or LearningPath)

    Design Rationale:
        Curriculum domains share patterns that Activity domains don't need:
        - Content retrieval (markdown, learning materials)
        - Prerequisite chains (knowledge dependencies)
        - Hierarchical structures (KU→LS→LP aggregation)

        By inheriting BackendOperations, curriculum domains get ALL the same
        capabilities as Activity domains (CRUD, relationships, search, traversal)
        PLUS these curriculum-specific additions.

    Example:
        class KuUniversalBackend(UniversalNeo4jBackend[Lesson], CurriculumOperations[Lesson]):
            async def get_with_content(self, uid: str) -> Result[Lesson]:
                # Implementation
                ...
    """

    # =========================================================================
    # CONTENT RETRIEVAL
    # =========================================================================

    async def get_with_content(self, uid: str) -> Result[tuple[T, str | None]]:
        """
        Get entity with full content loaded.

        For curriculum entities, content may be stored separately or lazily loaded.
        This method ensures the full content is retrieved.

        Args:
            uid: Entity UID

        Returns:
            Result[tuple[T, str | None]]: Entity and its content, or error
        """
        ...

    async def get_with_context(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[T]:
        """
        Get entity with graph neighborhood context.

        Fetches the entity plus related entities within the specified depth.
        Context is stored in entity.metadata["graph_context"].

        Args:
            uid: Entity UID
            depth: How many relationship hops to include (default: 2)
            min_confidence: Minimum relationship confidence (default: 0.7)

        Returns:
            Result[T]: Entity with graph_context in metadata
        """
        ...

    # =========================================================================
    # PREREQUISITE CHAINS
    # =========================================================================

    async def get_prerequisites(self, uid: str, depth: int = 3) -> Result[list[T]]:
        """
        Get prerequisite entities for this entity.

        Traverses REQUIRES/PREREQUISITE relationships to find all entities
        that must be mastered before this one.

        Args:
            uid: Entity UID
            depth: Maximum prerequisite chain depth (default: 3)

        Returns:
            Result[list[T]]: Ordered list of prerequisites (foundational first)
        """
        ...

    async def get_enables(self, uid: str, depth: int = 3) -> Result[list[T]]:
        """
        Get entities enabled by this entity.

        Finds all entities that become accessible after mastering this one.

        Args:
            uid: Entity UID
            depth: Maximum depth to traverse (default: 3)

        Returns:
            Result[list[T]]: Entities that this entity enables
        """
        ...

    # =========================================================================
    # HIERARCHICAL STRUCTURE
    # =========================================================================

    async def get_hierarchy(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get hierarchical structure for this entity.

        Returns the entity's position in the curriculum hierarchy:
        - For KU: Which LS and LP contain it
        - For LS: Which LP contains it, which KUs it aggregates
        - For LP: Its step sequence and knowledge coverage

        Args:
            uid: Entity UID

        Returns:
            Result[dict]: Hierarchical context including:
                - parent_uids: UIDs of containing entities
                - child_uids: UIDs of contained entities
                - position: Sequence/order information
                - aggregation: What this entity aggregates
        """
        ...

    # =========================================================================
    # USER-SCOPED QUERIES
    # =========================================================================

    async def get_user_curriculum(
        self,
        user_uid: str,
        include_completed: bool = False,
    ) -> Result[list[T]]:
        """
        Get curriculum entities for a user.

        Args:
            user_uid: User UID
            include_completed: Include completed/mastered entities

        Returns:
            Result[list[T]]: User's curriculum entities
        """
        ...


# =============================================================================
# INTERACTION PROTOCOLS
# =============================================================================


@runtime_checkable
class KuInteractionOperations(Protocol):
    """
    Protocol for KU interaction tracking (pedagogical search support).

    Tracks user interactions with knowledge units for self-directed learning.
    State progression: NONE -> VIEWED -> IN_PROGRESS -> MASTERED
    """

    async def record_view(
        self,
        user_uid: str,
        ku_uid: str,
        time_spent_seconds: int = 0,
    ) -> Result[bool]:
        """Record that a user viewed a knowledge unit."""
        ...

    async def mark_in_progress(self, user_uid: str, ku_uid: str) -> Result[bool]:
        """Mark a KU as in-progress for the user."""
        ...

    async def get_user_progress(self, user_uid: str, ku_uid: str) -> Result[Any]:
        """Get user's progress on a specific KU."""
        ...


# =============================================================================
# DOMAIN-SPECIFIC PROTOCOLS
# =============================================================================


@runtime_checkable
class LessonOperations(CurriculumOperations["Lesson"], Protocol):
    """
    Lesson (teaching composition) specific operations.

    Extends CurriculumOperations with Lesson-specific methods for:
    - Semantic relationships
    - Substance tracking (applied knowledge measurement)
    - Domain-specific queries

    Neo4j: Lesson nodes are :Entity:Lesson{entity_type='lesson'}
    UID Format: "a_{slug}_{random}" (e.g., "a_python-basics_a1b2c3d4")
    """

    # =========================================================================
    # SUB-SERVICES
    # =========================================================================

    @property
    def interaction(self) -> KuInteractionOperations | None:
        """Interaction tracking service for pedagogical search."""
        ...

    # =========================================================================
    # KU-SPECIFIC RETRIEVAL
    # =========================================================================

    async def get_ku(self, uid: str) -> Result[Lesson]:
        """
        Get a Knowledge Unit by UID.

        Semantic alias for get() - provides domain-specific naming.

        Args:
            uid: KU UID (e.g., "ku_python-basics_a1b2c3d4")

        Returns:
            Result[Lesson]: The knowledge unit or not-found error
        """
        ...

    async def get_user_kus(self, user_uid: str) -> Result[list[Lesson]]:
        """
        Get all KUs accessible to a user.

        Args:
            user_uid: User UID

        Returns:
            Result[list[Lesson]]: User's knowledge units
        """
        ...

    # =========================================================================
    # SEMANTIC RELATIONSHIPS
    # =========================================================================

    async def get_semantic_links(self, uid: str) -> Result[list[str]]:
        """
        Get semantically related KU UIDs.

        These are discovered relationships based on content analysis,
        not explicit user-defined relationships.

        Args:
            uid: KU UID

        Returns:
            Result[list[str]]: UIDs of semantically related KUs
        """
        ...

    async def get_related_by_domain(
        self,
        uid: str,
        domain: str,
    ) -> Result[list[Lesson]]:
        """
        Get related KUs filtered by domain.

        Args:
            uid: Source KU UID
            domain: Domain filter (e.g., "TECH", "HEALTH")

        Returns:
            Result[list[Lesson]]: Related KUs in specified domain
        """
        ...

    # =========================================================================
    # SUBSTANCE TRACKING
    # =========================================================================

    async def get_substance_score(self, uid: str) -> Result[float]:
        """
        Get the substance score for a KU.

        Substance measures how well knowledge is applied in practice:
        - 0.0: Pure theory (never applied)
        - 1.0: Fully substantiated (applied in habits, tasks, events, journals)

        Args:
            uid: KU UID

        Returns:
            Result[float]: Substance score (0.0-1.0)
        """
        ...

    async def get_substantiation_summary(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get detailed substantiation breakdown for a KU.

        Returns:
            Result[dict]: Breakdown including:
                - tasks_applied: Count of tasks using this KU
                - events_practiced: Count of events practicing this KU
                - habits_built: Count of habits reinforcing this KU
                - journal_reflections: Count of journal entries
                - choices_informed: Count of choices using this KU
                - substance_score: Overall score (0.0-1.0)
        """
        ...

    # =========================================================================
    # CURRICULUM INTEGRATION
    # =========================================================================

    async def get_learning_steps_using(self, uid: str) -> Result[list[str]]:
        """
        Get LS UIDs that include this KU.

        Args:
            uid: KU UID

        Returns:
            Result[list[str]]: UIDs of learning steps using this KU
        """
        ...

    async def get_learning_paths_featuring(self, uid: str) -> Result[list[str]]:
        """
        Get LP UIDs that feature this KU.

        Args:
            uid: KU UID

        Returns:
            Result[list[str]]: UIDs of learning paths featuring this KU
        """
        ...

    # =========================================================================
    # ORGANIZATION (ORGANIZES relationships — any Lesson can organize others)
    # =========================================================================

    async def organize(self, parent_uid: str, child_uid: str, order: int = 0) -> Result[bool]:
        """Create ORGANIZES relationship between two Lessons."""
        ...

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove ORGANIZES relationship between two Lessons."""
        ...

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        """Change the order of a child Lesson within its parent."""
        ...

    async def is_organizer(self, ku_uid: str) -> Result[bool]:
        """Check if a Lesson has organized children."""
        ...

    async def get_organization_view(self, ku_uid: str, max_depth: int = 3) -> Result[Any]:
        """Get a Lesson with its organized children hierarchy."""
        ...

    async def find_organizers(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Find all parent Lessons that organize the given Lesson."""
        ...

    async def list_root_organizers(self, limit: int = 50) -> Result[list[dict[str, Any]]]:
        """List Lessons that organize others but are not themselves organized."""
        ...

    async def get_organized_children(self, ku_uid: str) -> Result[list[dict[str, Any]]]:
        """Get direct children of a Lesson organized by ORGANIZES relationship."""
        ...


@runtime_checkable
class LsOperations(CurriculumOperations["LearningStep"], Protocol):
    """
    Learning Step (LS) specific operations.

    Extends CurriculumOperations with LS-specific methods for:
    - Knowledge aggregation (LS aggregates KUs)
    - Practice integration (habits, tasks, events)
    - Path integration (LS can be standalone or part of LP)

    Neo4j: LS nodes are :Entity:LearningStep{entity_type='learning_step'}
    UID Format: "ls:{random}" (e.g., "ls:a1b2c3d4")
    """

    # =========================================================================
    # LS-SPECIFIC RETRIEVAL
    # =========================================================================

    async def get_ls(self, uid: str) -> Result[LearningStep]:
        """
        Get a Learning Step by UID.

        Args:
            uid: LS UID (e.g., "ls:a1b2c3d4")

        Returns:
            Result[LearningStep]: The learning step or not-found error
        """
        ...

    async def get_user_steps(self, user_uid: str) -> Result[list[LearningStep]]:
        """
        Get all learning steps for a user.

        Args:
            user_uid: User UID

        Returns:
            Result[list[LearningStep]]: User's learning steps
        """
        ...

    async def get_learning_steps_batch(self, uids: list[str]) -> Result[list[LearningStep | None]]:
        """
        Batch load learning steps by UIDs.

        Args:
            uids: List of LS UIDs to load

        Returns:
            Result[list[LearningStep | None]]: Learning steps in same order as input UIDs,
                                     None for UIDs that don't exist
        """
        ...

    # =========================================================================
    # KNOWLEDGE AGGREGATION
    # =========================================================================

    async def get_knowledge_uids(self, uid: str) -> Result[list[str]]:
        """
        Get all KU UIDs aggregated by this step.

        Returns both primary and supporting knowledge UIDs.

        Args:
            uid: LS UID

        Returns:
            Result[list[str]]: All KU UIDs in this step
        """
        ...

    async def get_primary_knowledge(self, uid: str) -> Result[list[Lesson]]:
        """
        Get primary (core) knowledge units for this step.

        Args:
            uid: LS UID

        Returns:
            Result[list[Lesson]]: Primary knowledge units
        """
        ...

    async def get_supporting_knowledge(self, uid: str) -> Result[list[Lesson]]:
        """
        Get supporting (optional) knowledge units for this step.

        Args:
            uid: LS UID

        Returns:
            Result[list[Lesson]]: Supporting knowledge units
        """
        ...

    # =========================================================================
    # PRACTICE INTEGRATION
    # =========================================================================

    async def get_practice_summary(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get practice integration summary for this step.

        Returns:
            Result[dict]: Practice elements including:
                - habit_uids: Habits that build on this step
                - task_uids: Tasks for practicing this step
                - event_uids: Events for this step
                - total_practice_elements: Count of all elements
                - practice_completeness: Score (0.0-1.0)
        """
        ...

    async def get_practice_tasks(self, uid: str) -> Result[list[str]]:
        """
        Get task UIDs for practicing this step.

        Args:
            uid: LS UID

        Returns:
            Result[list[str]]: Task UIDs
        """
        ...

    async def get_practice_habits(self, uid: str) -> Result[list[str]]:
        """
        Get habit UIDs that reinforce this step.

        Args:
            uid: LS UID

        Returns:
            Result[list[str]]: Habit UIDs
        """
        ...

    async def get_practice_events(self, uid: str) -> Result[list[str]]:
        """
        Get event UIDs associated with this step.

        Args:
            uid: LS UID

        Returns:
            Result[list[str]]: Event UIDs
        """
        ...

    # =========================================================================
    # PATH INTEGRATION
    # =========================================================================

    async def get_path_steps(self, path_uid: str) -> Result[list[LearningStep]]:
        """
        Get all steps for a learning path, in sequence order.

        Args:
            path_uid: LP UID

        Returns:
            Result[list[LearningStep]]: Ordered list of steps
        """
        ...

    async def get_parent_path(self, uid: str) -> Result[str | None]:
        """
        Get the parent LP UID for this step, if any.

        Args:
            uid: LS UID

        Returns:
            Result[str | None]: Parent LP UID or None if standalone
        """
        ...

    async def is_standalone(self, uid: str) -> Result[bool]:
        """
        Check if this step exists independently (not part of a path).

        Args:
            uid: LS UID

        Returns:
            Result[bool]: True if standalone
        """
        ...

    # =========================================================================
    # GUIDANCE INTEGRATION
    # =========================================================================

    async def get_guiding_principles(self, uid: str) -> Result[list[str]]:
        """
        Get principle UIDs that guide this step.

        Args:
            uid: LS UID

        Returns:
            Result[list[str]]: Principle UIDs
        """
        ...

    async def get_offered_choices(self, uid: str) -> Result[list[str]]:
        """
        Get choice UIDs offered in this step.

        Args:
            uid: LS UID

        Returns:
            Result[list[str]]: Choice UIDs
        """
        ...


@runtime_checkable
class LpOperations(CurriculumOperations["LearningPath"], Protocol):
    """
    Learning Path (LP) specific operations.

    Extends CurriculumOperations with LP-specific methods for:
    - Step sequencing and navigation
    - Progress and mastery tracking
    - Motivational alignment (goals, principles)
    - Milestone and checkpoint management

    Neo4j: LP nodes are :Entity:LearningPath{entity_type='learning_path'}
    UID Format: "lp:{random}" (e.g., "lp:a1b2c3d4")
    """

    # =========================================================================
    # LP-SPECIFIC RETRIEVAL
    # =========================================================================

    async def get_lp(self, uid: str) -> Result[LearningPath]:
        """
        Get a Learning Path by UID.

        Args:
            uid: LP UID (e.g., "lp:a1b2c3d4")

        Returns:
            Result[LearningPath]: The learning path or not-found error
        """
        ...

    async def get_learning_paths_batch(self, uids: list[str]) -> Result[list[LearningPath | None]]:
        """
        Batch load learning paths by UIDs.

        Args:
            uids: List of LP UIDs to load

        Returns:
            Result[list[LearningPath | None]]: Learning paths in same order as input UIDs,
                                     None for UIDs that don't exist
        """
        ...

    async def list_user_paths(
        self,
        user_uid: str,
        include_completed: bool = False,
    ) -> Result[list[LearningPath]]:
        """
        Get all learning paths for a user.

        Args:
            user_uid: User UID
            include_completed: Include completed paths

        Returns:
            Result[list[LearningPath]]: User's learning paths
        """
        ...

    async def list_all_paths(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[LearningPath]]:
        """
        List all learning paths in the system with pagination and sorting.

        Args:
            limit: Maximum number of paths to return
            offset: Number of paths to skip (for pagination)
            order_by: Field to sort by (e.g., 'uid', 'created_at', 'title')
            order_desc: Sort in descending order if True

        Returns:
            Result[list[LearningPath]]: All learning paths
        """
        ...

    async def get_active_paths(self, user_uid: str) -> Result[list[LearningPath]]:
        """
        Get in-progress learning paths for a user.

        Args:
            user_uid: User UID

        Returns:
            Result[list[LearningPath]]: Paths with progress but not completed
        """
        ...

    # =========================================================================
    # STEP NAVIGATION
    # =========================================================================

    async def get_steps(self, uid: str) -> Result[list[LearningStep]]:
        """
        Get all steps in this path, in sequence order.

        Args:
            uid: LP UID

        Returns:
            Result[list[LearningStep]]: Ordered steps
        """
        ...

    async def get_next_step(
        self,
        uid: str,
        completed_step_uids: set[str],
    ) -> Result[LearningStep | None]:
        """
        Get the next step to complete in this path.

        Args:
            uid: LP UID
            completed_step_uids: Set of already-completed step UIDs

        Returns:
            Result[LearningStep | None]: Next step or None if path complete
        """
        ...

    async def get_current_step(self, uid: str, user_uid: str) -> Result[LearningStep | None]:
        """
        Get the current in-progress step for a user.

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[LearningStep | None]: Current step or None
        """
        ...

    # =========================================================================
    # PROGRESS AND MASTERY
    # =========================================================================

    async def calculate_progress(self, uid: str, user_uid: str) -> Result[float]:
        """
        Calculate overall path progress for a user.

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[float]: Progress percentage (0.0-1.0)
        """
        ...

    async def calculate_mastery(self, uid: str, user_uid: str) -> Result[float]:
        """
        Calculate average mastery across all steps.

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[float]: Average mastery (0.0-1.0)
        """
        ...

    async def is_complete(self, uid: str, user_uid: str) -> Result[bool]:
        """
        Check if path is complete for a user.

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[bool]: True if all steps completed
        """
        ...

    async def is_mastered(self, uid: str, user_uid: str) -> Result[bool]:
        """
        Check if path is fully mastered (all steps meet threshold).

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[bool]: True if all steps mastered
        """
        ...

    # =========================================================================
    # KNOWLEDGE AGGREGATION
    # =========================================================================

    async def get_all_knowledge_uids(self, uid: str) -> Result[set[str]]:
        """
        Get all KU UIDs across all steps in this path.

        Args:
            uid: LP UID

        Returns:
            Result[set[str]]: All unique KU UIDs
        """
        ...

    async def get_knowledge_scope_summary(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get comprehensive knowledge scope summary.

        Returns:
            Result[dict]: Scope including:
                - total_unique_kus: Count of unique KUs
                - primary_ku_count: Core knowledge count
                - supporting_ku_count: Supporting knowledge count
                - total_steps: Step count
                - complexity_score: Overall difficulty
        """
        ...

    # =========================================================================
    # MOTIVATIONAL ALIGNMENT
    # =========================================================================

    async def get_aligned_goals(self, uid: str) -> Result[list[str]]:
        """
        Get goal UIDs this path supports.

        Args:
            uid: LP UID

        Returns:
            Result[list[str]]: Goal UIDs
        """
        ...

    async def get_embodied_principles(self, uid: str) -> Result[list[str]]:
        """
        Get principle UIDs this path embodies.

        Args:
            uid: LP UID

        Returns:
            Result[list[str]]: Principle UIDs
        """
        ...

    async def get_motivational_context(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get complete motivational context for this path.

        Returns:
            Result[dict]: Context including:
                - aligned_goals: Goal details
                - embodied_principles: Principle details
                - motivational_strength: Score (0.0-1.0)
        """
        ...

    # =========================================================================
    # MILESTONE MANAGEMENT
    # =========================================================================

    async def get_milestone_events(self, uid: str) -> Result[list[str]]:
        """
        Get milestone event UIDs for this path.

        Args:
            uid: LP UID

        Returns:
            Result[list[str]]: Milestone event UIDs
        """
        ...

    async def get_checkpoint_schedule(self, uid: str) -> Result[list[int]]:
        """
        Get checkpoint week numbers for this path.

        Args:
            uid: LP UID

        Returns:
            Result[list[int]]: Week numbers for checkpoints
        """
        ...

    async def get_next_checkpoint_week(
        self,
        uid: str,
        current_week: int,
    ) -> Result[int | None]:
        """
        Get the next checkpoint week after current week.

        Args:
            uid: LP UID
            current_week: Current week number

        Returns:
            Result[int | None]: Next checkpoint week or None
        """
        ...


# =============================================================================
# EXERCISE OPERATIONS
# =============================================================================


@runtime_checkable
class ExerciseOperations(Protocol):
    """Reusable LLM instruction template operations.

    Exercise is a Curriculum subclass (EntityType.EXERCISE) — instruction
    templates for LLM-based feedback on student submissions.

    Route consumer: exercises_api.py (via CRUDRouteFactory)
    Implementation: ExerciseService

    See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
    """

    async def create_exercise(
        self,
        user_uid: str,
        name: str,
        instructions: str,
        model: str = "claude-sonnet-4-6",
        context_notes: list[str] | None = None,
        domain: Any | None = None,
        scope: Any = ...,
        due_date: date | None = None,
        processor_type: Any = ...,
        group_uid: str | None = None,
    ) -> Result[Any]:
        """Create an Exercise. Returns Result[Exercise]."""
        ...

    async def get_exercise(self, uid: str) -> Result[Exercise]:
        """Get exercise by UID. Returns Result[Exercise], or not-found error."""
        ...

    async def list_user_exercises(
        self,
        user_uid: str,
        active_only: bool = True,
    ) -> Result[list[Any]]:
        """List user's exercises. Returns Result[list[Exercise]]."""
        ...

    async def update_exercise(
        self,
        uid: str,
        name: str | None = None,
        instructions: str | None = None,
        model: str | None = None,
        context_notes: list[str] | None = None,
        domain: Any | None = None,
        is_active: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[Any]:
        """Update an exercise. Returns Result[Exercise]."""
        ...

    async def delete_exercise(self, uid: str) -> Result[bool]:
        """Delete an exercise. Returns Result[bool]."""
        ...

    # Curriculum linking
    async def link_to_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """Link exercise to curriculum KU via REQUIRES_KNOWLEDGE."""
        ...

    async def unlink_from_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """Remove REQUIRES_KNOWLEDGE relationship."""
        ...

    async def get_required_knowledge(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
        """Get curriculum KUs required by an exercise."""
        ...

    async def get_exercises_for_curriculum(
        self, curriculum_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get exercises that require a specific curriculum KU."""
        ...


class RevisedExerciseOperations(Protocol):
    """Revised exercise operations for the five-phase learning loop.

    RevisedExercise is a UserOwnedEntity (teacher-owned, student-targeted)
    that provides targeted revision instructions after SubmissionReport.

    Route consumer: revised_exercises_api.py
    Implementation: RevisedExerciseService
    """

    async def create_revised_exercise(
        self,
        teacher_uid: str,
        original_exercise_uid: str,
        report_uid: str,
        student_uid: str,
        instructions: str,
        title: str | None = None,
        model: str = "claude-sonnet-4-6",
        context_notes: list[str] | None = None,
        feedback_points_addressed: list[str] | None = None,
        revision_rationale: str | None = None,
    ) -> Result[Any]:
        """Create a RevisedExercise. Returns Result[RevisedExercise]."""
        ...

    async def get_revised_exercise(self, uid: str) -> Result[Any]:
        """Get revised exercise by UID. Returns Result[RevisedExercise]."""
        ...

    async def list_for_teacher(self, teacher_uid: str) -> Result[list[Any]]:
        """List revised exercises owned by a teacher."""
        ...

    async def list_for_student(
        self, student_uid: str, teacher_uid: str | None = None
    ) -> Result[list[Any]]:
        """List revised exercises targeting a student.

        Args:
            student_uid: The student whose revisions to list.
            teacher_uid: If provided, scope to revisions owned by this teacher.
        """
        ...

    async def get_revision_chain(self, exercise_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all revisions in the chain for an original exercise."""
        ...

    async def update_revised_exercise(
        self,
        uid: str,
        instructions: str | None = None,
        title: str | None = None,
        model: str | None = None,
        context_notes: list[str] | None = None,
        feedback_points_addressed: list[str] | None = None,
        revision_rationale: str | None = None,
    ) -> Result[Any]:
        """Update a revised exercise."""
        ...

    async def delete_revised_exercise(self, uid: str) -> Result[bool]:
        """Delete a revised exercise."""
        ...


# =============================================================================
# MOC OPERATIONS - REMOVED JANUARY 2026
# =============================================================================
#
# MocOperations protocol removed January 2026 - MOC is now KU-based.
#
# A KU "is" a MOC when it has outgoing ORGANIZES relationships to other KUs.
# This is an emergent identity pattern, not a separate entity type.
#
# For organization operations, use:
# - LessonOrganizationService (sub-service of LessonService) for graph navigation
# - LessonOperations protocol for type-safe access
#
# See: /docs/domains/moc.md for full architecture documentation

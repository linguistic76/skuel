"""
Curriculum Protocols - Consistent Protocol Hierarchy for KU, PS, LP
====================================================================

*Last updated: 2026-07-26*

This module provides a CONSISTENT protocol hierarchy for the three
curriculum domains (KU, PS, LP) plus Exercise, parallel to BackendOperations
for Activity domains.

Any entity can organize other entities via ORGANIZES relationships (emergent identity).
Organization methods are part of PsOperations protocol.

Design Principle: "Curriculum domains follow the same patterns as Activity domains"
-------------------------------------------------------------------------------

The Three Curriculum Domains + Exercise:
    - KU (Point topology): Atomic knowledge unit
    - PS (Edge topology): Sequential step aggregating KUs
    - LP (Path topology): Complete learning sequence of PSs
    - Exercise (Template): LLM instruction template for student submissions

Protocol Hierarchy:
    - CurriculumOperations[T]: Base protocol inheriting BackendOperations
    - PsOperations: Extends CurriculumOperations[PathStep] with PS-specific methods
    - LpOperations: Extends CurriculumOperations[LearningPath] with LP-specific methods
    - ExerciseOperations: Standalone protocol for Exercise instruction templates

Narrow ``*BackendOperations`` slices (July 2026) — each is what exactly one
service types ``self.backend`` against, so a wide protocol's unrelated methods
are not advertised at that seam:
    - PsOrganizesBackendOperations   → PsOrganizationService
    - PsProgressBackendOperations    → PsProgressService
    - PsIntelligenceBackendOperations → PsIntelligenceService
    - LpProgressBackendOperations    → LpProgressService (LpOperations inherits it)
``LpOperations`` inherits its slice, keeping one source for those signatures.
The PS slices deliberately stand alone: ``PsOperations`` is dual-layer (it types
both ``PsCoreService.backend`` and the ``PsService`` facade via
``EntityExtractor.knowledge_service``) and its signatures are the *service*'s,
not the backend's — inheriting would advertise backend signatures to facade
holders. See PR #826.

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
    PsOperations(CurriculumOperations[PathStep], Protocol):
        ├── get_knowledge_uids() → Result[list[str]]
        ├── get_path_steps() → Result[list[PathStep]]
        └── get_practice_summary() → Result[dict]

    LpOperations(CurriculumOperations[LearningPath], Protocol):
        ├── get_next_step() → Result[PathStep | None]
        ├── calculate_progress() → Result[float]

Return Type Consistency
-----------------------
ALL methods return Result[T] - no raw dicts, no None returns for not-found.
This aligns with Activity domain patterns per CLAUDE.md.

Usage
-----
    from core.ports import CurriculumOperations, PsOperations

    class PsCoreService(BaseService[PsOperations, PathStep]):
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

from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from core.models.type_hints import Neo4jProperties, UserUID
from core.models.update_contracts import RawChanges
from core.ports.query_types import (
    CurriculumExerciseResult,
    KuEdgeRow,
    KuEmbeddingRow,
    LearningGapResult,
    LearningRecommendationResult,
    LpKnowledgeScopeSummary,
    OrganizerResult,
    PrereqMasteryResult,
    PsDeleteStepRow,
    PsGuidanceCountsRow,
    PsKnowledgeSummaryResult,
    PsPracticeCountsRow,
    PsPracticeSummaryResult,
    PsPrerequisiteStepUidsRow,
    PsTaughtKuUidRow,
    ReadyToLearnResult,
    ReinforcementCandidateResult,
    RequiredKnowledgeResult,
    RevisionChainResult,
    RootOrganizerResult,
    SubstantiationSummaryResult,
    UserMasteryResult,
    UserProgressResult,
)

from .base_protocols import BackendOperations, GraphRelationshipOperations

if TYPE_CHECKING:
    from datetime import date

    from core.infrastructure.relationships.semantic_relationships import (
        SemanticRelationshipType,
        SemanticTriple,
    )
    from core.models.enums import Domain
    from core.models.enums.neo_labels import NeoLabel
    from core.models.enums.user_entry_enums import ExerciseScope
    from core.models.exercises.exercise import Exercise
    from core.models.exercises.revised_exercise import RevisedExercise
    from core.models.ku.ku import Ku  # noqa: F401 — used in BackendOperations["Ku"]
    from core.models.pathways.learning_path import LearningPath
    from core.models.pathways.path_step import PathStep
    from core.models.protocols.domain_model_protocol import DomainModelProtocol
    from core.models.relationship_names import RelationshipName
    from core.utils.result_simplified import Result


# =============================================================================
# CURRICULUM BASE PROTOCOL
# =============================================================================


@runtime_checkable
class CurriculumOperations[T: "DomainModelProtocol"](
    BackendOperations[T], GraphRelationshipOperations, Protocol
):
    """
    Base protocol for all curriculum domain backends (KU, PS, LP).

    Inherits:
        - BackendOperations[T]: Full CRUD, relationships, traversal, search
        - GraphRelationshipOperations: get_related_uids(), count_related()

    Adds curriculum-specific methods that all three domains share:
        - get_with_content(): Fetch entity with full content
        - get_with_context(): Fetch entity with graph neighborhood
        - get_prerequisites(): Fetch prerequisite entities
        - get_hierarchy(): Fetch hierarchical structure

    Type Parameter:
        T: The domain model (Curriculum, PathStep, or LearningPath)

    Design Rationale:
        Curriculum domains share patterns that Activity domains don't need:
        - Content retrieval (markdown, learning materials)
        - Prerequisite chains (knowledge dependencies)
        - Hierarchical structures (KU→PS→LP aggregation)

        By inheriting BackendOperations, curriculum domains get ALL the same
        capabilities as Activity domains (CRUD, relationships, search, traversal)
        PLUS these curriculum-specific additions.

    Example:
        class KuUniversalBackend(UniversalNeo4jBackend[Ku], CurriculumOperations[Ku]):
            async def get_with_content(self, uid: str) -> Result[Ku]:
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
    # boundary: get_hierarchy returns dict[str, Any] — shape varies by entity type
    # (KU vs PS vs LP each return different hierarchy structures from Cypher).

    async def get_hierarchy(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get hierarchical structure for this entity.

        Returns the entity's position in the curriculum hierarchy:
        - For KU: Which PS and LP contain it
        - For PS: Which LP contains it, which KUs it aggregates
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
        user_uid: UserUID,
        ku_uid: str,
        time_spent_seconds: int = 0,
    ) -> Result[bool]:
        """Record that a user viewed a knowledge unit."""
        ...

    async def mark_in_progress(self, user_uid: UserUID, ku_uid: str) -> Result[bool]:
        """Mark a KU as in-progress for the user."""
        ...

    async def get_user_progress(self, user_uid: UserUID, ku_uid: str) -> Result[UserProgressResult]:
        """Get user's progress on a specific KU."""
        ...


# =============================================================================
# DOMAIN-SPECIFIC PROTOCOLS
# =============================================================================


@runtime_checkable
class KuOperations(BackendOperations["Ku"], Protocol):
    """
    Knowledge Unit (KU) specific operations.

    Extends BackendOperations with KU-specific methods for:
    - Reverse traversal (PathSteps using this KU)
    - Namespace and alias search
    - Substance tracking
    - Relationship queries (related, broader, narrower, etc.)
    - Prerequisite and dependency analysis
    - Learning state management (IN_PROGRESS, MASTERED)

    Neo4j: KU nodes are :Entity:Ku{entity_type='ku'}
    UID Format: "ku_{slug}_{random}"
    """

    # =========================================================================
    # REVERSE TRAVERSAL
    # =========================================================================

    async def get_path_steps_using(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all PathSteps that use this atomic Ku via USES_KU."""
        ...

    async def get_cited_resources(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get the curated Resources this Ku cites via CITES_RESOURCE.

        Rows carry a ``resource`` map plus the edge's ``locator`` anchor; the
        service flattens them. Implementation: ``KuBackend.get_cited_resources``
        (the entity-agnostic ``_KnowledgeContextMixin`` variant is PS-oriented
        and is not mixed into the lightweight Ku backend).
        """
        ...

    async def get_usage_summary(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count path steps using, training, and organized children."""
        ...

    async def is_trained(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if any PathStep trains this Ku via TRAINS_KU."""
        ...

    async def is_organized(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Check if this Ku has ORGANIZES children (acts as MOC)."""
        ...

    async def get_organization_depth(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get depth of the ORGANIZES tree below this Ku."""
        ...

    # =========================================================================
    # ALIAS SEARCH
    # =========================================================================

    async def search_by_alias(self, alias: str) -> Result[list[Neo4jProperties]]:
        """Search Kus by alias (case-insensitive substring)."""
        ...

    async def nous_subtopic_pairs(self) -> Result[list[Neo4jProperties]]:
        """Distinct co-occurring (nous, nous_subtopic) pairs across :Ku + :PathStep."""
        ...

    # =========================================================================
    # SUBSTANCE METRICS
    # =========================================================================

    async def batch_increment_substance(
        self,
        ku_uids: list[str],
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for multiple KUs and connected PathSteps."""
        ...

    async def increment_substance(
        self,
        ku_uid: str,
        metric: str,
        timestamp_field: str,
        timestamp_str: str,
    ) -> Result[int]:
        """Atomically increment a substance metric for a single KU and connected PathSteps."""
        ...

    # =========================================================================
    # RELATIONSHIP QUERIES
    # =========================================================================

    async def get_related_knowledge_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get related knowledge units (RELATED_TO relationship)."""
        ...

    async def get_broader_concept_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get broader concepts (HAS_BROADER relationship)."""
        ...

    async def get_narrower_concept_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get narrower concepts (HAS_NARROWER relationship)."""
        ...

    async def get_learning_path_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get learning paths containing this KU."""
        ...

    async def get_applying_task_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get tasks applying this knowledge."""
        ...

    async def get_practicing_event_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get events practicing this knowledge."""
        ...

    async def get_reinforcing_habit_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get habits reinforcing this knowledge."""
        ...

    # =========================================================================
    # PREREQUISITE & DEPENDENCY QUERIES
    # =========================================================================

    async def get_unmastered_prerequisites(
        self, ku_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get unmastered prerequisites for a knowledge unit (depth 1..3)."""
        ...

    async def count_dependents(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Count entities that depend on this knowledge unit via REQUIRES_KNOWLEDGE."""
        ...

    # =========================================================================
    # LEARNING STATE
    # =========================================================================

    async def mark_in_progress(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Mark a Ku as actively being studied (IN_PROGRESS relationship)."""
        ...

    async def mark_mastered(
        self,
        user_uid: UserUID,
        ku_uid: str,
        mastery_score: float = 0.7,
        method: str = "self_report",
    ) -> Result[list[Neo4jProperties]]:
        """Mark a Ku as understood/mastered by the user."""
        ...

    async def get_ku_learning_state(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get user's learning state for a Ku (IN_PROGRESS, MASTERED, MARKED_AS_READ)."""
        ...

    async def count_studying_kus(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Count Kus the user has marked as studying."""
        ...

    async def get_user_learning_states(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all Kus with their learning state for a user."""
        ...


@runtime_checkable
class PsOrganizesBackendOperations(Protocol):
    """ORGANIZES relationship management — the backend-layer slice.

    MOC is emergent identity: any Entity with outgoing ORGANIZES edges is an
    organizer. This ISP slice is what ``PsOrganizationService`` types
    ``self.backend`` against — deliberately narrow, and deliberately *backend*
    layer. The service's own ``get_organization_view`` composes these reads with
    ``PsCoreService`` lookups and is NOT a backend operation; declaring it on a
    backend protocol is what made the wider contract unsatisfiable.

    Implementation: ``_OrganizesMixin`` (shared with ``UserEntryBackend`` —
    see ``UserEntryOrganizesOperations`` for that domain's read-only slice).
    """

    async def organize(self, parent_uid: str, child_uid: str, order: int = 0) -> Result[bool]:
        """Create ORGANIZES relationship between two entities."""
        ...

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove ORGANIZES relationship between two entities."""
        ...

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        """Change the order of a child entity within its parent."""
        ...

    async def is_organizer(self, entity_uid: str) -> Result[bool]:
        """Check if an entity has organized children."""
        ...

    async def get_organized_children(
        self, parent_uid: str, limit: int | None = None
    ) -> Result[list[OrganizerResult]]:
        """Direct ORGANIZES children of an entity, ordered by position."""
        ...

    async def find_organizers(self, entity_uid: str) -> Result[list[OrganizerResult]]:
        """Find all parent entities that organize the given entity."""
        ...

    async def list_root_organizers(self, limit: int = 50) -> Result[list[RootOrganizerResult]]:
        """List entities that organize others but are not themselves organized."""
        ...


@runtime_checkable
class PsProgressBackendOperations(Protocol):
    """KU → PathStep progress reads — the backend-layer slice.

    ``PsProgressService`` reacts to ``KnowledgeMastered`` and recomputes PathStep
    progress from these two reads only. Signatures are lifted from ``PsBackend``
    itself, not from ``PsOperations``.

    Deliberately NOT inherited by ``PsOperations``: that protocol is dual-layer —
    it types ``PsCoreService.backend`` *and* ``EntityExtractor.knowledge_service``
    (the ``PsService`` facade) — and is satisfied by neither ``PsBackend`` nor
    ``PsService``. Making it inherit a backend slice would advertise backend
    signatures to facade holders; the same reason ``PsOrganizesBackendOperations``
    above stands alone. See PR #826.
    """

    async def find_path_steps_for_ku(self, ku_uid: str) -> Result[list[str]]:
        """Find all PathStep UIDs that contain a given KU."""
        ...

    async def get_ku_completion_progress(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """Return total and mastered KU counts for PathStep progress."""
        ...


@runtime_checkable
class PsIntelligenceBackendOperations(Protocol):
    """Persistence port for PathStep readiness / practice / guidance reads.

    ``PsIntelligenceService`` composes these seven reads into readiness
    assessment and practice-completeness scoring. All the Cypher lives below the
    boundary in ``adapters/persistence/neo4j/ps_intelligence_backend.py``
    (ADR-044); the backend is built at the composition root and injected, so the
    service never imports the adapter (SKUEL022).

    Signatures are a 1:1 mirror of ``PsIntelligenceBackend``'s entire public
    surface — the class exists solely to serve this one service, so the slice and
    the class coincide. Each read declares a per-query ``Ps*Row`` TypedDict keyed
    to its RETURN clause; the service aggregates the rows into the
    ``*Result``/``*Analytics`` shapes it returns. The row types bind every
    *consumer* statically, but a Cypher alias rename cannot be caught by typing —
    the adapter's ``_to_*_rows`` processors enforce that at runtime instead.
    """

    async def fetch_prerequisite_step_uids(
        self, ps_uid: str
    ) -> Result[list[PsPrerequisiteStepUidsRow]]:
        """Return a single row with ``prereq_uids`` (collected REQUIRES_STEP targets)."""
        ...

    async def fetch_practice_counts(self, ps_uid: str) -> Result[list[PsPracticeCountsRow]]:
        """Return per-domain practice-opportunity counts for a PathStep."""
        ...

    async def fetch_guidance_counts(self, ps_uid: str) -> Result[list[PsGuidanceCountsRow]]:
        """Return principle/choice guidance counts for a PathStep."""
        ...

    async def has_prerequisites(self, ps_uid: str) -> Result[bool]:
        """True if the PathStep has REQUIRES_STEP or REQUIRES_KNOWLEDGE edges."""
        ...

    async def has_guidance(self, ps_uid: str) -> Result[bool]:
        """True if the PathStep has principle or choice guidance edges."""
        ...

    async def has_practice_opportunities(self, ps_uid: str) -> Result[bool]:
        """True if the PathStep has any of the 6 activity-domain practice edges."""
        ...

    async def fetch_taught_ku_uids(self, ps_uid: str) -> Result[list[PsTaughtKuUidRow]]:
        """Return ``ku_uid`` rows for the KUs taught by a PathStep."""
        ...


@runtime_checkable
class PsOperations(CurriculumOperations["PathStep"], Protocol):
    """
    PathStep (PS) specific operations.

    Extends CurriculumOperations with PS-specific methods for:
    - Knowledge aggregation (PS aggregates KUs)
    - Practice integration (habits, tasks, events)
    - Path integration (PS can be standalone or part of LP)

    Neo4j: PS nodes are :Entity:PathStep{entity_type='path_step'}
    UID Format: "ps:{random}" (e.g., "ps:a1b2c3d4")
    """

    # =========================================================================
    # KNOWLEDGE AGGREGATION
    # =========================================================================

    async def get_knowledge_uids(self, uid: str) -> Result[list[str]]:
        """
        Get all KU UIDs aggregated by this step.

        Returns both primary and supporting knowledge UIDs.

        Args:
            uid: PS UID

        Returns:
            Result[list[str]]: All KU UIDs in this step
        """
        ...

    # =========================================================================
    # KNOWLEDGE RELATIONSHIPS (CONTAINS_KNOWLEDGE edges — written at ingestion)
    # =========================================================================

    async def get_knowledge_summary(self, ps_uid: str) -> Result[PsKnowledgeSummaryResult]:
        """Aggregate count and UIDs of knowledge in this step."""
        ...

    async def nous_subtopic_pairs(self) -> Result[list[Neo4jProperties]]:
        """Distinct co-occurring (nous, nous_subtopic) pairs on :PathStep."""
        ...

    # =========================================================================
    # PRACTICE INTEGRATION
    # =========================================================================

    async def get_practice_summary(self, uid: str) -> Result[PsPracticeSummaryResult]:
        """
        Get practice integration summary for this step.

        Returns counts of activity entities (habits, tasks, events, goals,
        principles, choices) connected to this path step, plus total.
        """
        ...

    async def get_practice_tasks(self, uid: str) -> Result[list[str]]:
        """
        Get task UIDs for practicing this step.

        Args:
            uid: PS UID

        Returns:
            Result[list[str]]: Task UIDs
        """
        ...

    async def get_practice_habits(self, uid: str) -> Result[list[str]]:
        """
        Get habit UIDs that reinforce this step.

        Args:
            uid: PS UID

        Returns:
            Result[list[str]]: Habit UIDs
        """
        ...

    async def get_practice_events(self, uid: str) -> Result[list[str]]:
        """
        Get event UIDs associated with this step.

        Args:
            uid: PS UID

        Returns:
            Result[list[str]]: Event UIDs
        """
        ...

    # =========================================================================
    # PATH INTEGRATION
    # =========================================================================

    async def get_path_steps(self, path_uid: str) -> Result[list[PathStep]]:
        """
        Get all steps for a learning path, in sequence order.

        Args:
            path_uid: LP UID

        Returns:
            Result[list[PathStep]]: Ordered list of steps
        """
        ...

    async def get_parent_path(self, uid: str) -> Result[str | None]:
        """
        Get the parent LP UID for this step, if any.

        Args:
            uid: PS UID

        Returns:
            Result[str | None]: Parent LP UID or None if standalone
        """
        ...

    async def is_standalone(self, uid: str) -> Result[bool]:
        """
        Check if this step exists independently (not part of a path).

        Args:
            uid: PS UID

        Returns:
            Result[bool]: True if standalone
        """
        ...

    # =========================================================================
    # SEARCH QUERIES
    # =========================================================================

    async def get_standalone_steps(self, limit: int = 50) -> Result[list[PathStep]]:
        """Get PathStep nodes not belonging to any learning path."""
        ...

    async def get_prioritized_steps(
        self, user_uid: UserUID, limit: int = 20
    ) -> Result[list[PathStep]]:
        """Get PathStep nodes prioritized by user context."""
        ...

    # =========================================================================
    # GUIDANCE INTEGRATION
    # =========================================================================

    async def get_guiding_principles(self, uid: str) -> Result[list[str]]:
        """
        Get principle UIDs that guide this step.

        Args:
            uid: PS UID

        Returns:
            Result[list[str]]: Principle UIDs
        """
        ...

    async def get_informed_choices(self, uid: str) -> Result[list[str]]:
        """
        Get choice UIDs informed by this step.

        Args:
            uid: PS UID

        Returns:
            Result[list[str]]: Choice UIDs
        """
        ...

    # =========================================================================
    # SEMANTIC RELATIONSHIPS    # =========================================================================

    async def get_semantic_links(self, uid: str) -> Result[list[str]]:
        """Get semantically related entity UIDs."""
        ...

    async def get_related_by_domain(
        self,
        uid: str,
        domain: str,
    ) -> Result[list[PathStep]]:
        """Get related PathSteps filtered by domain."""
        ...

    # =========================================================================
    # SUBSTANCE TRACKING    # =========================================================================

    async def get_substance_score(self, uid: str) -> Result[float]:
        """Get the substance score for a PathStep (0.0-1.0)."""
        ...

    async def get_substantiation_summary(self, uid: str) -> Result[SubstantiationSummaryResult]:
        """Get detailed substantiation breakdown."""
        ...

    # =========================================================================
    # CURRICULUM INTEGRATION    # =========================================================================

    async def get_path_steps_using(self, uid: str) -> Result[list[str]]:
        """Get PS UIDs that include this entity via USES_KU."""
        ...

    async def get_learning_paths_featuring(self, uid: str) -> Result[list[str]]:
        """Get LP UIDs that feature this entity."""
        ...

    # =========================================================================
    # ORGANIZATION (ORGANIZES relationships)
    # =========================================================================
    # Deliberately NOT inherited from ``PsOrganizesBackendOperations``: these are
    # the *service-facing* shapes (``PsService.get_organized_children(entity_uid)``),
    # and they diverge from the backend's (``_OrganizesMixin`` takes
    # ``parent_uid`` plus an optional ``limit``). Same operations, two layers —
    # collapsing them would promise ``limit`` to callers holding a ``PsService``.
    # Type ``self.backend`` against the backend slice; keep this one for consumers
    # that hold the facade (e.g. ``EntityExtractor.knowledge_service``).

    async def organize(self, parent_uid: str, child_uid: str, order: int = 0) -> Result[bool]:
        """Create ORGANIZES relationship between two entities."""
        ...

    async def unorganize(self, parent_uid: str, child_uid: str) -> Result[bool]:
        """Remove ORGANIZES relationship between two entities."""
        ...

    async def reorder(self, parent_uid: str, child_uid: str, new_order: int) -> Result[bool]:
        """Change the order of a child entity within its parent."""
        ...

    async def is_organizer(self, entity_uid: str) -> Result[bool]:
        """Check if an entity has organized children."""
        ...

    async def find_organizers(self, entity_uid: str) -> Result[list[OrganizerResult]]:
        """Find all parent entities that organize the given entity."""
        ...

    async def list_root_organizers(self, limit: int = 50) -> Result[list[RootOrganizerResult]]:
        """List entities that organize others but are not themselves organized."""
        ...

    async def get_organized_children(self, entity_uid: str) -> Result[list[OrganizerResult]]:
        """Get direct children organized by ORGANIZES relationship."""
        ...

    # =========================================================================
    # PRACTICE + AI    # =========================================================================

    async def find_kus_practiced_by_event(
        self, event_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {ku_uid}
        """Find KU UIDs practiced by a completed event via PRACTICES relationship."""
        ...

    async def increment_practice_count(
        self, ku_uid: str, occurred_at: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {new_count}
        """Increment practice count and update last_practiced_date."""
        ...

    # Chunk-level vector search lives on VectorSearchBackend, not on the
    # PathStep backend — see core/ports/vector_search_protocols.py
    # (semantic_search_chunks) and adapters/persistence/neo4j/vector_search_backend.py.

    # =========================================================================
    # SEARCH    # =========================================================================

    async def find_similar_by_keywords(
        self, uid: str, limit: int
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns full entity node properties
        """Find similar entities using keyword matching."""
        ...

    async def search_by_keywords(
        self, query_text: str, limit: int
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns full entity node properties
        """Keyword-based search using CONTAINS on title/summary/tags."""
        ...

    # =========================================================================
    # APPLICATION DISCOVERY    # =========================================================================

    async def find_connected_activities(
        self,
        ku_uid: str,
        user_uid: UserUID,
        node_label: NeoLabel,
        rel_types: list[RelationshipName | str],
        filters: dict[str, Any] | None = None,
        order_by: str = "created_at",
        limit: int = 10,
        reverse_direction: bool = False,
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {entity_uid}
        """Find activity entities connected via graph relationships."""
        ...

    async def find_path_steps_containing_ku(
        self, ku_uid: str, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {step_uid}
        """Find path steps that contain a KU via CONTAINS_KNOWLEDGE."""
        ...

    async def find_learning_paths_teaching_ku(
        self, ku_uid: str, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {path_uid}
        """Find learning paths that teach a KU via step chain."""
        ...

    # =========================================================================
    # CONTEXT    # =========================================================================

    async def find_ready_to_learn(
        self, mastered_uids: list[str], domain: str | None, limit: int
    ) -> Result[list[ReadyToLearnResult]]:
        """Find entities the user is ready to learn (prerequisites >= 70% met)."""
        ...

    async def find_learning_gaps(
        self, goal_uids: list[str], mastered_uids: list[str], limit: int
    ) -> Result[list[LearningGapResult]]:
        """Find entities required by goals but not mastered."""
        ...

    async def find_reinforcement_candidates(
        self, uids: list[str], active_goal_uids: list[str]
    ) -> Result[list[ReinforcementCandidateResult]]:
        """Get details + goal relevance for reinforcement candidates."""
        ...

    # =========================================================================
    # SEMANTIC OPERATIONS    # =========================================================================

    async def create_semantic_relationship(
        self, triple: SemanticTriple
    ) -> Result[list[dict[str, Any]]]:  # boundary: neo4j record shape
        """Persist a single semantic triple as a MERGE'd relationship.

        Takes the domain triple; the adapter authors the Cypher below the
        hexagonal boundary (ADR-044).
        """
        ...

    async def query_semantic_neighborhood(
        self,
        uid: str,
        semantic_types: list[SemanticRelationshipType],
        depth: int,
        min_confidence: float,
    ) -> Result[list[dict[str, Any]]]:  # boundary: variable-depth graph traversal
        """Query semantic neighborhood."""
        ...

    async def delete_semantic_relationship(
        self,
        rel_name: str,
        subject_uid: str,
        object_uid: str,
        semantic_type: str | None = None,
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {deleted}
        """Delete a semantic relationship between two entities."""
        ...

    async def query_relationships_by_type(
        self,
        uid: str,
        rel_name: str,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        semantic_type: str | None = None,
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns target node + rel properties
        """Find relationships by type and direction."""
        ...

    async def discover_semantic_bridges(
        self, uid: str, target_domain: str | None, limit: int
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns target node + bridge metadata
        """Discover cross-domain semantic bridges via shared concepts."""
        ...

    async def infer_transitive_relationships(
        self, uid: str, limit: int
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns target node + inference metadata
        """Infer potential relationships via transitive closure."""
        ...

    # =========================================================================
    # GRAPH    # =========================================================================

    async def link_prerequisite(
        self, unit_uid: str, prereq_uid: str, is_mandatory: bool
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns relationship properties
        """Create REQUIRES_KNOWLEDGE relationship."""
        ...

    async def link_parent_child(
        self, parent_uid: str, child_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns relationship properties
        """Create HAS_NARROWER hierarchy relationship."""
        ...

    async def query_user_mastery_for_prereqs(
        self, user_uid: UserUID, prereq_uids: list[str]
    ) -> Result[list[PrereqMasteryResult]]:
        """Query user MASTERED + IN_PROGRESS state for prerequisite KUs."""
        ...

    async def find_learning_recommendations(
        self, user_uid: UserUID, domain: str | None, limit: int
    ) -> Result[list[LearningRecommendationResult]]:
        """Find entities user is ready to learn based on mastery and prerequisites."""
        ...

    async def compute_hub_scores(
        self,
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {updated_count}
        """Compute and cache degree centrality hub scores."""
        ...

    async def query_foundational_knowledge(
        self, domain: str | None, min_hub_score: int, limit: int
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns full entity node properties
        """Query high-hub-score entities (foundational concepts)."""
        ...

    async def find_prerequisite_chain(
        self, uid: str, depth: int, min_confidence: float
    ) -> Result[list[dict[str, Any]]]:  # boundary: variable-depth traversal
        """Find prerequisite chain."""
        ...

    async def find_next_steps(
        self, uid: str, limit: int
    ) -> Result[list[dict[str, Any]]]:  # boundary: traversal via CypherGenerator
        """Find entities that have this one as a prerequisite."""
        ...

    # =========================================================================
    # ADAPTIVE    # =========================================================================

    async def track_mastery_completion(
        self, user_uid: UserUID, ku_uid: str, completion_time_minutes: int
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns MASTERED relationship properties
        """Create/update MASTERED relationship."""
        ...

    async def query_user_masteries(self, user_uid: UserUID) -> Result[list[UserMasteryResult]]:
        """Query all MASTERED relationships with full metadata for a user."""
        ...

    async def query_active_learning_paths(self, user_uid: UserUID) -> Result[list[LearningPath]]:
        """Query user's active/in-progress learning paths as typed models."""
        ...

    async def query_completed_learning_paths(
        self, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {lp_uid}
        """Query UIDs of completed learning paths for a user."""
        ...

    # =========================================================================
    # KU COMPLETION PROGRESS (direct USES_KU/CONTAINS_KNOWLEDGE traversal)
    # =========================================================================

    async def get_ku_completion_progress(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """Return total and mastered KU counts for PathStep progress."""
        ...

    # =========================================================================
    # CORE CRUD QUERIES (backend-level Cypher)
    # =========================================================================
    # boundary: LP CRUD methods return list[dict[str, Any]] — raw Cypher node
    # properties from CREATE/SET/DELETE operations with variable RETURN clauses.

    async def create_step_node(
        self,
        params: dict[str, Any],
        has_knowledge: bool = False,
        path_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Create step node with conditional knowledge and path relationships."""
        ...

    async def get_step_with_knowledge(self, uid: str) -> Result[PathStep | None]:
        """Get a step (with its CONTAINS_KNOWLEDGE UIDs) as a typed model, or None."""
        ...

    async def update_step_fields(
        self, uid: str, set_clauses: list[str], params: dict[str, Any]
    ) -> Result[PathStep | None]:
        """Update step fields; return the updated step as a typed model (None if absent)."""
        ...

    async def delete_step_node(self, uid: str) -> Result[list[PsDeleteStepRow]]:
        """Delete a step node and return deletion count."""
        ...

    async def list_steps_raw(
        self,
        path_uid: str | None,
        limit: int,
        offset: int,
        order_field: str,
        order_direction: str,
        user_uid: UserUID | None = None,
    ) -> Result[list[PathStep]]:
        """List steps (with knowledge UIDs) as typed models, with pagination and filters."""
        ...

    # =========================================================================
    # LEARNING STATE TRACKING (VIEWED / IN_PROGRESS / MASTERED / bookmarks)
    # =========================================================================
    # Per-user progress edges on :Entity nodes, consumed by PsMasteryService.
    # These return raw Cypher rows the service interprets into UserKuProgress /
    # LearningState. The rows are genuinely heterogeneous — bool flags, counts,
    # UIDs, and Neo4j temporal objects (.to_native()) in one dict — so they use
    # the dict[str, Any] boundary shared by the raw-row methods above, not the
    # narrower Neo4jProperties value union (which cannot model the temporals).

    async def record_view(
        self, user_uid: UserUID, ku_uid: str, now: str, time_spent: int
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {view_count}
        """Record a user's visit to a KU; repeat visits accumulate count and time spent.

        Idempotent per user/KU pair — the first-viewed timestamp survives later
        visits, and the running view count comes back on the row.
        """
        ...

    async def mark_in_progress(
        self, user_uid: UserUID, ku_uid: str, now: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {success}
        """Put a KU into the user's in-progress set, refreshing last activity.

        Idempotent — re-marking keeps the original start time and progress score.
        """
        ...

    async def mark_as_learning(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {success}
        """Delete MARKED_AS_READ and ensure IN_PROGRESS (Review again action)."""
        ...

    async def mark_as_read(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns the MARKED_AS_READ edge
        """Mark a KU as read for this user, returning the resulting read record.

        Idempotent — the original marked-at time survives a repeat.
        """
        ...

    async def mark_mastered(
        self, user_uid: UserUID, ku_uid: str, now: str, mastery_score: float, method: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {mastery_score}
        """Record mastery of a KU; the highest score ever reported always wins.

        Idempotent — a lower score never regresses the stored mastery or
        confidence, but the reporting method is always the most recent one.
        Returns the score that ended up stored.
        """
        ...

    async def count_in_progress_path_steps(
        self, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {cnt}
        """Count PathSteps with an IN_PROGRESS edge for a user."""
        ...

    async def get_in_progress_path_step_uids(
        self, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {uid}
        """Get UIDs of PathSteps the user is enrolled in (IN_PROGRESS)."""
        ...

    async def check_bookmark(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {is_bookmarked}
        """Check whether a BOOKMARKED edge exists for a user/KU pair."""
        ...

    async def create_bookmark(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: no RETURN (empty rows)
        """Bookmark a KU for the user; idempotent, keeping the original bookmark time."""
        ...

    async def delete_bookmark(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: no RETURN (empty rows)
        """Delete the BOOKMARKED edge for a user/KU pair."""
        ...

    async def get_learning_state_raw(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: flags + counts + Neo4j temporals
        """Fetch all user learning-state edges for one KU in a single query."""
        ...

    async def get_learning_states_batch_raw(
        self, user_uid: UserUID, ku_uids: list[str]
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {ku_uid, has_* flags}
        """Batch-fetch learning states for multiple KUs."""
        ...

    async def detect_path_step_completion(
        self, ku_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {ps_uid, ps_title, all_ku_uids}
        """Find PathSteps whose KUs are all mastered after a KU-mastery event."""
        ...

    async def get_bookmarked_kus(
        self, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {ku_uid}
        """Get all bookmarked KU UIDs for a user."""
        ...

    async def get_all_user_knowledge_status(
        self, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {uid, title, domain, status flags}
        """Get all Ku entities with per-user VIEWED/BOOKMARKED/MASTERED status."""
        ...


@runtime_checkable
class LpProgressBackendOperations(Protocol):
    """KU/PathStep → LearningPath progress reads — the backend-layer slice.

    ``LpProgressService`` reacts to ``KnowledgeMastered`` / ``PathStepCompleted``
    events and recomputes LP progress. It consumes exactly these three reads out
    of ``LpOperations``' ~90-method surface, so it types ``self.backend`` against
    the slice rather than the wide contract (BACKEND_OPERATIONS_ISP.md §
    "Introduce a Minimal Protocol, Have the Broad One Inherit It").

    Implementation: ``_LpProgressMixin`` (mixed into ``LpBackend``); signatures
    are lifted from the mixin itself. ``LpOperations`` inherits this slice, so
    the wide contract is unchanged for every other LP consumer.
    """

    async def get_paths_containing_ku(self, ku_uid: str) -> Result[list[str]]:
        """Get UIDs of all learning paths that include the given KU."""
        ...

    async def get_paths_containing_step(self, ps_uid: str) -> Result[list[str]]:
        """Get UIDs of all learning paths containing a given path step."""
        ...

    async def get_ku_mastery_progress(
        self, lp_uid: str, user_uid: UserUID
    ) -> Result[Neo4jProperties]:
        """Return total and mastered KU counts for a user's progress in a path."""
        ...


@runtime_checkable
class LpOperations(CurriculumOperations["LearningPath"], LpProgressBackendOperations, Protocol):
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

    async def list_user_paths(
        self,
        user_uid: UserUID,
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

    async def get_active_paths(self, user_uid: UserUID) -> Result[list[LearningPath]]:
        """
        Get in-progress learning paths for a user.

        Args:
            user_uid: User UID

        Returns:
            Result[list[LearningPath]]: Paths with progress but not completed
        """
        ...

    # =========================================================================
    # STEP MANAGEMENT (HAS_STEP edges)
    # =========================================================================

    async def get_steps_raw(self, path_uid: str, depth: int = 1) -> Result[list[PathStep]]:
        """Get ordered steps as typed models."""
        ...

    async def get_parent_path_raw(self, step_uid: str) -> Result[LearningPath | None]:
        """Get parent learning path as a typed model, or None."""
        ...

    async def add_step_to_path(
        self, path_uid: str, step_uid: str, sequence: int, order: int = 0
    ) -> Result[bool]:
        """Create HAS_STEP relationship between path and step."""
        ...

    async def remove_step_from_path(self, path_uid: str, step_uid: str) -> Result[bool]:
        """Remove HAS_STEP relationship and reorder remaining steps."""
        ...

    async def reorder_steps(self, path_uid: str, step_uids: list[str]) -> Result[bool]:
        """Batch reorder all steps in a path."""
        ...

    # =========================================================================
    # PATH CRUD (steps composed into metadata["steps"])
    # =========================================================================
    # These return paths with their HAS_STEP steps eagerly loaded into
    # ``metadata["steps"]`` — the composed shape LpCoreService reads and returns.

    async def get_path_with_steps(self, path_uid: str) -> Result[LearningPath | None]:
        """Get a single path with its steps in ``metadata["steps"]``, or None."""
        ...

    async def list_user_paths_with_steps(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[LearningPath]]:
        """List a user's authored/enrolled paths, steps in ``metadata["steps"]``."""
        ...

    async def list_all_paths_with_steps(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[LearningPath]]:
        """List all paths with pagination/sorting, steps in ``metadata["steps"]``."""
        ...

    async def update_path_properties(
        self,
        set_clauses: list[str],
        # boundary: heterogeneous Neo4j query params (uid + mixed-type SET values)
        params: dict[str, Any],
    ) -> Result[LearningPath | None]:
        """Apply pre-validated SET clauses; return the updated path, or None."""
        ...

    async def delete_path_cascade(
        self, path_uid: str
    ) -> Result[list[dict[str, Any]]]:  # boundary: returns {deleted_count}
        """Delete a path and cascade-delete its step nodes; rows carry deleted_count."""
        ...

    async def persist_path_with_steps(
        self,
        user_uid: UserUID,
        # boundary: heterogeneous Neo4j node-property dicts (mixed-type values)
        path_params: dict[str, Any],
        steps_params: list[dict[str, Any]],
    ) -> Result[bool]:
        """Persist a path node (+ User edge), its step nodes, and PS→KU edges."""
        ...

    async def entity_exists(self, uid: str) -> Result[bool]:
        """Check whether an :Entity node with the given UID exists."""
        ...

    # =========================================================================
    # STEP NAVIGATION
    # =========================================================================

    async def get_steps(self, uid: str) -> Result[list[PathStep]]:
        """
        Get all steps in this path, in sequence order.

        Args:
            uid: LP UID

        Returns:
            Result[list[PathStep]]: Ordered steps
        """
        ...

    async def get_next_step(
        self,
        uid: str,
        completed_step_uids: set[str],
    ) -> Result[PathStep | None]:
        """
        Get the next step to complete in this path.

        Args:
            uid: LP UID
            completed_step_uids: Set of already-completed step UIDs

        Returns:
            Result[PathStep | None]: Next step or None if path complete
        """
        ...

    async def get_current_step(self, uid: str, user_uid: UserUID) -> Result[PathStep | None]:
        """
        Get the current in-progress step for a user.

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[PathStep | None]: Current step or None
        """
        ...

    # =========================================================================
    # PROGRESS AND MASTERY
    # =========================================================================

    async def calculate_progress(self, uid: str, user_uid: UserUID) -> Result[float]:
        """
        Calculate overall path progress for a user.

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[float]: Progress percentage (0.0-1.0)
        """
        ...

    async def calculate_mastery(self, uid: str, user_uid: UserUID) -> Result[float]:
        """
        Calculate average mastery across all steps.

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[float]: Average mastery (0.0-1.0)
        """
        ...

    async def is_complete(self, uid: str, user_uid: UserUID) -> Result[bool]:
        """
        Check if path is complete for a user.

        Args:
            uid: LP UID
            user_uid: User UID

        Returns:
            Result[bool]: True if all steps completed
        """
        ...

    async def is_mastered(self, uid: str, user_uid: UserUID) -> Result[bool]:
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

    async def get_all_knowledge_uids(self, path_uid: str) -> Result[set[str]]:
        """
        Get all distinct KU UIDs this path teaches, across every step.

        Traverses the canonical PS→KU union
        (USES_KU|CONTAINS_KNOWLEDGE|TRAINS_KU) and dedupes KUs shared by
        several steps.

        Args:
            path_uid: LP UID

        Returns:
            Result[set[str]]: distinct KU UIDs (empty for an unknown/stepless path)
        """
        ...

    async def get_knowledge_scope_summary(self, path_uid: str) -> Result[LpKnowledgeScopeSummary]:
        """
        Measure the structural facts of a path's KU coverage (one row).

        Reports only what the graph knows — step count, distinct-KU count,
        breadth density, and prerequisite-chain depth. There is deliberately no
        primary/supporting split: PS→KU edges carry no importance weight today,
        so no such distinction is asserted (a KU importance scale is a deferred
        arc). The interpreted ``complexity_score`` is derived from these facts
        at the service layer (analyze_path_knowledge_scope), not here.

        Args:
            path_uid: LP UID

        Returns:
            Result[LpKnowledgeScopeSummary]:
                - total_steps: path steps (a multi-KU step counts once)
                - total_unique_kus: distinct KUs across all steps
                - kus_per_step: mean distinct KUs per step (breadth density)
                - max_prerequisite_depth: longest REQUIRES_KNOWLEDGE chain
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

    # =========================================================================
    # SEARCH QUERIES
    # =========================================================================

    async def get_paths_aligned_with_goal(
        self, goal_uid: str, limit: int = 50
    ) -> Result[list[LearningPath]]:
        """Get learning paths aligned with a goal via ALIGNED_WITH_GOAL."""
        ...

    async def get_paths_by_knowledge(
        self, ku_uid: str, limit: int = 20
    ) -> Result[list[LearningPath]]:
        """Get learning paths that teach a knowledge unit (2-hop via PS)."""
        ...

    async def get_user_paths_prioritized(
        self, user_uid: UserUID, limit: int = 20
    ) -> Result[list[LearningPath]]:
        """Get learning paths prioritized by enrollment, goal alignment, and type."""
        ...

    # ``get_paths_containing_step`` is inherited from LpProgressBackendOperations.

    # =========================================================================
    # INTELLIGENCE QUERIES
    # =========================================================================

    async def validate_path_prerequisites(self, path_uid: str) -> Result[list[dict[str, Any]]]:
        """Run prerequisite validation query for a learning path."""
        ...

    async def identify_path_blockers(
        self, path_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        """Run blocker identification query for a user on a learning path."""
        ...

    async def get_optimal_path_recommendations(
        self, user_uid: UserUID, goal_domain: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Find optimal learning path recommendations for a user."""
        ...

    async def find_learning_sequence(
        self, start_uid: str, goal_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Find optimal learning path from start to goal using graph traversal."""
        ...

    async def get_next_adaptive_step(
        self, current_step_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        """Get next path step based on adaptive intelligence."""
        ...

    async def get_recommended_path_steps(
        self, user_uid: UserUID, max_difficulty: float = 0.5, limit: int = 5
    ) -> Result[list[dict[str, Any]]]:
        """Get recommended path steps for a user based on their progress."""
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

    See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
    """

    async def create_exercise(
        self,
        user_uid: UserUID,
        name: str,
        instructions: str,
        model: str = "claude-sonnet-4-6",
        context_notes: list[str] | None = None,
        domain: Domain | None = None,
        scope: ExerciseScope = ...,
        due_date: date | None = None,
        group_uid: str | None = None,
    ) -> Result[Exercise]:
        """Create an Exercise. Returns Result[Exercise]."""
        ...

    async def get_exercise(self, uid: str) -> Result[Exercise]:
        """Get exercise by UID. Returns Result[Exercise], or not-found error."""
        ...

    async def list_user_exercises(
        self,
        user_uid: UserUID,
        active_only: bool = True,
    ) -> Result[list[Exercise]]:
        """List user's exercises. Returns Result[list[Exercise]]."""
        ...

    async def update(self, uid: str, updates: RawChanges) -> Result[Exercise]:
        """Update an exercise (generic CRUD patch + ADR-074 embedding refresh)."""
        ...

    # Curriculum linking
    async def link_to_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """Link exercise to curriculum KU via REQUIRES_KNOWLEDGE."""
        ...

    async def unlink_from_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """Remove REQUIRES_KNOWLEDGE relationship."""
        ...

    async def get_required_knowledge(
        self, exercise_uid: str
    ) -> Result[list[RequiredKnowledgeResult]]:
        """Get curriculum KUs required by an exercise."""
        ...

    async def get_exercises_for_curriculum(
        self, curriculum_uid: str
    ) -> Result[list[CurriculumExerciseResult]]:
        """Get exercises that require a specific curriculum KU."""
        ...


class RevisedExerciseBackendOperations(BackendOperations["RevisedExercise"], Protocol):
    """Backend operations for RevisedExercise — base CRUD + revision-loop methods.

    Implementation: RevisedExerciseBackend (backends/exercise_backends.py)
    Consumer: RevisedExerciseService.__init__
    """

    async def link_to_report(self, re_uid: str, report_uid: str) -> Result[bool]: ...

    async def link_to_exercise(self, re_uid: str, exercise_uid: str) -> Result[bool]: ...

    async def verify_teacher_authority(
        self,
        teacher_uid: str,
        report_uid: str,
        student_uid: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def create_owns_relationship(
        self,
        teacher_uid: str,
        re_uid: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def auto_share_with_student(
        self,
        student_uid: str,
        re_uid: str,
        shared_at: str,
    ) -> Result[list[Neo4jProperties]]: ...

    async def list_for_student(
        self,
        student_uid: str,
        teacher_uid: str | None = None,
    ) -> Result[list[Neo4jProperties]]: ...

    async def get_by_report_uid(self, report_uid: str) -> Result[list[Neo4jProperties]]: ...

    async def get_revision_chain(self, exercise_uid: str) -> Result[list[RevisionChainResult]]: ...


class RevisedExerciseOperations(Protocol):
    """Revised exercise operations for the four-phase learning loop.

    RevisedExercise is a UserOwnedEntity (teacher-owned, student-targeted)
    that provides targeted revision instructions after EntryReport.

    CRUD: Inherited from CrudOperationsMixin via BaseService (create, get, update, delete, list).
    Domain-specific: list_for_student, get_revision_chain.

    Route consumer: revised_exercises_api.py (CRUDRouteFactory + domain-specific routes)
    Implementation: RevisedExerciseService
    """

    async def create(self, entity: RevisedExercise) -> Result[RevisedExercise]:
        """Create a RevisedExercise with authority verification and relationships."""
        ...

    async def get(self, uid: str) -> Result[RevisedExercise]:
        """Get revised exercise by UID."""
        ...

    async def update(self, uid: str, updates: RawChanges) -> Result[RevisedExercise]:
        """Update a revised exercise."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """Delete a revised exercise with cascade."""
        ...

    async def list_for_student(
        self, student_uid: str, teacher_uid: str | None = None
    ) -> Result[list[RevisedExercise]]:
        """List revised exercises targeting a student.

        Args:
            student_uid: The student whose revisions to list.
            teacher_uid: If provided, scope to revisions owned by this teacher.
        """
        ...

    async def get_revision_chain(self, exercise_uid: str) -> Result[list[RevisionChainResult]]:
        """Get all revisions in the chain for an original exercise."""
        ...


# =============================================================================
# PREREQUISITE-EDGE SUGGESTIONS (Discovery Analytics PR 4)
# =============================================================================


class PrereqSuggestionBackendOperations(Protocol):
    """
    Backend contract for the prerequisite-edge suggestion read side.

    Read-only: candidate generation computes pairwise cosine in Python over
    stored Ku embeddings — this feature never writes to the graph (the only
    write is the Edge YAML file the admin approves into the content vault).

    Backend: adapters/persistence/neo4j/prereq_candidate_backend.py
    """

    async def get_kus_with_embeddings(self) -> Result[list[KuEmbeddingRow]]:
        """All Kus that have a stored entity embedding (uid, title, summary, vector)."""
        ...

    async def get_ku_ku_edges(self) -> Result[list[KuEdgeRow]]:
        """All directed Ku→Ku relationships of any type (for pair exclusion)."""
        ...

    async def get_ku_titles(self, uids: list[str]) -> Result[dict[str, str]]:
        """Titles of the given Ku uids — doubles as the approve-time existence check."""
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
# - PsGraphService (sub-service of PsService) for graph navigation
# - PsOperations protocol for type-safe access
#
# See: /docs/domains/moc.md for full architecture documentation

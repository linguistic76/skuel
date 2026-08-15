"""
Search Service Protocols
=========================

Interfaces for search, query building, and Cypher operations.

Protocol Categories:
1. DomainSearchOperations[T] - Universal search protocol for all activity domains
2. Domain-Specific Search Protocols - Extended protocols for each domain:
   - EventsSearchOperations - Events domain search
   - HabitsSearchOperations - Habits domain search
   - TasksSearchOperations - Tasks domain search
   - GoalsSearchOperations - Goals domain search
   - ChoicesSearchOperations - Choices domain search
   - PrinciplesSearchOperations - Principles domain search
3. ScopedChunkRetrievalOperations - Chunk-level (RAG) retrieval (SearchRouter's ISP slice)
4. QueryBuilderOperations - Cypher query building
5. CypherOperations - Query execution
6. SearchIndexOperations - Index management
7. Supports* capability protocols - per-call narrowing for SearchRouter dispatch

- v2.0.0: Added DomainSearchOperations[T] protocol for activity domain search services
"""

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from core.models.enums import EntityStatus, EntityType, SearchVisibility
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, Metadata, UserUID
from core.ports.base_protocols import Direction
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from datetime import date

    from core.models.choice.choice import Choice as Choice
    from core.models.event.event import Event as Event
    from core.models.goal.goal import Goal as Goal
    from core.models.habit.habit import Habit as Habit
    from core.models.principle.principle import Principle as Principle
    from core.models.search_request import SearchRequest
    from core.models.task.task import Task as Task
    from core.ports.query_types import (
        SearchEventProps,
        SearchGapRow,
        SemanticSearchChunkResult,
    )
    from core.services.user import UserContext

# Generic type variable for domain entities
T = TypeVar("T")


# =============================================================================
# DOMAIN SEARCH OPERATIONS - Per-Domain Search Services
# =============================================================================


@runtime_checkable
class DomainSearchOperations(Protocol[T]):
    """
    Standard search interface for activity domain services.

    All activity domain SearchServices (TaskSearchService, GoalSearchService,
    HabitsSearchService, EventSearchService, ChoiceSearchService, PrincipleSearchService)
    implement this protocol plus domain-specific methods.

    Architecture (November 2025):
    - Separates search concerns from CRUD (CoreService)
    - Provides consistent interface across all 6 activity domains
    - Supports UserContext-aware prioritization
    - Enables graph-based relationship queries

    Universal Methods (all domains implement):
    - search() - Text search on title/description
    - get_by_status() - Filter by EntityStatus
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_upcoming() - Entities with upcoming dates / work still to do
    - get_overdue() - Past-due entities
    - get_active() - Non-terminal entities owned by the user

    Domain-Specific Methods (examples):
    - TaskSearchService: get_tasks_for_goal(), get_curriculum_tasks()
    - GoalSearchService: get_goals_by_timeframe(), get_goals_needing_habits()
    - HabitsSearchService: get_habits_by_frequency(), get_habits_needing_attention()

    See: /docs/patterns/search_service_pattern.md for full documentation.
    """

    async def search(
        self, query: str, limit: int = 50, user_uid: UserUID | None = None
    ) -> Result[list[T]]:
        """
        Text search on title and description fields.

        Args:
            query: Search string (case-insensitive)
            limit: Maximum results to return
            user_uid: Optional user UID to scope results to owner

        Returns:
            Result containing matching entities sorted by relevance
        """
        ...

    async def list_recent_for_user(
        self,
        user_uid: UserUID,
        limit: int = 10,
        exclude: set[str] | None = None,
    ) -> Result[list[T]]:
        """
        List a user's most-recently-updated entities, with optional exclusions.

        Used by the entity-picker UI (``ui/patterns/entity_picker.py``) to populate
        the dropdown when no query has been typed yet.

        Args:
            user_uid: Owner of the entities.
            limit: Maximum entries to return.
            exclude: UIDs to filter out of the result.

        Returns:
            Result containing the user's entities sorted by ``updated_at`` desc.
        """
        ...

    async def search_for_user(
        self,
        query: str,
        user_uid: UserUID,
        limit: int = 10,
        exclude: set[str] | None = None,
    ) -> Result[list[T]]:
        """
        User-scoped title/description search with optional UID exclusions.

        Used by the entity-picker UI for live typeahead. Wraps ``search()`` with
        a non-optional ``user_uid`` and post-filters excluded UIDs.

        Args:
            query: Search string (case-insensitive).
            user_uid: Owner of the entities.
            limit: Maximum entries to return.
            exclude: UIDs to filter out of the result.

        Returns:
            Result containing matching entities sorted by ``_search_order_by`` desc.
        """
        ...

    async def get_by_status(
        self, status: EntityStatus | str, limit: int = 100, user_uid: UserUID | None = None
    ) -> Result[list[T]]:
        """
        Filter entities by EntityStatus.

        Args:
            status: Status string (e.g., "active", "completed", "paused")
            limit: Maximum results to return
            user_uid: Optional user UID to scope results to owner

        Returns:
            Result containing entities with matching status
        """
        ...

    async def get_prioritized(
        self, user_context: "UserContext", limit: int = 10
    ) -> Result[list[T]]:
        """
        Get entities prioritized for the user's current context.

        Uses UserContext to determine relevance:
        - Current goals and active tasks
        - Learning position and knowledge gaps
        - Habit streaks and momentum
        - Workload and capacity

        Args:
            user_context: User's current context (~240 fields)
            limit: Maximum results to return

        Returns:
            Result containing entities sorted by priority/relevance
        """
        ...

    async def get_by_relationship(
        self,
        related_uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
    ) -> Result[list[T]]:
        """
        Get entities connected via graph relationship.

        Args:
            related_uid: UID of the related entity
            relationship_type: Type-safe RelationshipName enum (e.g., RelationshipName.FULFILLS_GOAL)
            direction: "outgoing", "incoming", or "both" (typed as Direction literal)

        Returns:
            Result containing related entities

        Example:
            # Get goals that a task fulfills
            goals = await goal_search.get_by_relationship(
                task_uid,
                RelationshipName.FULFILLS_GOAL,
                direction="incoming"
            )
        """
        ...

    async def get_upcoming(
        self,
        days_ahead: int = 7,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[T]]:
        """
        Get entities upcoming within specified number of days.

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing upcoming entities, sorted by date
        """
        ...

    async def get_overdue(
        self,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[T]]:
        """
        Get entities past their target/due date.

        Args:
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing overdue entities, sorted by how overdue
        """
        ...

    async def get_active(
        self,
        user_uid: UserUID,
        limit: int = 100,
    ) -> Result[list[T]]:
        """
        Get active (non-terminal) entities for a user.

        Active means not in a terminal state (completed, failed, cancelled, archived).
        Domains with different liveness semantics (e.g., Habits' frequency window,
        Principles' is_active flag) may override.

        Args:
            user_uid: User UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing active entities
        """
        ...


# =============================================================================
# DOMAIN-SPECIFIC SEARCH PROTOCOLS
# =============================================================================
# Each protocol extends DomainSearchOperations with domain-specific methods.
# This completes the protocol layer - every public method has a protocol declaration.


@runtime_checkable
class EventsSearchOperations(DomainSearchOperations["Event"], Protocol):
    """
    Extended search protocol for Events domain.
    Uses Entity model with EntityType.EVENT.

    Inherits all methods from DomainSearchOperations[Entity]:
    - search(), get_by_status(), get_prioritized()
    - get_by_relationship(), get_upcoming(), get_overdue(), get_active()

    Adds event-specific methods:
    - Calendar and date range queries
    - Recurring event handling
    - Conflict detection
    - Goal/Habit integration
    """

    # --- Event-specific methods ---
    async def get_in_range(
        self,
        start_date: "date",
        end_date: "date",
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list["Event"]]:
        """Get events within a date range."""
        ...

    async def get_recurring(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list["Event"]]:
        """Get recurring events."""
        ...

    async def get_for_goal(
        self, goal_uid: str, user_uid: UserUID | None = None
    ) -> Result[list["Event"]]:
        """Get events supporting a goal."""
        ...

    async def get_conflicting(self, event_uid: str) -> Result[list["Event"]]:
        """Get events that conflict with a given event."""
        ...

    async def get_for_habit(
        self, habit_uid: str, user_uid: UserUID | None = None
    ) -> Result[list["Event"]]:
        """Get events reinforcing a habit."""
        ...

    async def get_calendar_events(
        self,
        user_uid: UserUID,
        start_date: "date | None" = None,
        end_date: "date | None" = None,
        limit: int = 100,
    ) -> Result[list["Event"]]:
        """Get events for calendar display."""
        ...


@runtime_checkable
class HabitsSearchOperations(DomainSearchOperations["Habit"], Protocol):
    """
    Extended search protocol for Habits domain.

    Inherits all methods from DomainSearchOperations[Habit]:
    - search(), get_by_status(), get_prioritized()
    - get_by_relationship(), get_upcoming(), get_overdue(), get_active()

    Adds habit-specific methods:
    - Frequency-based filtering
    - Streak and attention tracking
    - Goal support relationships
    - Category management
    """

    # --- Habit-specific methods ---
    async def enrich_with_goal_links(
        self, habits: list["Habit"], active_goal_uids: list[str] | None = None
    ) -> list["Habit"]:
        """Populate each habit's derived ``supports_goal_uid`` from its SUPPORTS_GOAL edge."""
        ...

    async def get_by_frequency(self, frequency: str, limit: int = 100) -> Result[list["Habit"]]:
        """Get habits by frequency pattern."""
        ...

    async def get_needing_attention(
        self, user_uid: UserUID, limit: int = 20
    ) -> Result[list["Habit"]]:
        """Get habits that need attention (broken streaks, missed completions)."""
        ...

    async def get_at_risk(
        self, user_uid: UserUID, days_threshold: int = 3, limit: int = 20
    ) -> Result[list["Habit"]]:
        """Get habits at risk of breaking streak."""
        ...

    async def get_user_due_today(self, user_uid: UserUID) -> Result[list["Habit"]]:
        """Get habits due today for a specific user."""
        ...

    async def get_all_due_today(self) -> Result[list["Habit"]]:
        """Get all habits due today (admin use)."""
        ...

    async def get_by_category(
        self, category: str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list["Habit"]]:
        """Get habits by category, optionally filtered by user."""
        ...

    async def list_user_categories(self, user_uid: UserUID) -> Result[list[str]]:
        """List habit categories for a specific user."""
        ...

    async def list_all_categories(self) -> Result[list[str]]:
        """List all habit categories (admin use)."""
        ...


@runtime_checkable
class TasksSearchOperations(DomainSearchOperations["Task"], Protocol):
    """
    Extended search protocol for Tasks domain.

    Inherits all methods from DomainSearchOperations[Task]:
    - search(), get_by_status(), get_prioritized()
    - get_by_relationship(), get_upcoming(), get_overdue(), get_active()

    Adds task-specific methods:
    - Goal/Habit relationship queries
    - Knowledge application tracking
    - Prerequisite and blocking detection
    - Curriculum task management
    """

    # --- Task-specific methods ---
    async def get_tasks_for_goal(self, goal_uid: str) -> Result[list["Task"]]:
        """Get tasks that fulfill a goal."""
        ...

    async def get_tasks_for_habit(self, habit_uid: str) -> Result[list["Task"]]:
        """Get tasks related to a habit."""
        ...

    async def get_tasks_applying_knowledge(self, knowledge_uid: str) -> Result[list["Task"]]:
        """Get tasks that apply a knowledge unit."""
        ...

    async def get_blocked_by_prerequisites(self, user_uid: UserUID) -> Result[list["Task"]]:
        """Get tasks blocked by unfulfilled prerequisites."""
        ...

    async def get_curriculum_tasks(self) -> Result[list["Task"]]:
        """Get tasks related to curriculum learning."""
        ...

    async def get_tasks_for_path_step(self, step_uid: str) -> Result[list["Task"]]:
        """Get tasks for a path step."""
        ...

    async def get_user_assigned_tasks(
        self, user_uid: UserUID, include_completed: bool = False, limit: int = 100
    ) -> Result[list["Task"]]:
        """Get tasks assigned to a user."""
        ...

    async def get_tasks_requiring_knowledge(
        self, knowledge_uid: str, limit: int = 20
    ) -> Result[list["Task"]]:
        """Get tasks requiring a knowledge unit."""
        ...


@runtime_checkable
class GoalsSearchOperations(DomainSearchOperations["Goal"], Protocol):
    """
    Extended search protocol for Goals domain.

    Inherits all methods from DomainSearchOperations[Entity]:
    - search(), get_by_status(), get_prioritized()
    - get_by_relationship(), get_upcoming(), get_overdue(), get_active()

    Adds goal-specific methods:
    - Category navigation
    """

    # --- Goal-specific methods ---
    async def get_by_category(
        self, category: str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list["Goal"]]:
        """Get goals by category."""
        ...

    async def list_user_categories(self, user_uid: UserUID) -> Result[list[str]]:
        """List goal categories for a specific user."""
        ...

    async def list_all_categories(self) -> Result[list[str]]:
        """List all goal categories (admin use)."""
        ...


@runtime_checkable
class ChoicesSearchOperations(DomainSearchOperations["Choice"], Protocol):
    """
    Extended search protocol for Choices domain.

    Inherits all methods from DomainSearchOperations[Entity]:
    - search(), get_by_status(), get_prioritized()
    - get_by_relationship(), get_upcoming(), get_overdue(), get_active()

    Adds choice-specific methods:
    - Pending/urgent choice filtering
    - Goal and principle alignment
    - Decision timeline tracking
    """

    # --- Choice-specific methods ---
    async def get_pending(self, user_uid: UserUID, limit: int = 100) -> Result[list["Choice"]]:
        """Get pending choices for a user."""
        ...

    async def get_needing_decision(
        self, user_uid: UserUID, deadline_days: int = 7
    ) -> Result[list["Choice"]]:
        """Get choices needing decision within deadline."""
        ...

    async def get_by_category(
        self, category: str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list["Choice"]]:
        """Get choices by category."""
        ...

    async def list_user_categories(self, user_uid: UserUID) -> Result[list[str]]:
        """List choice categories for a specific user."""
        ...

    async def list_all_categories(self) -> Result[list[str]]:
        """List all choice categories (admin use)."""
        ...


@runtime_checkable
class PrinciplesSearchOperations(DomainSearchOperations["Principle"], Protocol):
    """
    Extended search protocol for Principles domain. Uses Entity model with EntityType.PRINCIPLE.

    Inherits all methods from DomainSearchOperations[Entity]:
    - search(), get_by_status(), get_prioritized()
    - get_by_relationship(), get_upcoming(), get_overdue(), get_active()

    Adds principle-specific methods:
    - Category filtering
    - Goal/habit guidance relationships
    - Review scheduling
    """

    # --- Principle-specific methods ---
    async def get_by_category(
        self, category: str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list["Principle"]]:
        """Get principles by category."""
        ...

    async def get_for_habit(self, habit_uid: str, limit: int = 10) -> Result[list["Principle"]]:
        """Get principles relevant to a habit."""
        ...

    async def get_for_goal(self, goal_uid: str, limit: int = 10) -> Result[list["Principle"]]:
        """Get principles guiding a goal."""
        ...

    async def list_user_categories(self, user_uid: UserUID) -> Result[list[str]]:
        """List principle categories for a specific user."""
        ...

    async def list_all_categories(self) -> Result[list[str]]:
        """List all principle categories (admin use)."""
        ...

    async def get_needing_review(
        self, user_uid: UserUID | None = None, days_since_review: int = 30, limit: int = 20
    ) -> Result[list["Principle"]]:
        """Get principles needing review."""
        ...

    async def get_related_principles(
        self, principle_uid: str, limit: int = 10
    ) -> Result[list["Principle"]]:
        """Get principles related to a given principle."""
        ...


# =============================================================================
# RETRIEVAL AND CROSS-DOMAIN SEARCH
# =============================================================================


@runtime_checkable
class Retrievable(Protocol):
    """Protocol for objects that can retrieve information."""

    async def retrieve(
        self, query: str, filters: Metadata | None = None, limit: int = 10
    ) -> list[Metadata]:
        """Retrieve information based on query."""
        ...


class ScopedChunkRetrievalOperations(Protocol):
    """Chunk-level (RAG) retrieval scoped by SearchRequest facets.

    The narrow slice of SearchRouter that Askesis's ContextRetriever holds —
    grounding-passage retrieval, nothing else (ISP). Satisfied by
    ``core.orchestrator.search_router.SearchRouter``; conformance is checked
    where compose post-wires the router onto the retriever.
    """

    async def retrieve_scoped_chunks(
        self,
        request: "SearchRequest",
        *,
        chunk_types: list[str] | None = None,
        min_score: float | None = None,
        user_uid: UserUID | None = None,
    ) -> Result[list["SemanticSearchChunkResult"]]:
        """Retrieve lesson-BODY passages scoped to the request's facets."""
        ...


@runtime_checkable
class QueryBuilderOperations(Protocol):
    """Query building and optimization operations."""

    def build_query(
        self, pattern: str, filters: Metadata | None = None, return_clause: str | None = None
    ) -> str:
        """Build an optimized Cypher query."""
        ...

    def add_filters(self, base_query: str, filters: Metadata) -> str:
        """Add filters to an existing query."""
        ...

    def optimize_query(self, query: str) -> str:
        """Optimize a Cypher query for performance."""
        ...


@runtime_checkable
class CypherOperations(Protocol):
    """Cypher query execution operations."""

    async def execute_query(self, query: str, parameters: Metadata | None = None) -> list[Metadata]:
        """Execute a Cypher query with parameters."""
        ...

    async def execute_template(self, template_name: str, parameters: Metadata) -> list[Metadata]:
        """Execute a named query template."""
        ...

    def validate_query(self, query: str) -> bool:
        """Validate Cypher query syntax."""
        ...


@runtime_checkable
class SearchIndexOperations(Protocol):
    """Search index management operations."""

    async def index_entity(
        self, entity_type: EntityType, entity_id: EntityUID, data: Metadata
    ) -> bool:
        """Index an entity for search."""
        ...

    async def update_index(
        self, entity_type: EntityType, entity_id: str, data: dict[str, Any]
    ) -> bool:
        """Update an indexed entity."""
        ...

    async def remove_from_index(self, entity_type: EntityType, entity_id: str) -> bool:
        """Remove an entity from search index."""
        ...

    async def rebuild_index(self, entity_type: EntityType | None = None) -> int:
        """Rebuild search index, returns number of indexed items."""
        ...


# =============================================================================
# GRAPH-AWARE SEARCH CAPABILITY PROTOCOLS (January 2026)
# =============================================================================
# These protocols enable type-safe capability checking for advanced search
# features. Use isinstance(service, Protocol) instead of hasattr().
# See: SKUEL011 linter rule - "No hasattr() in production code"


@runtime_checkable
class SupportsTextSearch(Protocol):
    """
    Protocol for services with plain owner-scoped text search capability.

    The baseline capability SearchRouter dispatches to: facade domains carry it
    on their ``.search`` sub-service (SearchOperationsMixin), thin services
    (Exercise, UserEntry, ...) implement it directly on the service.

    Use isinstance(service, SupportsTextSearch) to narrow the heterogeneous
    domain-service union before calling search(). Note runtime_checkable
    isinstance checks attribute PRESENCE only — SearchRouter additionally
    keeps its callable() check to tell "``.search`` is the sub-service"
    apart from "``.search`` is the method".
    """

    async def search(
        self,
        query: str,
        limit: int = 50,
        user_uid: UserUID | None = None,
        # boundary: genuinely heterogeneous — the router dispatches across the
        # searchable domains by runtime enum, so the element type is the cross-domain
        # union no static T can name at the isinstance narrowing site (same
        # shape as SupportsGraphTraversalSearch / SupportsTagSearch below).
    ) -> Result[list[Any]]:
        """Text search on the domain's configured fields, owner-scoped by user_uid."""
        ...


@runtime_checkable
class SupportsGraphAwareSearch(Protocol):
    """
    Protocol for search services with graph-aware faceted search capability.

    Services implementing this protocol support enriched search results that
    include graph context (relationships, connected entities, etc.).

    Use isinstance(service, SupportsGraphAwareSearch) to check capability
    before calling graph_aware_faceted_search().

    Example:
        if isinstance(search_service, SupportsGraphAwareSearch):
            result = await search_service.graph_aware_faceted_search(request, user_uid)
    """

    async def graph_aware_faceted_search(
        self,
        request: "SearchRequest",
        user_uid: UserUID | None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Faceted search with graph enrichment.

        Args:
            request: SearchRequest with query and filters
            user_uid: User performing the search. None is valid only for
                PUBLIC-visibility domains (anonymous catalog browse) — the
                implementation fails closed for OWNER_ONLY domains.

        Returns:
            Result containing list of enriched search results with _graph_context
        """
        ...

    @property
    def search_visibility(self) -> SearchVisibility:
        """The domain's declared visibility (drives the anonymous-access gate)."""
        ...


@runtime_checkable
class SupportsGraphTraversalSearch(Protocol):
    """
    Protocol for search services supporting relationship traversal search.

    Enables searching for entities connected to a specific entity via
    a relationship type (e.g., "find KUs that ENABLE content I've mastered").

    Use isinstance(service, SupportsGraphTraversalSearch) to check capability.
    """

    async def search_connected_to(
        self,
        query: str,
        related_uid: str,
        relationship_type: RelationshipName,
        direction: Direction,
        limit: int,
        user_uid: UserUID | None = None,
    ) -> Result[list[Any]]:
        """
        Search entities connected via relationship.

        Args:
            query: Text search query
            related_uid: UID of entity to find connections from
            relationship_type: Type of relationship to traverse
            direction: Relationship direction ("outgoing", "incoming", "both")
            limit: Maximum results
            user_uid: Requesting user — scoped per the domain's search_visibility

        Returns:
            Result containing list of connected entities matching query
        """
        ...


@runtime_checkable
class SupportsTagSearch(Protocol):
    """
    Protocol for search services supporting array/tag search.

    Enables searching entities by tags or array field values with
    AND/OR semantics.

    Use isinstance(service, SupportsTagSearch) to check capability.
    """

    async def search_by_tags(
        self,
        tags: list[str],
        match_all: bool,
        limit: int,
        user_uid: UserUID | None = None,
    ) -> Result[list[Any]]:
        """
        Search entities by tags.

        Args:
            tags: List of tags to search for
            match_all: True for AND semantics, False for OR
            limit: Maximum results
            user_uid: Requesting user — scoped per the domain's search_visibility

        Returns:
            Result containing list of entities with matching tags
        """
        ...


# =============================================================================
# SEARCH EVENT LOGGING (Discovery Analytics)
# =============================================================================
# :SearchEvent is a plain infrastructure node (like :ContentChunk/:AuthEvent),
# NOT an EntityType. The recorder writes one node per search.executed event;
# the gap reader aggregates them (read-only) for content-gap analysis.
# See: /docs/roadmap/DISCOVERY_ANALYTICS_ROADMAP.md


class SearchEventBackendOperations(Protocol):
    """
    Backend contract for :SearchEvent persistence and aggregation.

    Backend: adapters/persistence/neo4j/search_event_backend.py
    """

    async def record_search_event(self, props: "SearchEventProps") -> Result[None]:
        """Persist one :SearchEvent node from a search.executed event's properties."""
        ...

    async def get_search_gaps(
        self,
        *,
        max_result_count: int = 2,
        days: int = 90,
        limit: int = 50,
    ) -> Result[list["SearchGapRow"]]:
        """
        Aggregate low/zero-result searches — the content-authoring gap queue.

        Groups by normalized query text; returns per-query search counts,
        zero-result counts, average result count, last-seen timestamp, and
        the entry points that produced them.
        """
        ...

    async def count_search_events(self) -> Result[int]:
        """Total :SearchEvent count — the 1000+ trigger for deferred analytics phases."""
        ...

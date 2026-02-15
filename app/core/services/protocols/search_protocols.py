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
3. SearchOperations - Cross-domain unified search
4. QueryBuilderOperations - Cypher query building
5. CypherOperations - Query execution
6. SearchIndexOperations - Index management

Version: 2.2.0
Date: 2025-11-29
Changes:
- v2.2.0: Added domain-specific search protocols (EventsSearchOperations, etc.)
          completing the protocol layer per MyPy analysis
- v2.1.0: Added search_filtered() method with BaseSearchFilters type
- v2.0.0: Added DomainSearchOperations[T] protocol for activity domain search services
"""

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, Metadata
from core.services.protocols.base_protocols import Direction
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from datetime import date

    from core.models.enums import Domain
    from core.models.ku.ku import Ku
    from core.models.ku.ku import Ku as Habit
    from core.models.ku.ku import Ku as Task
    from core.models.search.filters import BaseSearchFilters
    from core.models.search.query_parser import ParsedSearchQuery
    from core.models.search_request import SearchRequest
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
    HabitSearchService, EventSearchService, ChoiceSearchService, PrincipleSearchService)
    implement this protocol plus domain-specific methods.

    Architecture (November 2025):
    - Separates search concerns from CRUD (CoreService)
    - Provides consistent interface across all 6 activity domains
    - Supports UserContext-aware prioritization
    - Enables graph-based relationship queries

    Universal Methods (all domains implement):
    - search() - Text search on title/description
    - search_filtered() - Type-safe filtered search (NEW v2.1.0)
    - intelligent_search() - Natural language search with semantic filter extraction (NEW v2.1.0)
    - get_by_status() - Filter by KuStatus
    - get_by_domain() - Filter by Domain enum
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_due_soon() - Time-based filtering
    - get_overdue() - Past-due items

    Domain-Specific Methods (examples):
    - TaskSearchService: get_tasks_for_goal(), get_curriculum_tasks()
    - GoalSearchService: get_goals_by_timeframe(), get_goals_needing_habits()
    - HabitSearchService: get_habits_by_frequency(), get_habits_needing_attention()

    See: /docs/patterns/search_service_pattern.md for full documentation.
    """

    async def search(self, query: str, limit: int = 50) -> Result[list[T]]:
        """
        Text search on title and description fields.

        Args:
            query: Search string (case-insensitive)
            limit: Maximum results to return

        Returns:
            Result containing matching entities sorted by relevance
        """
        ...

    async def search_filtered(self, filters: "BaseSearchFilters") -> Result[list[T]]:
        """
        Type-safe filtered search using domain-specific filter dataclass.

        Accepts a BaseSearchFilters (or domain-specific subclass) with type-safe
        filter fields. This is the preferred method for complex queries as it
        provides compile-time verification of filter parameters.

        Args:
            filters: BaseSearchFilters or domain-specific subclass
                     (TaskSearchFilters, GoalSearchFilters, etc.)

        Returns:
            Result containing entities matching all specified filters

        Example:
            from dataclasses import dataclass
            from core.models.search import BaseSearchFilters
            from core.models.enums import KuStatus, Domain

            # Define domain-specific filters locally (see MocSearchFilters pattern)
            @dataclass(frozen=True)
            class MocSearchFilters(BaseSearchFilters):
                is_template: bool | None = None
                visibility: str | None = None

            # Create type-safe filters
            filters = MocSearchFilters(
                query="python tutorial",
                domain=Domain.TECH,
                is_template=False,
                limit=20
            )

            # Execute filtered search
            result = await moc_search.search_filtered(filters)

        Note:
            For most searches, use SearchRequest (Pydantic model) via SearchRouter.
            search_filtered() is for domain-specific internal searches that need
            type-safe frozen filter objects.

        See Also:
            - core.models.search_request.SearchRequest - THE canonical search model
            - core.models.search.filters.BaseSearchFilters - Base for local filters
        """
        ...

    async def intelligent_search(
        self, query: str, limit: int = 50
    ) -> Result[tuple[list[T], "ParsedSearchQuery"]]:
        """
        Natural language search with automatic semantic filter extraction.

        Parses the query to extract semantic meaning using enum synonyms:
        - Priority: "urgent", "asap", "critical" → Priority.CRITICAL
        - Status: "completed", "in progress", "active" → KuStatus values
        - Domain: "health", "tech", "business" → Domain values

        This is the user-friendly search method that bridges natural language
        to type-safe filtering.

        Args:
            query: Natural language search query (e.g., "urgent health tasks")
            limit: Maximum results to return

        Returns:
            Result containing tuple of:
            - list[T]: Matching entities (filtered and text-searched)
            - ParsedSearchQuery: The extracted filters for transparency

        Example:
            # User types: "show me urgent tasks in progress"
            result = await task_search.intelligent_search("show me urgent tasks in progress")

            if result.is_ok:
                entities, parsed = result.value
                # entities: Tasks matching Priority.CRITICAL/HIGH + KuStatus.ACTIVE
                # parsed.priorities: (Priority.CRITICAL, Priority.HIGH)
                # parsed.statuses: (KuStatus.ACTIVE,)
                # parsed.text_query: "tasks"  (cleaned for text search)

        Implementation Notes:
            1. Use SearchQueryParser.parse() to extract semantic filters
            2. Apply extracted priority/status/domain filters
            3. Run text search on cleaned query
            4. Return both results and parsed query for UI transparency

        See Also:
            - core.models.search.query_parser.SearchQueryParser
            - core.models.search.query_parser.ParsedSearchQuery
        """
        ...

    async def get_by_status(self, status: str, limit: int = 100) -> Result[list[T]]:
        """
        Filter entities by KuStatus.

        Args:
            status: Status string (e.g., "active", "completed", "paused")
            limit: Maximum results to return

        Returns:
            Result containing entities with matching status
        """
        ...

    async def get_by_domain(self, domain: "Domain", limit: int = 100) -> Result[list[T]]:
        """
        Filter entities by Domain enum.

        Args:
            domain: Domain enum value (TECH, HEALTH, PERSONAL, etc.)
            limit: Maximum results to return

        Returns:
            Result containing entities in specified domain
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

    async def get_due_soon(
        self,
        days_ahead: int = 7,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[T]]:
        """
        Get entities due within specified number of days.

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing entities due soon, sorted by due date
        """
        ...

    async def get_overdue(
        self,
        user_uid: str | None = None,
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


# =============================================================================
# DOMAIN-SPECIFIC SEARCH PROTOCOLS
# =============================================================================
# Each protocol extends DomainSearchOperations with domain-specific methods.
# This completes the protocol layer - every public method has a protocol declaration.


@runtime_checkable
class EventsSearchOperations(DomainSearchOperations["Ku"], Protocol):
    """
    Extended search protocol for Events domain.
    Uses unified Ku model with KuType.EVENT.

    Inherits all methods from DomainSearchOperations[Ku]:
    - search(), search_filtered(), intelligent_search()
    - get_by_status(), get_by_domain(), get_prioritized()
    - get_by_relationship(), get_due_soon(), get_overdue()

    Adds event-specific methods:
    - Calendar and date range queries
    - Recurring event handling
    - Conflict detection
    - Goal/Habit integration
    """

    # --- Event-specific methods ---
    async def get_in_range(
        self, start_date: "date", end_date: "date", user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get events within a date range."""
        ...

    async def get_recurring(
        self, user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get recurring events."""
        ...

    async def get_for_goal(self, goal_uid: str, user_uid: str | None = None) -> Result[list["Ku"]]:
        """Get events supporting a goal."""
        ...

    async def get_conflicting(self, event_uid: str) -> Result[list["Ku"]]:
        """Get events that conflict with a given event."""
        ...

    async def get_by_type(
        self, event_type: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get events by event type."""
        ...

    async def get_upcoming(
        self, user_uid: str, days_ahead: int = 30, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get upcoming events for a user."""
        ...

    async def get_history(
        self, user_uid: str, days_back: int = 90, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get completed/past events for a user."""
        ...

    async def get_for_habit(
        self, habit_uid: str, user_uid: str | None = None
    ) -> Result[list["Ku"]]:
        """Get events reinforcing a habit."""
        ...

    async def get_calendar_events(
        self,
        user_uid: str,
        start_date: "date | None" = None,
        end_date: "date | None" = None,
        limit: int = 100,
    ) -> Result[list["Ku"]]:
        """Get events for calendar display."""
        ...


@runtime_checkable
class HabitsSearchOperations(DomainSearchOperations["Habit"], Protocol):
    """
    Extended search protocol for Habits domain.

    Inherits all methods from DomainSearchOperations[Habit]:
    - search(), search_filtered(), intelligent_search()
    - get_by_status(), get_by_domain(), get_prioritized()
    - get_by_relationship(), get_due_soon(), get_overdue()

    Adds habit-specific methods:
    - Frequency-based filtering
    - Streak and attention tracking
    - Goal support relationships
    - Category management
    """

    # --- Habit-specific methods ---
    async def get_by_frequency(
        self, frequency: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Habit"]]:
        """Get habits by frequency pattern."""
        ...

    async def get_needing_attention(self, user_uid: str, limit: int = 20) -> Result[list["Habit"]]:
        """Get habits that need attention (broken streaks, missed completions)."""
        ...

    async def get_supporting_goal(self, goal_uid: str) -> Result[list["Habit"]]:
        """Get habits supporting a goal."""
        ...

    async def get_at_risk(
        self, user_uid: str, days_threshold: int = 3, limit: int = 20
    ) -> Result[list["Habit"]]:
        """Get habits at risk of breaking streak."""
        ...

    async def get_user_due_today(self, user_uid: str) -> Result[list["Habit"]]:
        """Get habits due today for a specific user."""
        ...

    async def get_all_due_today(self) -> Result[list["Habit"]]:
        """Get all habits due today (admin use)."""
        ...

    async def get_by_category(self, category: str, limit: int = 100) -> Result[list["Habit"]]:
        """Get habits by category."""
        ...

    async def list_user_categories(self, user_uid: str) -> Result[list[str]]:
        """List habit categories for a specific user."""
        ...

    async def list_all_categories(self) -> Result[list[str]]:
        """List all habit categories (admin use)."""
        ...

    async def get_reinforcing_knowledge(
        self, knowledge_uid: str, limit: int = 20
    ) -> Result[list["Habit"]]:
        """Get habits that reinforce a knowledge unit."""
        ...

    async def get_active_habits(self, user_uid: str) -> Result[list["Habit"]]:
        """Get all active habits for a user."""
        ...


@runtime_checkable
class TasksSearchOperations(DomainSearchOperations["Task"], Protocol):
    """
    Extended search protocol for Tasks domain.

    Inherits all methods from DomainSearchOperations[Task]:
    - search(), search_filtered(), intelligent_search()
    - get_by_status(), get_by_domain(), get_prioritized()
    - get_by_relationship(), get_due_soon(), get_overdue()

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

    async def get_blocked_by_prerequisites(self, user_uid: str) -> Result[list["Task"]]:
        """Get tasks blocked by unfulfilled prerequisites."""
        ...

    async def get_prioritized_tasks(
        self, user_context: "UserContext", limit: int = 10
    ) -> Result[list["Task"]]:
        """Get tasks prioritized for user context (alias for get_prioritized)."""
        ...

    async def get_learning_relevant_tasks(
        self, user_uid: str, learning_path_uid: str | None = None, limit: int = 20
    ) -> Result[list["Task"]]:
        """Get tasks relevant to current learning."""
        ...

    async def get_curriculum_tasks(self) -> Result[list["Task"]]:
        """Get tasks related to curriculum learning."""
        ...

    async def get_tasks_for_learning_step(self, step_uid: str) -> Result[list["Task"]]:
        """Get tasks for a learning step."""
        ...

    async def get_user_assigned_tasks(
        self, user_uid: str, include_completed: bool = False, limit: int = 100
    ) -> Result[list["Task"]]:
        """Get tasks assigned to a user."""
        ...

    async def get_tasks_requiring_knowledge(
        self, knowledge_uid: str, limit: int = 20
    ) -> Result[list["Task"]]:
        """Get tasks requiring a knowledge unit."""
        ...


@runtime_checkable
class GoalsSearchOperations(DomainSearchOperations["Ku"], Protocol):
    """
    Extended search protocol for Goals domain.

    Inherits all methods from DomainSearchOperations[Ku]:
    - search(), search_filtered(), intelligent_search()
    - get_by_status(), get_by_domain(), get_prioritized()
    - get_by_relationship(), get_due_soon(), get_overdue()

    Adds goal-specific methods:
    - Timeframe-based filtering
    - Habit and knowledge gap analysis
    - Category and hierarchy navigation
    """

    # --- Goal-specific methods ---
    async def get_by_timeframe(
        self, timeframe: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get goals by timeframe (daily, weekly, monthly, yearly)."""
        ...

    async def get_by_category(self, category: str, limit: int = 100) -> Result[list["Ku"]]:
        """Get goals by category."""
        ...

    async def get_needing_habits(self, user_uid: str, limit: int = 20) -> Result[list["Ku"]]:
        """Get goals that need supporting habits."""
        ...

    async def get_blocked_by_knowledge(self, user_uid: str, limit: int = 20) -> Result[list["Ku"]]:
        """Get goals blocked by missing knowledge."""
        ...

    async def list_user_categories(self, user_uid: str) -> Result[list[str]]:
        """List goal categories for a specific user."""
        ...

    async def list_all_categories(self) -> Result[list[str]]:
        """List all goal categories (admin use)."""
        ...

    async def get_goals_for_task(self, task_uid: str) -> Result[list["Ku"]]:
        """Get goals that a task fulfills."""
        ...

    async def get_goals_for_habit(self, habit_uid: str) -> Result[list["Ku"]]:
        """Get goals that a habit supports."""
        ...

    async def get_sub_goals(self, parent_goal_uid: str) -> Result[list["Ku"]]:
        """Get sub-goals of a parent goal."""
        ...

    async def get_related_goals(self, goal_uid: str, limit: int = 10) -> Result[list["Ku"]]:
        """Get goals related to a given goal."""
        ...


@runtime_checkable
class ChoicesSearchOperations(DomainSearchOperations["Ku"], Protocol):
    """
    Extended search protocol for Choices domain.

    Inherits all methods from DomainSearchOperations[Choice]:
    - search(), search_filtered(), intelligent_search()
    - get_by_status(), get_by_domain(), get_prioritized()
    - get_by_relationship(), get_due_soon(), get_overdue()

    Adds choice-specific methods:
    - Pending/urgent choice filtering
    - Goal and principle alignment
    - Decision timeline tracking
    """

    # --- Choice-specific methods ---
    async def get_pending(self, user_uid: str, limit: int = 100) -> Result[list["Ku"]]:
        """Get pending choices for a user."""
        ...

    async def get_by_urgency(
        self, urgency: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get choices by urgency level."""
        ...

    async def get_affecting_goal(self, goal_uid: str) -> Result[list["Ku"]]:
        """Get choices that affect a goal."""
        ...

    async def get_needing_decision(
        self, user_uid: str, deadline_days: int = 7
    ) -> Result[list["Ku"]]:
        """Get choices needing decision within deadline."""
        ...

    async def get_aligned_with_principle(
        self, principle_uid: str, limit: int = 20
    ) -> Result[list["Ku"]]:
        """Get choices aligned with a principle."""
        ...

    async def get_by_category(
        self, category: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get choices by category."""
        ...

    async def list_user_categories(self, user_uid: str) -> Result[list[str]]:
        """List choice categories for a specific user."""
        ...

    async def list_all_categories(self) -> Result[list[str]]:
        """List all choice categories (admin use)."""
        ...

    async def get_decided(
        self, user_uid: str, days_back: int = 30, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get recently decided choices."""
        ...


@runtime_checkable
class PrinciplesSearchOperations(DomainSearchOperations["Ku"], Protocol):
    """
    Extended search protocol for Principles domain. Uses unified Ku model with KuType.PRINCIPLE.

    Inherits all methods from DomainSearchOperations[Ku]:
    - search(), search_filtered(), intelligent_search()
    - get_by_status(), get_by_domain(), get_prioritized()
    - get_by_relationship(), get_due_soon(), get_overdue()

    Adds principle-specific methods:
    - Strength and category filtering
    - Goal/choice guidance relationships
    - Review scheduling
    """

    # --- Principle-specific methods ---
    async def get_by_strength(
        self, strength: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get principles by strength level."""
        ...

    async def get_by_category(
        self, category: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list["Ku"]]:
        """Get principles by category."""
        ...

    async def get_guiding_goals(self, principle_uid: str) -> Result[list[str]]:
        """Get goal UIDs guided by a principle."""
        ...

    async def get_inspiring_habits(self, principle_uid: str) -> Result[list[str]]:
        """Get habit UIDs inspired by a principle."""
        ...

    async def get_for_choice(self, choice_uid: str, limit: int = 10) -> Result[list["Ku"]]:
        """Get principles relevant to a choice."""
        ...

    async def get_for_goal(self, goal_uid: str, limit: int = 10) -> Result[list["Ku"]]:
        """Get principles guiding a goal."""
        ...

    async def get_active_principles(self, user_uid: str, limit: int = 100) -> Result[list["Ku"]]:
        """Get active principles for a user."""
        ...

    async def list_user_categories(self, user_uid: str) -> Result[list[str]]:
        """List principle categories for a specific user."""
        ...

    async def list_all_categories(self) -> Result[list[str]]:
        """List all principle categories (admin use)."""
        ...

    async def get_needing_review(
        self, user_uid: str, days_since_review: int = 30, limit: int = 20
    ) -> Result[list["Ku"]]:
        """Get principles needing review."""
        ...

    async def get_related_principles(
        self, principle_uid: str, limit: int = 10
    ) -> Result[list["Ku"]]:
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


@runtime_checkable
class SearchOperations(Protocol):
    """Core search operations."""

    async def search(
        self,
        query: str,
        domain: str | None = None,
        filters: Metadata | None = None,
        limit: int = 25,
    ) -> list[Metadata]:
        """Perform a search with optional domain and filters."""
        ...

    async def search_by_domain(self, query: str, domain: str, limit: int = 25) -> list[Metadata]:
        """Search within a specific domain."""
        ...

    async def unified_search(self, query: str) -> dict[str, list[Metadata]]:
        """Search across all domains, returns results grouped by domain."""
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

    async def index_entity(self, entity_type: str, entity_id: EntityUID, data: Metadata) -> bool:
        """Index an entity for search."""
        ...

    async def update_index(self, entity_type: str, entity_id: str, data: dict[str, Any]) -> bool:
        """Update an indexed entity."""
        ...

    async def remove_from_index(self, entity_type: str, entity_id: str) -> bool:
        """Remove an entity from search index."""
        ...

    async def rebuild_index(self, entity_type: str | None = None) -> int:
        """Rebuild search index, returns number of indexed items."""
        ...


# =============================================================================
# GRAPH-AWARE SEARCH CAPABILITY PROTOCOLS (January 2026)
# =============================================================================
# These protocols enable type-safe capability checking for advanced search
# features. Use isinstance(service, Protocol) instead of hasattr().
# See: SKUEL011 linter rule - "No hasattr() in production code"


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
        user_uid: str,
    ) -> Result[list[dict[str, Any]]]:
        """
        Faceted search with graph enrichment.

        Args:
            request: SearchRequest with query and filters
            user_uid: User performing the search

        Returns:
            Result containing list of enriched search results with _graph_context
        """
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
    ) -> Result[list[Any]]:
        """
        Search entities connected via relationship.

        Args:
            query: Text search query
            related_uid: UID of entity to find connections from
            relationship_type: Type of relationship to traverse
            direction: Relationship direction ("outgoing", "incoming", "both")
            limit: Maximum results

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
    ) -> Result[list[Any]]:
        """
        Search entities by tags.

        Args:
            tags: List of tags to search for
            match_all: True for AND semantics, False for OR
            limit: Maximum results

        Returns:
            Result containing list of entities with matching tags
        """
        ...

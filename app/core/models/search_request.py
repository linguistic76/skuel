"""
Clean Search API Models - THE Canonical Search Request
========================================================

*Last updated: 2026-01-04*

THE single search request model for SKUEL (One Path Forward).

Core Principle: "Search by domain, filter by facets"

This module provides:
- SearchRequest: THE canonical Pydantic request model combining:
  - Faceted search (domain, status, priority, etc.)
  - Graph-aware search (relationship patterns)
  - Cross-domain search (entity types)
  - Array search (tags)
- SearchResponse: Structured response with results and facet counts
- FacetCount: UI-ready facet counts for UI filters

Usage Example:
    ```python
    # Simple text search across all domains
    request = SearchRequest(query_text="self-awareness")

    # Search with domain filter
    request = SearchRequest(query_text="meditation", domain=Domain.KNOWLEDGE)

    # Faceted search with multiple filters
    request = SearchRequest(
        query_text="practice exercises",
        domain=Domain.KNOWLEDGE,
        sel_category=SELCategory.SELF_AWARENESS,
        learning_level=LearningLevel.BEGINNER,
    )

    # Cross-domain search with entity types (unified search)
    request = SearchRequest(
        query_text="machine learning",
        entity_types=[EntityType.PATH_STEP, EntityType.TASK],
        tags_contain=["python", "ml"],
        tags_match_all=False,
    )

    # Graph-aware search with relationship filter
    request = SearchRequest(
        query_text="python",
        connected_to_uid="ku.python-basics",
        connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
    )
    ```

One Path Forward (January 2026):
    SearchRequest is THE canonical request model. UnifiedSearchRequest was
    merged into this model. All search paths use SearchRequest:
    - UI routes → SearchRouter.search()
    - API routes → SearchRouter.advanced_search()
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models.enums import (
    ContentType,
    Domain,
    EducationalLevel,
    EntityStatus,
    LearningLevel,
    Priority,
    SELCategory,
)
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.relationship_filters import RelationshipFilters
from core.models.search.filter_enums import SearchSortOrder
from core.models.type_hints import UserUID
from core.ports.query_types import CapacityWarnings
from core.utils.logging import get_logger

logger = get_logger("skuel.models.search_request")

_StrEnumT = TypeVar("_StrEnumT", bound=StrEnum)


def _facet_enum_or_none(enum_cls: type[_StrEnumT], value: str | None) -> _StrEnumT | None:
    """Coerce a raw facet string to an enum member, or None if unrecognized.

    Facet values arrive from the client and can be stale — a service-worker- or
    bfcache-cached older page after a deploy, a hand-edited URL, a replayed
    request. A garbage value must degrade to "no filter", never abort the whole
    search: dropping one unknown facet is the graceful path and matches
    filter-only faceted search (a filter alone is a valid search).
    """
    if not value:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        logger.warning("Ignoring unrecognized %s search facet value: %r", enum_cls.__name__, value)
        return None


# ============================================================================
# FACET MODELS
# ============================================================================


class FacetCount(BaseModel):
    """
    Count of results per facet value - for UI filter badges.

    Used by the UI to show how many results exist for each filter option.
    """

    facet_type: str = Field(..., description="Type of facet (sel_category, learning_level, etc.)")
    facet_value: str = Field(..., description="Value of facet (self_awareness, beginner, etc.)")
    count: int = Field(..., ge=0, description="Number of results with this facet")
    display_name: str | None = Field(default=None, description="Human-readable display name")
    icon: str | None = Field(default=None, description="Emoji icon for this facet")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# SEARCH REQUEST
# ============================================================================


class SearchRequest(BaseModel):
    """
    Clean, simple search request - the foundation of SKUEL search.

    Core facets are first-class fields, not buried in dictionaries.
    All facets map directly to Neo4j properties via dynamic queries.

    Examples:
        # Text search only
        SearchRequest(query_text="meditation")

        # Filter-only search (no text)
        SearchRequest(domain=Domain.TASKS, priority=Priority.HIGH)

        # Hybrid search (text + filters)
        SearchRequest(query_text="meditation", domain=Domain.HABITS)
    """

    # Search query (OPTIONAL - can do filter-only search)
    query_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="Search query text (optional if filters provided)",
    )

    # ========================================================================
    # CORE FACETS (First-class filters - fundamental to SKUEL)
    # ========================================================================

    # Domain filter - which entity type to search
    domain: Domain | None = Field(
        default=None,
        description="Domain to search: knowledge (ku), tasks, events, habits, goals, choices, principles",
    )

    # SEL Category - for knowledge units
    sel_category: SELCategory | None = Field(
        default=None,
        description="SEL category: self_awareness, self_management, social_awareness, relationship_skills, responsible_decision_making",
    )

    # Learning level - for content difficulty
    learning_level: LearningLevel | None = Field(
        default=None, description="Learning level: beginner, intermediate, advanced, expert"
    )

    # Content type - for knowledge units
    content_type: ContentType | None = Field(
        default=None,
        description="Content type: concept, practice, example, exercise, assessment, resource, summary",
    )

    # Educational level - age-appropriate filtering
    educational_level: EducationalLevel | None = Field(
        default=None,
        description="Educational level: elementary, middle_school, high_school, college, professional, lifelong",
    )

    # ========================================================================
    # DOMAIN-SPECIFIC FACETS (Common across multiple domains)
    # ========================================================================

    # Status filter - for tasks, events, habits, goals
    status: EntityStatus | None = Field(
        default=None,
        description="Activity status: draft, scheduled, in_progress, completed, cancelled, etc.",
    )

    # Priority filter - for tasks, events
    priority: Priority | None = Field(
        default=None, description="Priority level: low, medium, high, critical"
    )

    # ========================================================================
    # RELATIONSHIP-BASED FACETS (Graph-aware filters)
    # ========================================================================

    # Ready to learn - prerequisites are met
    ready_to_learn: bool = Field(
        default=False,
        description="Filter by prerequisites met (graph pattern: all required knowledge mastered)",
    )

    # Builds on mastered knowledge
    builds_on_mastered: bool = Field(
        default=False,
        description="Show knowledge connected to mastered units (graph pattern: related to mastered knowledge)",
    )

    # In active learning path
    in_active_path: bool = Field(
        default=False,
        description="Filter by active learning path membership (graph pattern: part of followed learning path)",
    )

    # Supports active goals
    supports_goals: bool = Field(
        default=False,
        description="Show knowledge supporting active goals (graph pattern: connected to active goals)",
    )

    # Builds on active habits
    builds_on_habits: bool = Field(
        default=False,
        description="Show knowledge connected to active habits (graph pattern: reinforces practicing habits)",
    )

    # Applied in recent tasks
    applied_in_tasks: bool = Field(
        default=False,
        description="Show knowledge used in recent tasks (graph pattern: applied in completed/active tasks)",
    )

    # Recommended by principles
    aligned_with_principles: bool = Field(
        default=False,
        description="Show knowledge aligned with core principles (graph pattern: supports adopted principles)",
    )

    # Next logical step
    next_logical_step: bool = Field(
        default=False,
        description="Show natural progression from mastered knowledge (graph pattern: enabled by mastered units)",
    )

    # ========================================================================
    # NOUS-SPECIFIC FACETS (For worldview content)
    # ========================================================================

    # NOUS topic filter — matches membership in the `nous` array property on
    # Ku/PathStep (the 11 official topic sections; vocabulary derived from the
    # graph, anchors guarantee completeness)
    nous: str | None = Field(
        default=None,
        description="Filter by NOUS topic slug (stories, environment, intelligence, investment, words, relationships, social, body, exercises, self-management, self-awareness)",
    )

    # NOUS sub-topic filter — the 2nd taxonomy level beneath `nous` (e.g.
    # nervous-system under body). Matches membership in the `nous_subtopic`
    # array property on Ku/PathStep. The /search dropdown only offers
    # sub-topics that CO-OCCUR with the chosen nous topic on ≥1 entity
    # (SearchRouter.nous_subtopic_map — the dropdown follows the content), so
    # every offered combination has at least one match; the filter itself is
    # the same independent array membership.
    nous_subtopic: str | None = Field(
        default=None,
        description="Filter by NOUS sub-topic slug (2nd level, e.g. nervous-system, sleep, education)",
    )

    # Content source filter
    source: str | None = Field(
        default=None,
        description="Content source: nous, obsidian, manual, ingested",
    )

    # ========================================================================
    # PEDAGOGICAL FILTERS (Learning progress tracking)
    # ========================================================================

    # Not yet viewed - show only unseen content
    not_yet_viewed: bool = Field(
        default=False,
        description="Show only content the user hasn't viewed yet (graph pattern: no VIEWED relationship)",
    )

    # Viewed but not mastered - in-progress content
    viewed_not_mastered: bool = Field(
        default=False,
        description="Show content viewed but not yet mastered (graph pattern: VIEWED or IN_PROGRESS but not MASTERED)",
    )

    # Ready for review - spaced repetition
    ready_to_review: bool = Field(
        default=False,
        description="Show mastered content due for review (graph pattern: MASTERED with decay)",
    )

    # ========================================================================
    # SEMANTIC SEARCH ENHANCEMENT
    # ========================================================================

    # Enable semantic relationship boosting
    enable_semantic_boost: bool = Field(
        default=False,
        description="Enable semantic relationship boosting (requires context_uids)",
    )

    # Context for semantic boosting
    context_uids: list[str] | None = Field(
        default=None,
        description="UIDs representing user's current context for semantic boosting (e.g., current learning path, active tasks)",
    )

    # Enable learning-aware personalization
    enable_learning_aware: bool = Field(
        default=False,
        description="Enable learning state boosting (personalizes results based on user progress)",
    )

    # Learning preference mode
    prefer_unmastered: bool = Field(
        default=True,
        description="True = prioritize unlearned content, False = prioritize mastered content (review mode)",
    )

    # ========================================================================
    # EXTENDED FACETS (Domain-specific, rarely used)
    # ========================================================================

    extended_facets: dict[str, Any] | None = Field(
        default=None,
        description="Extended domain-specific filters (e.g., habit frequency, goal deadline)",
    )

    # ========================================================================
    # CROSS-DOMAIN SEARCH (EntityType dispatch)
    # ========================================================================

    entity_types: list[EntityType | NonKuDomain] = Field(
        default_factory=list,
        description="Target entity types for cross-domain search (empty = use domain field)",
    )

    # ========================================================================
    # GRAPH TRAVERSAL FILTER (Relationship-based)
    # ========================================================================

    connected_to_uid: str | None = Field(
        default=None,
        description="UID of entity to filter by relationship (e.g., 'ku.python-basics')",
    )

    connected_relationship: Any | None = Field(
        default=None,
        description="RelationshipName for connected_to filter (e.g., ENABLES, REQUIRES_KNOWLEDGE)",
    )

    connected_direction: Literal["outgoing", "incoming", "both"] = Field(
        default="outgoing",
        description="Relationship direction: 'outgoing', 'incoming', or 'both'",
    )

    # ========================================================================
    # ARRAY/TAG SEARCH
    # ========================================================================

    tags_contain: list[str] | None = Field(
        default=None,
        description="Filter by tags containing these values",
    )

    tags_match_all: bool = Field(
        default=False,
        description="True = AND semantics (all tags must match), False = OR semantics (any tag matches)",
    )

    # ========================================================================
    # SORT, PAGINATION & OPTIONS
    # ========================================================================

    # Result ordering. Every SearchSortOrder member is honored end-to-end in
    # the faceted path (ORDER BY in faceted_search_raw); RELEVANCE falls back
    # to the domain's configured `search_order_by` DESC.
    sort_order: SearchSortOrder = Field(
        default=SearchSortOrder.RELEVANCE,
        description="Result ordering (relevance, created_desc, created_asc, updated_desc, title_asc)",
    )

    # Ceiling accommodates the multi-domain sweep's over-fetch pagination
    # (limit=offset+limit per domain) and the library browse page depth.
    limit: int = Field(default=20, ge=1, le=200, description="Maximum results to return")

    offset: int = Field(default=0, ge=0, description="Pagination offset")

    include_facet_counts: bool = Field(
        default=True, description="Include facet counts for UI filters"
    )

    user_uid: UserUID | None = Field(
        default=None, description="User ID for personalized results (optional)"
    )

    @field_validator("query_text")
    @classmethod
    def validate_query_text(cls, v) -> Any:
        """Ensure query text is not empty when provided.

        A ``None`` query is valid — filter-only search is a first-class mode
        (see ``has_any_criteria``). Only an all-whitespace string is rejected,
        because that is a malformed query rather than a deliberate omission.
        """
        if v is not None and not v.strip():
            raise ValueError("Query text cannot be empty or whitespace")
        return v.strip() if v else None

    def to_property_filters(self) -> dict[str, Any]:
        """
        Convert facets to property filters.

        Used by UniversalNeo4jBackend.find_by() for dynamic queries.
        All facets become WHERE clauses in Cypher.
        """
        filters: dict[str, str] = {}

        # Core facets (handle both enum and string values from Pydantic)
        if self.sel_category:
            filters["sel_category"] = (
                self.sel_category if isinstance(self.sel_category, str) else self.sel_category.value
            )
        if self.learning_level:
            filters["learning_level"] = (
                self.learning_level
                if isinstance(self.learning_level, str)
                else self.learning_level.value
            )
        if self.content_type:
            filters["content_type"] = (
                self.content_type if isinstance(self.content_type, str) else self.content_type.value
            )
        if self.educational_level:
            filters["educational_level"] = (
                self.educational_level
                if isinstance(self.educational_level, str)
                else self.educational_level.value
            )

        # Domain-specific facets
        if self.status:
            filters["status"] = self.status if isinstance(self.status, str) else self.status.value
        if self.priority:
            filters["priority"] = (
                self.priority if isinstance(self.priority, str) else self.priority.value
            )

        # NOUS topic facet — `nous` is the real array property on Ku/PathStep;
        # faceted_search_raw renders scalar-vs-array membership type-agnostically
        if self.nous:
            filters["nous"] = self.nous
        # NOUS sub-topic facet — same array-membership property as `nous`, one
        # level down. Feeds chunk `parent_filters` too, so scoped RAG retrieval
        # honors the sub-topic for free (see SearchRouter.retrieve_scoped_chunks).
        if self.nous_subtopic:
            filters["nous_subtopic"] = self.nous_subtopic
        if self.source:
            filters["source"] = self.source

        # Extended facets
        if self.extended_facets:
            filters.update(self.extended_facets)

        return filters

    def get_graph_label(self) -> str | None:
        """
        Get graph label from domain.

        Maps Domain enum/string to graph node labels.
        """
        if not self.domain:
            return None

        # Domain string to Neo4j label mapping
        # (domain is already a string due to use_enum_values=True)
        label_mapping = {
            "knowledge": "Entity",
            "tasks": "Task",
            "events": "Event",
            "habits": "Habit",
            "goals": "Goal",
            "choices": "Choice",
            "principles": "Principle",
            "journals": "Journal",
        }

        return label_mapping.get(self.domain)

    def to_relationship_filters(self) -> RelationshipFilters:
        """Capture the active relationship-filter flags as transport intent.

        The boolean flags below cross the hexagonal boundary as a plain
        ``RelationshipFilters`` object. The Cypher WHERE-clause fragments that
        realize each flag are authored below the boundary (ADR-044) in
        ``adapters/persistence/neo4j/query/cypher/relationship_filter_fragments.py``
        — a core model must not build Cypher (SKUEL021).

        Returns:
            RelationshipFilters mirroring this request's relationship flags.
        """
        return RelationshipFilters(
            ready_to_learn=self.ready_to_learn,
            builds_on_mastered=self.builds_on_mastered,
            in_active_path=self.in_active_path,
            supports_goals=self.supports_goals,
            builds_on_habits=self.builds_on_habits,
            applied_in_tasks=self.applied_in_tasks,
            aligned_with_principles=self.aligned_with_principles,
            next_logical_step=self.next_logical_step,
            not_yet_viewed=self.not_yet_viewed,
            viewed_not_mastered=self.viewed_not_mastered,
            ready_to_review=self.ready_to_review,
        )

    def has_relationship_filters(self) -> bool:
        """Check if any relationship-based filters are active."""
        return any(
            [
                self.ready_to_learn,
                self.builds_on_mastered,
                self.in_active_path,
                self.supports_goals,
                self.builds_on_habits,
                self.applied_in_tasks,
                self.aligned_with_principles,
                self.next_logical_step,
                # Pedagogical filters
                self.not_yet_viewed,
                self.viewed_not_mastered,
                self.ready_to_review,
            ]
        )

    # ========================================================================
    # UNIFIED SEARCH HELPERS (merged from UnifiedSearchRequest)
    # ========================================================================

    def has_entity_type_filter(self) -> bool:
        """Check if cross-domain entity type filter is specified."""
        return len(self.entity_types) > 0

    def has_graph_traversal_filter(self) -> bool:
        """Check if graph traversal filter is specified."""
        return self.connected_to_uid is not None and self.connected_relationship is not None

    def has_tag_filter(self) -> bool:
        """Check if tag/array filter is specified."""
        return self.tags_contain is not None and len(self.tags_contain) > 0

    def get_sort_order(self) -> SearchSortOrder:
        """``sort_order`` re-hydrated as the enum.

        ``use_enum_values=True`` stores the field as its raw string value, so
        every consumer that wants enum behavior (get_sort_field / is_descending)
        goes through this accessor.
        """
        if isinstance(self.sort_order, SearchSortOrder):
            return self.sort_order
        return SearchSortOrder.from_string(self.sort_order)

    def has_semantic_boost(self) -> bool:
        """Check if semantic relationship boosting is enabled."""
        return (
            self.enable_semantic_boost
            and self.context_uids is not None
            and len(self.context_uids) > 0
        )

    def has_learning_aware(self) -> bool:
        """Check if learning-aware personalization is enabled."""
        return self.enable_learning_aware

    def has_any_criteria(self) -> bool:
        """True if this request defines a result set at all.

        A request has criteria when it carries query text OR any result-defining
        filter: property facets (nous, status, priority, ...), relationship /
        pedagogical flags, an entity-type scope, tags, or a graph traversal.
        The pure enhancement toggles (semantic boost, learning-aware) are
        deliberately excluded — they re-rank a result set, they do not define
        one, so they cannot stand alone.

        The /search route uses this to distinguish the blank initial state
        (show the prompt) from a real filter-only search (run it). Emptiness is
        UX, not a validation error — hence a query is genuinely optional.
        """
        return bool(
            self.query_text
            or self.domain  # programmatic domain-only scope (_resolve_single_domain routes it)
            or self.to_property_filters()
            or self.has_relationship_filters()
            or self.has_entity_type_filter()  # the /search dropdown's entity_types path
            or self.has_tag_filter()
            or self.has_graph_traversal_filter()
        )

    def get_search_strategy(self) -> str:
        """
        Determine the optimal search strategy based on filters.

        Returns:
            'semantic': Use semantic-enhanced search (relationship boosting)
            'learning': Use learning-aware search (personalization)
            'graph': Use graph-aware search (relationship traversal)
            'tags': Use tag/array search
            'text': Use text search only
            'faceted': Use faceted property search
        """
        # Semantic/learning-aware search takes priority
        if self.has_semantic_boost():
            return "semantic"
        if self.has_learning_aware():
            return "learning"
        # Existing strategies
        if self.has_graph_traversal_filter():
            return "graph"
        if self.has_tag_filter():
            return "tags"
        if self.has_relationship_filters():
            return "faceted"  # Boolean graph patterns
        return "text"

    @classmethod
    def from_form_params(
        cls,
        *,
        query: str = "",
        user_uid: UserUID | None = None,
        entity_type: str | None = None,
        sort_order: str = "relevance",
        # Tag facet — CSV of exact tag values (vocabulary via SearchRouter.list_tags)
        tags: str | None = None,
        # Common filters
        status: str | None = None,
        priority: str | None = None,
        # Domain-specific filters
        frequency: str | None = None,
        event_type: str | None = None,
        urgency: str | None = None,
        strength: str | None = None,
        # Knowledge filters
        sel_category: str | None = None,
        learning_level: str | None = None,
        content_type: str | None = None,
        educational_level: str | None = None,
        # Graph relationship filters (checkbox strings)
        ready_to_learn: str | None = None,
        builds_on_mastered: str | None = None,
        in_active_path: str | None = None,
        supports_goals: str | None = None,
        builds_on_habits: str | None = None,
        applied_in_tasks: str | None = None,
        aligned_with_principles: str | None = None,
        next_logical_step: str | None = None,
        # NOUS topic
        nous: str | None = None,
        # NOUS sub-topic (2nd taxonomy level)
        nous_subtopic: str | None = None,
        # Pedagogical filters (checkbox strings)
        not_yet_viewed: str | None = None,
        viewed_not_mastered: str | None = None,
        ready_to_review: str | None = None,
        # Semantic search filters (checkbox strings)
        enable_semantic_boost: str | None = None,
        enable_learning_aware: str | None = None,
        prefer_unmastered: str | None = None,
        # Pagination
        limit: int = 20,
        offset: int = 0,
    ) -> "SearchRequest":
        """Build a SearchRequest from raw HTML form string parameters.

        Handles empty-string-to-None normalization, checkbox-to-bool conversion,
        entity type string parsing, and extended_facets assembly — all the
        coercion that previously lived in the route handler.
        """

        def _none_if_empty(value: str | None) -> str | None:
            return None if not value or value.strip() == "" else value

        def _checkbox_to_bool(value: str | None) -> bool:
            return value == "true" if value else False

        # Normalize optional strings
        status = _none_if_empty(status)
        priority = _none_if_empty(priority)
        sel_category = _none_if_empty(sel_category)
        learning_level = _none_if_empty(learning_level)
        content_type = _none_if_empty(content_type)
        educational_level = _none_if_empty(educational_level)
        nous = _none_if_empty(nous)
        nous_subtopic = _none_if_empty(nous_subtopic)
        entity_type = _none_if_empty(entity_type)

        # Parse entity type to enum
        parsed_entity_types: list[EntityType | NonKuDomain] = []
        if entity_type:
            et = EntityType.from_string(entity_type) or NonKuDomain.from_string(entity_type)
            if et:
                parsed_entity_types = [et]

        # Parse CSV tags → exact-match tag facet
        parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        # Build extended_facets for domain-specific filters
        extended_facets: dict[str, Any] = {
            key: val
            for key, val in [
                ("frequency", _none_if_empty(frequency)),
                ("event_type", _none_if_empty(event_type)),
                ("urgency", _none_if_empty(urgency)),
                ("strength", _none_if_empty(strength)),
            ]
            if val
        }

        return cls(
            # Empty/whitespace query → None: filter-only search is valid, and a
            # bare "" would otherwise trip validate_query_text.
            query_text=_none_if_empty(query),
            entity_types=parsed_entity_types,
            sort_order=SearchSortOrder.from_string(sort_order),
            tags_contain=parsed_tags or None,
            status=_facet_enum_or_none(EntityStatus, status),
            priority=_facet_enum_or_none(Priority, priority),
            extended_facets=extended_facets if extended_facets else None,
            sel_category=_facet_enum_or_none(SELCategory, sel_category),
            learning_level=_facet_enum_or_none(LearningLevel, learning_level),
            content_type=_facet_enum_or_none(ContentType, content_type),
            educational_level=_facet_enum_or_none(EducationalLevel, educational_level),
            ready_to_learn=_checkbox_to_bool(ready_to_learn),
            builds_on_mastered=_checkbox_to_bool(builds_on_mastered),
            in_active_path=_checkbox_to_bool(in_active_path),
            supports_goals=_checkbox_to_bool(supports_goals),
            builds_on_habits=_checkbox_to_bool(builds_on_habits),
            applied_in_tasks=_checkbox_to_bool(applied_in_tasks),
            aligned_with_principles=_checkbox_to_bool(aligned_with_principles),
            next_logical_step=_checkbox_to_bool(next_logical_step),
            nous=nous,
            nous_subtopic=nous_subtopic,
            not_yet_viewed=_checkbox_to_bool(not_yet_viewed),
            viewed_not_mastered=_checkbox_to_bool(viewed_not_mastered),
            ready_to_review=_checkbox_to_bool(ready_to_review),
            enable_semantic_boost=_checkbox_to_bool(enable_semantic_boost),
            enable_learning_aware=_checkbox_to_bool(enable_learning_aware),
            prefer_unmastered=_checkbox_to_bool(prefer_unmastered),
            user_uid=user_uid,
            limit=limit,
            offset=offset,
            include_facet_counts=True,
        )

    model_config = ConfigDict(
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "query_text": "self-awareness practice",
                "domain": "knowledge",
                "sel_category": "self_awareness",
                "learning_level": "beginner",
                "content_type": "practice",
                "educational_level": "high_school",
                "limit": 20,
            }
        },
    )


# ============================================================================
# SEARCH RESPONSE
# ============================================================================


# Stamped on rows the semantic-boost path APPENDS beyond the entity page
# (`SearchRouter._augment_with_body_chunks` does not cap the merge). The /search
# header counts them so a boosted page reads 'Top N results + K lesson-body hits'
# instead of folding K extras into the top-N window.
BODY_HIT_MATCH_REASON = "Matched lesson body"


class SearchResponse(BaseModel):
    """
    Clean search response with results and facet counts.

    Provides everything needed for:
    - Displaying search results
    - Rendering filter badges with counts
    - Pagination
    """

    # Results (polymorphic - can be ku, task, event, etc.)
    results: list[dict[str, Any]] = Field(
        default_factory=list, description="Search results (polymorphic based on domain)"
    )

    # Result metadata
    # Rows in THIS page — search is top-N by design: one page-only query, no
    # match-set count (#555, ruled DROP 2026-08-28). Kept as the API's page size
    # (`total_count`); never read as "how many matched".
    total: int = Field(
        ..., ge=0, description="Number of results in this page (top-N; not a match count)"
    )

    limit: int = Field(..., ge=1, description="Results per page")
    offset: int = Field(..., ge=0, description="Current offset")

    # Query info
    query_text: str | None = Field(default=None, description="Original query text")
    domain: str | None = Field(default=None, description="Searched domain")

    # Facet counts for UI filters
    facet_counts: dict[str, list[FacetCount]] = Field(
        default_factory=dict, description="Facet counts grouped by facet type"
    )

    # Applied filters
    applied_filters: dict[str, Any] = Field(
        default_factory=dict, description="Filters that were applied to this search"
    )

    # Metadata
    search_time_ms: float | None = Field(
        default=None, description="Search execution time in milliseconds"
    )

    timestamp: datetime = Field(default_factory=datetime.now, description="Response timestamp")

    # Capacity warnings for user-aware search — payload shapes in
    # core/ports/query_types.py; produced by SearchRouter._peek_capacity_warnings
    capacity_warnings: CapacityWarnings = Field(
        default_factory=CapacityWarnings,
        description="User capacity warnings (workload, overdue backlog)",
    )

    def has_results(self) -> bool:
        """Check if search returned any results"""
        return len(self.results) > 0

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "results": [
                    {
                        "uid": "ku.self_awareness.001",
                        "title": "Introduction to Self-Awareness",
                        "content_type": "concept",
                        "learning_level": "beginner",
                    }
                ],
                "total": 42,
                "limit": 20,
                "offset": 0,
                "query_text": "self-awareness",
                "domain": "knowledge",
                "facet_counts": {
                    "sel_category": [
                        {
                            "facet_type": "sel_category",
                            "facet_value": "self_awareness",
                            "count": 23,
                            "display_name": "Self-Awareness",
                            "icon": "🧘",
                        }
                    ]
                },
            }
        },
    )


def build_facet_counts(results: list[dict[str, Any]]) -> dict[str, list[FacetCount]]:
    """Facet-value counts across the returned result window.

    Derived from the results actually returned (post-limit), NOT a separate
    count query — cheap enough for the keystroke-driven ``/search`` path and
    consistent with the window-scoped ``total``: search is top-N and never
    counts the match set (#555, ruled DROP 2026-08-28). Two facets today:

    - ``entity_type`` — from the ``_domain`` stamp every SearchRouter
      producer path writes (EntityType values, one vocabulary)
    - ``nous`` — the topic array on curriculum results (Ku/PathStep)

    Counts are sorted descending so the UI can render the dominant facet
    first. Empty results → empty dict (the field's default).
    """
    from collections import Counter

    domain_counts: Counter[str] = Counter()
    nous_counts: Counter[str] = Counter()
    for result in results:
        domain = result.get("_domain")
        if domain:
            domain_counts[str(domain)] += 1
        nous = result.get("nous") or ()
        if isinstance(nous, str):
            nous = (nous,)
        for topic in nous:
            if topic:
                nous_counts[str(topic)] += 1

    counts: dict[str, list[FacetCount]] = {}
    if domain_counts:
        counts["entity_type"] = [
            FacetCount(
                facet_type="entity_type",
                facet_value=value,
                count=count,
                display_name=value.replace("_", " ").title(),
            )
            for value, count in domain_counts.most_common()
        ]
    if nous_counts:
        counts["nous"] = [
            FacetCount(
                facet_type="nous",
                facet_value=value,
                count=count,
                display_name=value.title(),
            )
            for value, count in nous_counts.most_common()
        ]
    return counts


__all__ = ["FacetCount", "SearchRequest", "SearchResponse", "build_facet_counts"]

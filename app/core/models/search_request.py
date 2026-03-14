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
        entity_types=[EntityType.LESSON, EntityType.TASK],
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
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

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
    display_name: str | None = Field(None, description="Human-readable display name")
    icon: str | None = Field(None, description="Emoji icon for this facet")

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
        None,
        min_length=1,
        max_length=500,
        description="Search query text (optional if filters provided)",
    )

    # ========================================================================
    # CORE FACETS (First-class filters - fundamental to SKUEL)
    # ========================================================================

    # Domain filter - which entity type to search
    domain: Domain | None = Field(
        None,
        description="Domain to search: knowledge (ku), tasks, events, habits, goals, choices, principles",
    )

    # SEL Category - for knowledge units
    sel_category: SELCategory | None = Field(
        None,
        description="SEL category: self_awareness, self_management, social_awareness, relationship_skills, responsible_decision_making",
    )

    # Learning level - for content difficulty
    learning_level: LearningLevel | None = Field(
        None, description="Learning level: beginner, intermediate, advanced, expert"
    )

    # Content type - for knowledge units
    content_type: ContentType | None = Field(
        None,
        description="Content type: concept, practice, example, exercise, assessment, resource, summary",
    )

    # Educational level - age-appropriate filtering
    educational_level: EducationalLevel | None = Field(
        None,
        description="Educational level: elementary, middle_school, high_school, college, professional, lifelong",
    )

    # ========================================================================
    # DOMAIN-SPECIFIC FACETS (Common across multiple domains)
    # ========================================================================

    # Status filter - for tasks, events, habits, goals
    status: EntityStatus | None = Field(
        None,
        description="Activity status: draft, scheduled, in_progress, completed, cancelled, etc.",
    )

    # Priority filter - for tasks, events
    priority: Priority | None = Field(
        None, description="Priority level: low, medium, high, critical"
    )

    # ========================================================================
    # RELATIONSHIP-BASED FACETS (Graph-aware filters)
    # ========================================================================

    # Ready to learn - prerequisites are met
    ready_to_learn: bool = Field(
        False,
        description="Filter by prerequisites met (graph pattern: all required knowledge mastered)",
    )

    # Builds on mastered knowledge
    builds_on_mastered: bool = Field(
        False,
        description="Show knowledge connected to mastered units (graph pattern: related to mastered knowledge)",
    )

    # In active learning path
    in_active_path: bool = Field(
        False,
        description="Filter by active learning path membership (graph pattern: part of followed learning path)",
    )

    # Supports active goals
    supports_goals: bool = Field(
        False,
        description="Show knowledge supporting active goals (graph pattern: connected to active goals)",
    )

    # Builds on active habits
    builds_on_habits: bool = Field(
        False,
        description="Show knowledge connected to active habits (graph pattern: reinforces practicing habits)",
    )

    # Applied in recent tasks
    applied_in_tasks: bool = Field(
        False,
        description="Show knowledge used in recent tasks (graph pattern: applied in completed/active tasks)",
    )

    # Recommended by principles
    aligned_with_principles: bool = Field(
        False,
        description="Show knowledge aligned with core principles (graph pattern: supports adopted principles)",
    )

    # Next logical step
    next_logical_step: bool = Field(
        False,
        description="Show natural progression from mastered knowledge (graph pattern: enabled by mastered units)",
    )

    # ========================================================================
    # NOUS-SPECIFIC FACETS (For worldview MOC content)
    # ========================================================================

    # Nous section filter
    nous_section: str | None = Field(
        None,
        description="Filter by nous section slug (stories, environment, intelligence, investment, words, relationships, social, body, exercises, self_management, self_awareness)",
    )

    # Content source filter
    source: str | None = Field(
        None,
        description="Content source: nous, obsidian, manual, ingested",
    )

    # ========================================================================
    # PEDAGOGICAL FILTERS (Learning progress tracking)
    # ========================================================================

    # Not yet viewed - show only unseen content
    not_yet_viewed: bool = Field(
        False,
        description="Show only content the user hasn't viewed yet (graph pattern: no VIEWED relationship)",
    )

    # Viewed but not mastered - in-progress content
    viewed_not_mastered: bool = Field(
        False,
        description="Show content viewed but not yet mastered (graph pattern: VIEWED or IN_PROGRESS but not MASTERED)",
    )

    # Ready for review - spaced repetition
    ready_to_review: bool = Field(
        False,
        description="Show mastered content due for review (graph pattern: MASTERED with decay)",
    )

    # ========================================================================
    # SEMANTIC SEARCH ENHANCEMENT
    # ========================================================================

    # Enable semantic relationship boosting
    enable_semantic_boost: bool = Field(
        False,
        description="Enable semantic relationship boosting (requires context_uids)",
    )

    # Context for semantic boosting
    context_uids: list[str] | None = Field(
        None,
        description="UIDs representing user's current context for semantic boosting (e.g., current learning path, active tasks)",
    )

    # Enable learning-aware personalization
    enable_learning_aware: bool = Field(
        False,
        description="Enable learning state boosting (personalizes results based on user progress)",
    )

    # Learning preference mode
    prefer_unmastered: bool = Field(
        True,
        description="True = prioritize unlearned content, False = prioritize mastered content (review mode)",
    )

    # ========================================================================
    # EXTENDED FACETS (Domain-specific, rarely used)
    # ========================================================================

    extended_facets: dict[str, Any] | None = Field(
        None, description="Extended domain-specific filters (e.g., habit frequency, goal deadline)"
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
        None,
        description="UID of entity to filter by relationship (e.g., 'ku.python-basics')",
    )

    connected_relationship: Any | None = Field(
        None,
        description="RelationshipName for connected_to filter (e.g., ENABLES, REQUIRES_KNOWLEDGE)",
    )

    connected_direction: str = Field(
        "outgoing",
        description="Relationship direction: 'outgoing', 'incoming', or 'both'",
    )

    # ========================================================================
    # ARRAY/TAG SEARCH
    # ========================================================================

    tags_contain: list[str] | None = Field(
        None,
        description="Filter by tags containing these values",
    )

    tags_match_all: bool = Field(
        False,
        description="True = AND semantics (all tags must match), False = OR semantics (any tag matches)",
    )

    # ========================================================================
    # PAGINATION & OPTIONS
    # ========================================================================

    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")

    offset: int = Field(0, ge=0, description="Pagination offset")

    include_facet_counts: bool = Field(True, description="Include facet counts for UI filters")

    user_uid: str | None = Field(None, description="User ID for personalized results (optional)")

    @field_validator("query_text")
    @classmethod
    def validate_query_text(cls, v) -> Any:
        """Ensure query text is not empty when provided"""
        if v is not None and not v.strip():
            raise ValueError("Query text cannot be empty or whitespace")
        return v.strip() if v else None

    @field_validator("domain")
    @classmethod
    def validate_has_query_or_filters(cls, v, info: ValidationInfo) -> Any:
        """Ensure at least query_text OR facet filters are provided"""
        query_text = info.data.get("query_text")

        # If no query text, must have at least one filter
        if not query_text:
            has_filter = any(
                [
                    v is not None,  # domain itself
                    info.data.get("sel_category") is not None,
                    info.data.get("learning_level") is not None,
                    info.data.get("content_type") is not None,
                    info.data.get("educational_level") is not None,
                    info.data.get("status") is not None,
                    info.data.get("priority") is not None,
                    info.data.get("nous_section") is not None,
                    info.data.get("source") is not None,
                    info.data.get("extended_facets"),
                ]
            )

            if not has_filter:
                raise ValueError("Must provide either query_text or at least one filter")

        return v

    def to_property_filters(self) -> dict[str, Any]:
        """
        Convert facets to property filters.

        Used by UniversalNeo4jBackend.find_by() for dynamic queries.
        All facets become WHERE clauses in Cypher.
        """
        filters = {}

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

        # Nous-specific facets
        if self.nous_section:
            filters["nous_section"] = self.nous_section
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

    def to_graph_patterns(self) -> dict[str, str]:
        """
        Convert relationship filters to Cypher graph patterns.

        This is the core of graph-native search - converting boolean flags into
        Cypher relationship patterns that leverage Neo4j's graph structure.

        Returns:
            Dictionary mapping pattern names to Cypher WHERE clause fragments

        Note:
            Patterns reference $user_uid as a Cypher query parameter placeholder.
            The actual user_uid value is provided at query EXECUTION time via params dict,
            not at pattern building time.

        Example:
            >>> request = SearchRequest(ready_to_learn=True, domain="knowledge")
            >>> patterns = request.to_graph_patterns()
            >>> patterns["ready_to_learn"]
            'NOT EXISTS { MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity) ... }'

            >>> # Later, at query execution:
            >>> params = {"user_uid": "user_123"}  # $user_uid gets filled here
            >>> results = await execute_query(cypher_with_patterns, params)
        """
        patterns = {}

        # Pattern 1: Ready to learn (all prerequisites mastered)
        if self.ready_to_learn:
            patterns["ready_to_learn"] = """
            NOT EXISTS {
                MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
                WHERE NOT EXISTS {
                    MATCH (user:User {uid: $user_uid})-[:MASTERED]->(prereq)
                }
            }
            """

        # Pattern 2: Builds on mastered knowledge (related to what user knows)
        if self.builds_on_mastered:
            patterns["builds_on_mastered"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
                WHERE (mastered)-[:ENABLES_LEARNING|RELATED_TO]-(ku)
            }
            """

        # Pattern 3: In active learning path
        if self.in_active_path:
            patterns["in_active_path"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[:ENROLLED_IN]->(lp:Lp)
                      -[:CONTAINS_STEP]->(ls:Ls)
                      -[:REQUIRES_KNOWLEDGE]->(ku)
                WHERE lp.status = 'active'
            }
            """

        # Pattern 4: Supports active goals
        if self.supports_goals:
            patterns["supports_goals"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[:PURSUING_GOAL]->(goal:Goal)
                      -[:REQUIRES_KNOWLEDGE]->(ku)
                WHERE goal.status IN ['active', 'in_progress']
            }
            """

        # Pattern 5: Builds on active habits
        if self.builds_on_habits:
            patterns["builds_on_habits"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[:PRACTICES]->(habit:Habit)
                      -[:APPLIES_KNOWLEDGE]->(ku)
                WHERE habit.status IN ['active', 'in_progress']
                  AND habit.is_active = true
            }
            """

        # Pattern 6: Applied in recent tasks
        if self.applied_in_tasks:
            patterns["applied_in_tasks"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[:OWNS]->(task:Task)
                      -[:APPLIES_KNOWLEDGE]->(ku)
                WHERE task.status IN ['completed', 'in_progress']
                  AND task.updated_at >= datetime() - duration({days: 30})
            }
            """

        # Pattern 7: Aligned with principles
        if self.aligned_with_principles:
            patterns["aligned_with_principles"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[:ADHERES_TO]->(principle:Principle)
                      -[:EMBODIES_KNOWLEDGE]->(ku)
                WHERE principle.status = 'adopted'
                  OR principle.priority >= 0.7
            }
            """

        # Pattern 8: Next logical step
        if self.next_logical_step:
            patterns["next_logical_step"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[:MASTERED]->(mastered:Entity)
                      -[:ENABLES_LEARNING]->(ku)
                WHERE NOT EXISTS {
                    MATCH (user)-[:MASTERED]->(ku)
                }
                AND NOT EXISTS {
                    MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
                    WHERE NOT EXISTS {
                        MATCH (user)-[:MASTERED]->(prereq)
                    }
                }
            }
            """

        # ====================================================================
        # PEDAGOGICAL PATTERNS (Learning progress tracking)
        # ====================================================================

        # Pattern 9: Not yet viewed - show unseen content
        if self.not_yet_viewed:
            patterns["not_yet_viewed"] = """
            NOT EXISTS {
                MATCH (user:User {uid: $user_uid})-[:VIEWED|IN_PROGRESS|MASTERED]->(ku)
            }
            """

        # Pattern 10: Viewed but not mastered - in-progress content
        if self.viewed_not_mastered:
            patterns["viewed_not_mastered"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[:VIEWED|IN_PROGRESS]->(ku)
            }
            AND NOT EXISTS {
                MATCH (user:User {uid: $user_uid})-[:MASTERED]->(ku)
            }
            """

        # Pattern 11: Ready for review (mastered but not reviewed recently)
        if self.ready_to_review:
            patterns["ready_to_review"] = """
            EXISTS {
                MATCH (user:User {uid: $user_uid})-[m:MASTERED]->(ku)
                WHERE m.mastered_at <= datetime() - duration({days: 30})
            }
            """

        return patterns

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
    total: int = Field(..., ge=0, description="Total number of matching results")

    limit: int = Field(..., ge=1, description="Results per page")
    offset: int = Field(..., ge=0, description="Current offset")

    # Query info
    query_text: str | None = Field(None, description="Original query text")
    domain: str | None = Field(None, description="Searched domain")

    # Facet counts for UI filters
    facet_counts: dict[str, list[FacetCount]] = Field(
        default_factory=dict, description="Facet counts grouped by facet type"
    )

    # Applied filters
    applied_filters: dict[str, Any] = Field(
        default_factory=dict, description="Filters that were applied to this search"
    )

    # Metadata
    search_time_ms: float | None = Field(None, description="Search execution time in milliseconds")

    timestamp: datetime = Field(default_factory=datetime.now, description="Response timestamp")

    # P5: Capacity warnings for user-aware search
    capacity_warnings: dict[str, Any] = Field(
        default_factory=dict,
        description="User capacity warnings (workload, energy, time constraints)",
    )

    def has_results(self) -> bool:
        """Check if search returned any results"""
        return len(self.results) > 0

    def has_more_pages(self) -> bool:
        """Check if there are more pages available"""
        return (self.offset + self.limit) < self.total

    def get_page_info(self) -> dict[str, int]:
        """Get pagination information"""
        current_page = (self.offset // self.limit) + 1
        total_pages = (self.total + self.limit - 1) // self.limit

        return {
            "current_page": current_page,
            "total_pages": total_pages,
            "showing_from": self.offset + 1,
            "showing_to": min(self.offset + self.limit, self.total),
            "total_results": self.total,
        }

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


__all__ = ["FacetCount", "SearchRequest", "SearchResponse"]

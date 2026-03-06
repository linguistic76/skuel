"""
Search Field Configuration - Centralized Search Schema
=======================================================

*Last updated: 2026-01-04*

Single source of truth for what fields are searchable per entity type.
Aligns search capabilities with ingestion fields for harmonization.

This configuration documents and centralizes the `_search_fields` class
attributes used across all domain search services.

Usage:
    from core.services.search.config import SEARCH_FIELD_CONFIG, SearchFieldConfig

    # Get search fields for an entity type
    fields = SEARCH_FIELD_CONFIG[EntityType.ARTICLE].text_fields

    # Check if a field is searchable
    if "content" in SEARCH_FIELD_CONFIG[EntityType.ARTICLE].text_fields:
        # Field is text-searchable

Graph-Aware Search:
    BaseService provides `search_connected_to()` which combines text search
    with relationship traversal in a single Neo4j query:

        # Find KUs containing "python" that ENABLE content I've mastered
        result = await ku_service.search_connected_to(
            query="python",
            related_uid="ku.python-basics",
            relationship_type=RelationshipName.ENABLES_KNOWLEDGE,
            direction="outgoing"
        )

Tag/Array Search:
    BaseService provides `search_by_tags()` and `search_array_field()` for
    searching within array fields like tags:

        # Find KUs with ANY of these tags (OR)
        result = await ku_service.search_by_tags(
            tags=["python", "ml"],
            match_all=False
        )

        # Find KUs with ALL of these tags (AND)
        result = await ku_service.search_by_tags(
            tags=["python", "beginner"],
            match_all=True
        )

        # Search any array field
        result = await service.search_array_field("categories", "investment")

Unified Search API:
    SearchRouter provides `advanced_search()` combining all phases in one call.
    SearchRequest is THE canonical request model (One Path Forward).

        from core.models.search import SearchRouter
        from core.models.search_request import SearchRequest

        request = SearchRequest(
            query_text="machine learning",
            entity_types=[EntityType.ARTICLE, EntityType.TASK],
            connected_to_uid="ku.python-basics",
            connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
            tags_contain=["python", "beginner"],
            tags_match_all=False, # OR semantics
        )
        result = await router.advanced_search(request)

    REST API endpoint: POST /api/search/unified

Architecture Notes:
    - Each domain service still defines `_search_fields` class attribute
    - This config serves as documentation and for unified search API
    - BaseService.search() uses text_fields for text search
    - BaseService.search_connected_to() combines text search + graph traversal
    - BaseService.search_by_tags() searches within array fields (ANY/ALL)
    - BaseService.search_array_field() generic array field search
    - SearchRouter.advanced_search() combines all phases with smart strategy selection
"""

from dataclasses import dataclass

from core.models.enums.entity_enums import EntityType, NonKuDomain


@dataclass(frozen=True)
class SearchFieldConfig:
    """
    Configuration for searchable fields per entity type.

    Attributes:
        text_fields: Fields searched via text CONTAINS (OR semantics)
        array_fields: Fields searched via array membership (tags, etc.)
        filter_fields: Fields for exact-match filtering (find_by)
        order_by: Default ordering field for search results
    """

    text_fields: tuple[str, ...] = ("title", "description")
    array_fields: tuple[str, ...] = ()
    filter_fields: tuple[str, ...] = ("status", "domain")
    order_by: str = "created_at"


# =============================================================================
# CENTRALIZED SEARCH FIELD CONFIGURATION
# =============================================================================
#
# This configuration mirrors what each domain service has in _search_fields.
# It provides a single reference point for:
# 1. Documentation of what's searchable
# 2. Future unified search API
# 3. Validation that services are aligned
#
# When modifying search fields:
# 1. Update the domain service's _search_fields
# 2. Update this config to match
# 3. Run tests to verify alignment

SEARCH_FIELD_CONFIG: dict[EntityType | NonKuDomain, SearchFieldConfig] = {
    # =========================================================================
    # CURRICULUM DOMAINS (4) - Content-rich entities
    # =========================================================================
    EntityType.ARTICLE: SearchFieldConfig(
        # Matches ArticleCoreService._search_fields = ["title", "content", "tags"]
        # Note: tags is stored as array but searched as text (JSON string match)
        text_fields=("title", "content", "tags"),
        array_fields=(),  # Future: add proper array search for tags
        filter_fields=("domain", "complexity", "learning_level", "status"),
        order_by="quality_score",
    ),
    EntityType.LEARNING_STEP: SearchFieldConfig(
        text_fields=("title", "intent", "description"),
        array_fields=(),
        filter_fields=("domain", "status"),
        order_by="step_order",
    ),
    EntityType.LEARNING_PATH: SearchFieldConfig(
        text_fields=("name", "goal", "description"),
        array_fields=("tags",),
        filter_fields=("domain", "difficulty", "status"),
        order_by="created_at",
    ),
    # =========================================================================
    # ACTIVITY DOMAINS (6) - User action entities
    # =========================================================================
    EntityType.TASK: SearchFieldConfig(
        text_fields=("title", "description"),
        array_fields=("tags",),
        filter_fields=("status", "priority", "domain"),
        order_by="due_date",
    ),
    EntityType.GOAL: SearchFieldConfig(
        text_fields=("title", "description"),
        array_fields=("tags",),
        filter_fields=("status", "domain", "priority"),
        order_by="target_date",
    ),
    EntityType.HABIT: SearchFieldConfig(
        text_fields=("title", "description"),
        array_fields=("tags",),
        filter_fields=("status", "domain", "frequency"),
        order_by="created_at",
    ),
    EntityType.EVENT: SearchFieldConfig(
        text_fields=("title", "description"),
        array_fields=("tags",),
        filter_fields=("status", "domain", "event_type"),
        order_by="event_date",
    ),
    EntityType.CHOICE: SearchFieldConfig(
        text_fields=("title", "description", "context"),
        array_fields=("tags",),
        filter_fields=("status", "domain", "urgency"),
        order_by="decision_deadline",
    ),
    EntityType.PRINCIPLE: SearchFieldConfig(
        text_fields=("name", "statement", "description", "why_important"),
        array_fields=("tags",),
        filter_fields=("domain", "strength"),
        order_by="created_at",
    ),
    # =========================================================================
    # FINANCE DOMAIN (1) - Standalone financial tracking
    # =========================================================================
    NonKuDomain.FINANCE: SearchFieldConfig(
        text_fields=("description", "notes"),
        array_fields=("tags",),
        filter_fields=("category", "status", "payment_method"),
        order_by="expense_date",
    ),
}


def get_search_fields(entity_type: EntityType | NonKuDomain) -> tuple[str, ...]:
    """
    Get text search fields for an entity type.

    Falls back to default ("title", "description") if entity type not configured.
    """
    config = SEARCH_FIELD_CONFIG.get(entity_type)
    if config:
        return config.text_fields
    return ("title", "description")


def get_array_fields(entity_type: EntityType | NonKuDomain) -> tuple[str, ...]:
    """
    Get array fields (like tags) for an entity type.

    Returns empty tuple if entity type not configured.
    """
    config = SEARCH_FIELD_CONFIG.get(entity_type)
    if config:
        return config.array_fields
    return ()


def get_filter_fields(entity_type: EntityType | NonKuDomain) -> tuple[str, ...]:
    """
    Get filter fields for an entity type.

    Falls back to default ("status", "domain") if not configured.
    """
    config = SEARCH_FIELD_CONFIG.get(entity_type)
    if config:
        return config.filter_fields
    return ("status", "domain")


__all__ = [
    "SEARCH_FIELD_CONFIG",
    "SearchFieldConfig",
    "get_array_fields",
    "get_filter_fields",
    "get_search_fields",
]

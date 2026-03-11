---
title: Search Models Reference
created: 2026-01-03
updated: 2026-01-04
status: active
category: reference
tags: [search, models, reference, pedagogical, nous]
---

# Search Models Reference

**Source:** `/core/models/search_request.py`
**Last Updated:** January 4, 2026

## Overview

This document provides the canonical reference for SKUEL's search models: `SearchRequest`, `SearchResponse`, and `FacetCount`.

**Core Principle:** "Search by domain, filter by facets"

## FacetCount Model

Count of results per facet value - for UI filter badges.

```python
class FacetCount(BaseModel):
    """Count of results per facet value - for UI filter badges."""

    facet_type: str          # Type of facet (sel_category, learning_level, etc.)
    facet_value: str         # Value of facet (self_awareness, beginner, etc.)
    count: int               # Number of results with this facet (>= 0)
    display_name: str | None # Human-readable display name
    icon: str | None         # Emoji icon for this facet
```

**Usage:**
Used by FrankenUI to show how many results exist for each filter option.

```html
<button uk-filter="sel_category: self_awareness">
    Self-Awareness 🧘 ({{count}})
</button>
```

## SearchRequest Model

Clean, simple search request - the foundation of SKUEL search.

### Core Features

- **Query text is OPTIONAL** - Can do filter-only search
- **Core facets are first-class fields** - Not buried in dictionaries
- **All facets map to Neo4j properties** - Via dynamic queries
- **Relationship-based filters** - Graph-aware search patterns

### Field Categories

#### Search Query (Optional)

```python
query_text: str | None = None  # Search query text (optional if filters provided)
                               # Min: 1, Max: 500 characters
```

**Validation:** At least `query_text` OR one filter must be provided.

#### Core Facets (Fundamental to SKUEL)

```python
# Domain filter - which entity type to search
domain: Domain | None = None
# Options: knowledge (ku), tasks, events, habits, goals, choices, principles

# SEL Category - for knowledge units
sel_category: SELCategory | None = None
# Options: self_awareness, self_management, social_awareness,
#          relationship_skills, responsible_decision_making

# Learning level - for content difficulty
learning_level: LearningLevel | None = None
# Options: beginner, intermediate, advanced, expert

# Content type - for knowledge units
content_type: ContentType | None = None
# Options: concept, practice, example, exercise, assessment, resource, summary

# Educational level - age-appropriate filtering
educational_level: EducationalLevel | None = None
# Options: elementary, middle_school, high_school, college, professional, lifelong
```

#### Domain-Specific Facets

```python
# Status filter - for tasks, events, habits, goals
status: EntityStatus | None = None
# Options: draft, scheduled, in_progress, completed, cancelled, etc.

# Priority filter - for tasks, events
priority: Priority | None = None
# Options: low, medium, high, critical
```

#### Relationship-Based Facets (Graph-Aware Filters)

```python
# Ready to learn - prerequisites are met
ready_to_learn: bool = False
# Graph pattern: all required knowledge mastered

# Builds on mastered knowledge
builds_on_mastered: bool = False
# Graph pattern: related to mastered knowledge

# In active learning path
in_active_path: bool = False
# Graph pattern: part of followed learning path

# Supports active goals
supports_goals: bool = False
# Graph pattern: connected to active goals

# Builds on active habits
builds_on_habits: bool = False
# Graph pattern: reinforces practicing habits

# Applied in recent tasks
applied_in_tasks: bool = False
# Graph pattern: applied in completed/active tasks

# Aligned with principles
aligned_with_principles: bool = False
# Graph pattern: supports adopted principles

# Next logical step
next_logical_step: bool = False
# Graph pattern: enabled by mastered units
```

#### Nous-Specific Facets

```python
# Nous section filter - for Worldview MOC content
nous_section: str | None = None
# Options: "stories", "environment", "intelligence", "consciousness",
#          "identity", "cosmos", "society", "history", "tech", "values", "practice"
# Example: nous_section="stories" filters to Stories section content

# Content source filter
source: str | None = None
# Options: "nous", "obsidian", "manual", "ingested"
# Example: source="nous" filters to Worldview MOC content only
```

#### Pedagogical Filters (Learning Progress)

```python
# Not yet viewed - content user hasn't seen
not_yet_viewed: bool = False
# Graph pattern: no VIEWED/IN_PROGRESS/MASTERED relationship exists

# Viewed but not mastered - content being learned
viewed_not_mastered: bool = False
# Graph pattern: VIEWED or IN_PROGRESS exists, but not MASTERED

# Ready to review - mastered content due for spaced repetition
ready_to_review: bool = False
# Graph pattern: MASTERED exists (future: time-based review scheduling)
```

**Note:** Pedagogical filters trigger graph-aware search mode (same as relationship filters).

#### Extended Facets

```python
# Extended domain-specific filters (rarely used)
extended_facets: dict[str, Any] | None = None
# Example: habit frequency, goal deadline
```

#### Pagination & Options

```python
limit: int = 20              # Maximum results (1-100)
offset: int = 0              # Pagination offset (>= 0)
include_facet_counts: bool = True  # Include facet counts for UI
user_uid: str | None = None  # User ID for personalized results
```

### Key Methods

#### to_property_filters()

Convert facets to property filters.

```python
def to_property_filters() -> dict[str, Any]:
    """Convert facets to WHERE clauses."""
    # Returns: {property_name: value}
    # Example: {"domain": "knowledge", "learning_level": "beginner"}
```

#### get_graph_label()

Get graph label from domain.

```python
def get_graph_label() -> str | None:
    """Maps Domain enum to graph node labels."""
    # Example: "knowledge" → "Entity"
    #          "tasks" → "Task"
```

#### to_graph_patterns()

Convert relationship filters to Cypher graph patterns.

```python
def to_graph_patterns() -> dict[str, str]:
    """
    Convert boolean flags into Cypher relationship patterns.
    Core of graph-native search.

    Returns: {pattern_name: cypher_where_clause}
    """
```

**Note:** Patterns reference `$user_uid` as a Cypher query parameter placeholder. The actual user_uid value is provided at query execution time.

#### has_relationship_filters()

Check if any relationship filters are active.

```python
def has_relationship_filters() -> bool:
    """Determines search mode routing (Simple vs Graph-Aware)."""
    # Returns: True if any relationship filter is True
```

### Usage Examples

```python
from core.models.search_request import SearchRequest
from core.models.enums import Domain, Priority

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
    content_type=ContentType.PRACTICE,
    educational_level=EducationalLevel.HIGH_SCHOOL,
)

# Filter-only search (no text query)
request = SearchRequest(
    domain=Domain.TASKS,
    priority=Priority.HIGH,
    status=EntityStatus.ACTIVE
)

# Graph-aware search (relationship filters)
request = SearchRequest(
    query_text="meditation",
    domain=Domain.KNOWLEDGE,
    ready_to_learn=True,  # Triggers graph-aware search
    supports_goals=True
)

# Nous-specific search (Worldview content)
request = SearchRequest(
    query_text="creativity",
    nous_section="stories",  # Filter to Stories section
    source="nous",           # Only nous content
)

# Pedagogical search (learning progress)
request = SearchRequest(
    domain=Domain.KNOWLEDGE,
    not_yet_viewed=True,     # Only content user hasn't seen
)

# Combined nous + pedagogical
request = SearchRequest(
    nous_section="intelligence",
    viewed_not_mastered=True,  # In-progress intelligence content
)
```

## SearchResponse Model

Clean search response with results and facet counts.

### Fields

```python
class SearchResponse(BaseModel):
    """Clean search response with results and facet counts."""

    # Results (polymorphic - can be ku, task, event, etc.)
    results: list[dict[str, Any]] = []
    # Polymorphic based on domain

    # Result metadata
    total: int           # Total number of matching results (>= 0)
    limit: int           # Results per page (>= 1)
    offset: int          # Current offset (>= 0)

    # Query info
    query_text: str | None  # Original query text (can be None for filter-only)
    domain: str | None      # Searched domain

    # Facet counts for UI filters
    facet_counts: dict[str, list[FacetCount]] = {}
    # Grouped by facet type
    # Example: {
    #   "learning_level": [
    #     FacetCount(facet_type="learning_level", facet_value="beginner", count=42),
    #     FacetCount(facet_type="learning_level", facet_value="intermediate", count=28)
    #   ]
    # }

    # Applied filters
    applied_filters: dict[str, Any] = {}
    # Filters that were applied to this search

    # Metadata
    search_time_ms: float | None  # Search execution time in milliseconds
    timestamp: datetime           # Response timestamp

    # Capacity warnings (user-aware search)
    capacity_warnings: dict[str, Any] = {}
    # User capacity warnings (workload, energy, time constraints)
```

### Key Methods

#### has_results()

```python
def has_results() -> bool:
    """Check if search returned any results."""
    return len(results) > 0
```

#### has_more_pages()

```python
def has_more_pages() -> bool:
    """Check if there are more pages available."""
    return (offset + limit) < total
```

#### get_page_info()

```python
def get_page_info() -> dict[str, int]:
    """
    Get pagination information.

    Returns:
        {
            "current_page": int,  # Current page number (1-indexed)
            "total_pages": int,   # Total number of pages
            "showing_from": int,  # First result index (1-indexed)
            "showing_to": int,    # Last result index (1-indexed)
            "total_results": int  # Total matching results
        }
    """
```

### Usage Example

```python
from core.models.search_request import SearchResponse, FacetCount

response = SearchResponse(
    results=[
        {"uid": "ku.meditation", "title": "Meditation Basics", ...},
        {"uid": "ku.mindfulness", "title": "Mindfulness Practice", ...}
    ],
    total=42,
    limit=20,
    offset=0,
    query_text="meditation",
    domain="knowledge",
    facet_counts={
        "learning_level": [
            FacetCount(
                facet_type="learning_level",
                facet_value="beginner",
                count=15,
                display_name="Beginner",
                icon="🌱"
            )
        ]
    },
    applied_filters={"domain": "knowledge"},
    search_time_ms=23.4
)

# Check pagination
if response.has_results():
    print(f"Found {response.total} results")

if response.has_more_pages():
    print("More results available")

page_info = response.get_page_info()
# {"current_page": 1, "total_pages": 3, "showing_from": 1, "showing_to": 20, ...}
```

## Search Modes

SearchRequest automatically routes to appropriate search mode:

| Mode | Trigger | Implementation |
|------|---------|----------------|
| **Simple Search** | Property filters only (incl. `nous_section`, `source`) | `SimpleSearchService` |
| **Graph-Aware Search** | Any relationship OR pedagogical filter = True | Domain-specific graph handlers |

**Routing Logic:**
```python
if request.has_relationship_filters():
    # Includes relationship filters (ready_to_learn, etc.)
    # AND pedagogical filters (not_yet_viewed, viewed_not_mastered, ready_to_review)
    return await _graph_aware_search(request)
else:
    # Use simple property-based search
    return await _simple_search(request)
```

**Note:** `nous_section` and `source` are property filters (Simple Search), while pedagogical filters require graph traversal (Graph-Aware Search).

## Integration Points

### FrankenUI Integration

```html
<!-- Filter badges with counts -->
<div uk-filter="target: .js-filter">
    <button uk-filter="domain: knowledge">
        Knowledge ({{facet_count}})
    </button>
</div>
```

### Neo4j Mapping

| SearchRequest Field | Neo4j Mapping |
|---------------------|---------------|
| `domain` | Node label (Ku, Task, Event, etc.) |
| `sel_category` | Property filter |
| `learning_level` | Property filter |
| `nous_section` | Property filter (`ku.nous_section`) |
| `source` | Property filter (`ku.source`) |
| `ready_to_learn` | Graph pattern (prerequisites) |
| `supports_goals` | Graph pattern (relationships) |
| `not_yet_viewed` | Graph pattern (`NOT EXISTS VIEWED/IN_PROGRESS/MASTERED`) |
| `viewed_not_mastered` | Graph pattern (`EXISTS VIEWED/IN_PROGRESS, NOT EXISTS MASTERED`) |
| `ready_to_review` | Graph pattern (`EXISTS MASTERED`) |

## See Also

- [search_service_pattern.md](../../patterns/search_service_pattern.md) - Search service implementation pattern
- [SIMPLE_SEARCH_QUICK_REFERENCE.md](../../guides/SIMPLE_SEARCH_QUICK_REFERENCE.md) - Quick reference and examples
- [SIMPLE_SEARCH_SETUP_GUIDE.md](../../guides/SIMPLE_SEARCH_SETUP_GUIDE.md) - Setup and integration guide
- [SEARCH_ARCHITECTURE.md](../../architecture/SEARCH_ARCHITECTURE.md) - Complete search architecture
- `/core/models/search_request.py` - Source code (canonical)

---

**Status:** Active - Canonical reference for all search model documentation

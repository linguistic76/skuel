---
title: SearchService Pattern for Activity Domains
updated: 2026-01-07
category: patterns
related_skills:
- base-analytics-service
- skuel-search-architecture
- neo4j-genai-plugin
related_docs:
- /docs/decisions/ADR-025-service-consolidation-patterns.md
---

# SearchService Pattern for Activity Domains

*Last updated: 2026-01-06*
## Related Skills

For implementation guidance, see:
- [@base-analytics-service](../../.claude/skills/base-analytics-service/SKILL.md)
- [@neo4j-genai-plugin](../../.claude/skills/neo4j-genai-plugin/SKILL.md)
- [@skuel-search-architecture](../../.claude/skills/skuel-search-architecture/SKILL.md)


## Overview

The SearchService pattern separates search and discovery concerns from CRUD operations across all 6 activity domains in SKUEL. Each domain has a dedicated SearchService that implements the `DomainSearchOperations[T]` protocol plus domain-specific methods.

## Core Principle

> "Search is fundamental to SKUEL. Search builds UserContext. Askesis is built on top of both the UserContext and search."

Search is recognized as a **separation of concerns** issue. All activity domains treat search similarly with consistent interfaces, while allowing domain-specific search capabilities.

## Architecture

### Activity Domains with SearchServices

| Domain | SearchService | Entity Type |
|--------|--------------|-------------|
| Tasks | `TaskSearchService` | `Task` |
| Goals | `GoalSearchService` | `Goal` |
| Habits | `HabitSearchService` | `Habit` |
| Events | `EventSearchService` | `Event` |
| Choices | `ChoiceSearchService` | `Choice` |
| Principles | `PrincipleSearchService` | `Principle` |

### Service Responsibility Split

**SearchService responsibilities:**
- Text search (title, description)
- Filter by status/category/domain
- Date range queries (due soon, overdue)
- Graph-based discovery (find by relationship)
- Learning-aligned discovery
- User-context-aware prioritization

**CoreService responsibilities (remaining):**
- CRUD (create, get, update, delete)
- Status transitions (activate, pause, complete, archive)
- Basic `get_user_items()` and `get_user_items_in_range()`

## DomainSearchOperations Protocol

All SearchServices implement `DomainSearchOperations[T]` from `/core/services/protocols/search_protocols.py`:

```python
@runtime_checkable
class DomainSearchOperations(Protocol[T]):
    """Standard search interface for activity domain services."""

    # Universal methods - ALL domains implement these
    async def search(self, query: str, limit: int = 50) -> Result[list[T]]: ...
    async def get_by_status(self, status: str, limit: int = 100) -> Result[list[T]]: ...
    async def get_by_domain(self, domain: Domain, limit: int = 100) -> Result[list[T]]: ...
    async def get_prioritized(self, user_context: UserContext, limit: int = 10) -> Result[list[T]]: ...
    async def get_by_relationship(self, related_uid: str, relationship_type: str, direction: str = "outgoing") -> Result[list[T]]: ...
    async def get_due_soon(self, days_ahead: int = 7) -> Result[list[T]]: ...
    async def get_overdue(self, limit: int = 100) -> Result[list[T]]: ...
```

## BaseService Generic Filter Methods (January 2026)

`BaseService` provides **default implementations** for common filter methods, eliminating duplication across SearchServices:

### Inherited Methods

| Method | Purpose | Configuration |
|--------|---------|---------------|
| `search()` | Text search on configurable fields | `_search_fields`, `_search_order_by` |
| `get_by_relationship()` | Graph traversal queries | Uses `_dto_class`, `_model_class` |
| `get_by_status()` | Filter by status field | Generic implementation |
| `get_by_domain()` | Filter by Domain enum | Generic implementation |
| `get_by_category()` | Filter by category field | Uses `_category_field` |
| `list_categories()` | List unique category values | Uses `_category_field` |
| `get_prerequisites()` | Traverse prerequisite chains | Uses `_prerequisite_relationships` |
| `get_enables()` | Traverse enables chains | Uses `_enables_relationships` |
| `get_user_progress()` | Get user completion/mastery | Requires `_supports_user_progress = True` |
| `update_user_mastery()` | Update progress level | Requires `_supports_user_progress = True` |
| `get_user_curriculum()` | Get entities by progress state | Requires `_supports_user_progress = True` |

### Class Attributes for Configuration

```python
class GoalsSearchService(BaseService[GoalsOperations, Goal]):
    # Required for all inherited methods
    _dto_class = GoalDTO
    _model_class = Goal

    # Optional overrides (defaults shown)
    _search_fields = ["title", "description"]  # Fields for text search
    _search_order_by = "created_at"            # Sort order for results
    _category_field = "category"               # Field for get_by_category/list_categories

    # Prerequisite/enables chains (January 2026)
    _prerequisite_relationships: ClassVar[list[str]] = [
        RelationshipName.REQUIRES_KNOWLEDGE.value,
        RelationshipName.DEPENDS_ON_GOAL.value,
    ]
    _enables_relationships: ClassVar[list[str]] = [
        RelationshipName.ENABLES_GOAL.value,
    ]

    # Progress tracking (January 2026)
    _supports_user_progress: ClassVar[bool] = True
```

### When to Override

Override inherited methods when domain-specific logic differs:

```python
# PrincipleSearchService overrides get_by_status() because
# Principles use is_active boolean instead of status string
async def get_by_status(self, status: str, limit: int = 100) -> Result[list[Principle]]:
    is_active = status.lower() in ("active", "true", "1")
    result = await self.backend.find_by(is_active=is_active, limit=limit)
    # ...
```

**Common override scenarios:**
- Different field names (e.g., Goals use `domain` for categorization → `_category_field = "domain"`)
- Different data types (e.g., Principles use `is_active` boolean instead of `status` string)
- Domain-specific enum mapping (e.g., Principles map Domain → PrincipleCategory)

## Graph-Aware Search (January 2026)

BaseService now provides **Neo4j-native graph-aware search** that combines text search with relationship traversal in a single query. This leverages Neo4j's unique graph capabilities.

### New BaseService Methods

| Method | Purpose | Use Case |
|--------|---------|----------|
| `search_connected_to()` | Text search + relationship filter | "Find KUs about 'python' that ENABLE content I've mastered" |
| `search_by_tags()` | Array field search with AND/OR | "Find KUs tagged with 'python' AND 'beginner'" |
| `search_array_field()` | Generic array field search | "Find entities where categories contains 'investment'" |

### Usage Examples

```python
# Graph-aware search: text + relationship in ONE query
result = await ku_service.search_connected_to(
    query="machine learning",
    related_uid="ku.python-basics",
    relationship_type=RelationshipName.ENABLES_KNOWLEDGE,
    direction="outgoing",
    limit=20
)

# Tag search with OR semantics (any tag matches)
result = await ku_service.search_by_tags(
    tags=["python", "ml"],
    match_all=False,  # OR
    limit=50
)

# Tag search with AND semantics (all tags must match)
result = await ku_service.search_by_tags(
    tags=["python", "beginner"],
    match_all=True,  # AND
    limit=50
)
```

### Centralized Search Field Configuration

Search fields are configured centrally in `core/services/search/config.py`:

```python
from core.services.search.config import SEARCH_FIELD_CONFIG, get_search_fields
from core.models.shared_enums import EntityType

# Get text search fields for an entity type
fields = get_search_fields(EntityType.KU)  # ('title', 'content', 'tags')
fields = get_search_fields(EntityType.TASK)  # ('title', 'description')

# Full config includes text_fields, array_fields, filter_fields, order_by
config = SEARCH_FIELD_CONFIG[EntityType.KU]
# SearchFieldConfig(
#     text_fields=('title', 'content', 'tags'),
#     array_fields=(),
#     filter_fields=('domain', 'complexity', 'learning_level', 'status'),
#     order_by='quality_score'
# )
```

### Unified Search API

For cross-domain search combining all capabilities, use `SearchRouter.advanced_search()`.
**SearchRequest is THE canonical request model** (One Path Forward, January 2026).

```python
from core.models.search import SearchRouter
from core.models.search_request import SearchRequest

request = SearchRequest(
    query_text="machine learning",
    entity_types=[EntityType.KU, EntityType.TASK],
    connected_to_uid="ku.python-basics",
    connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
    tags_contain=["python"],
    tags_match_all=False,
)
result = await router.advanced_search(request)
```

**REST API:** `POST /api/search/unified`

## Intelligent Search (January 2026)

All 6 Activity domain search services implement `intelligent_search()` for **NLP-based query parsing**. This method extracts semantic filters from natural language queries.

### How It Works

1. **Query Parsing**: Uses `SearchQueryParser` to extract Priority, ActivityStatus, and Domain from the query
2. **Domain-Specific Keywords**: Each service recognizes keywords specific to its domain
3. **Filter Building**: Extracted keywords become filters for the backend query
4. **Fallback**: If no filters extracted, falls back to text search

### Usage

```python
# Natural language search with automatic filter extraction
result = await tasks_service.search.intelligent_search("urgent tech tasks in progress")
tasks, parsed = result.value

print(f"Found {len(tasks)} tasks")
print(f"Filters: {parsed.to_filter_summary()}")  # "priority: critical; status: in_progress"
```

### Domain-Specific Keywords

| Service | Keywords Extracted | Examples |
|---------|-------------------|----------|
| **TasksSearchService** | Priority, Status | "urgent" → CRITICAL, "in progress" → IN_PROGRESS |
| **GoalsSearchService** | Timeframe, GoalStatus | "weekly" → WEEKLY, "achieved" → ACHIEVED |
| **HabitSearchService** | Frequency, Streak State | "daily" → DAILY, "at risk" → streak filtering |
| **EventsSearchService** | Date Range, Recurrence | "this week" → date range, "recurring" → filter |
| **ChoicesSearchService** | Urgency, Decision State | "urgent" → CRITICAL, "pending" → PENDING status |
| **PrinciplesSearchService** | Strength, Category, State | "core" → CORE strength, "health" → HEALTH category |

### Return Value

```python
async def intelligent_search(
    self, query: str, user_uid: str | None = None, limit: int = 50
) -> Result[tuple[list[Entity], ParsedSearchQuery]]:
    """Returns (entities, parsed_query) tuple."""
```

The `ParsedSearchQuery` contains:
- `raw_query`: Original query string
- `text_query`: Query with filter keywords removed
- `priorities`: List of extracted Priority enums
- `statuses`: List of extracted ActivityStatus enums
- `domains`: List of extracted Domain enums
- `to_filter_summary()`: Human-readable summary of filters

### Implementation Pattern

Each service follows the same pattern with domain-specific keyword mappings:

```python
@with_error_handling("intelligent_search", error_type="database")
async def intelligent_search(
    self, query: str, user_uid: str | None = None, limit: int = 50
) -> Result[tuple[list[Task], ParsedSearchQuery]]:
    # 1. Parse query with shared parser
    parser = SearchQueryParser()
    parsed = parser.parse(query)
    query_lower = query.lower()

    # 2. Build filters from parsed + domain-specific keywords
    filters: dict[str, object] = {}

    # Domain-specific keyword extraction
    if "urgent" in query_lower:
        filters["priority"] = Priority.CRITICAL.value
    # ... more keywords

    # 3. Execute search
    if filters:
        result = await self.backend.find_by(limit=limit, **filters)
    else:
        result = await self.search(parsed.text_query, limit=limit)

    # 4. Return tuple with parsed query for caller insight
    return Result.ok((entities, parsed))
```

## Domain-Specific Extensions

Each SearchService extends the protocol with domain-appropriate methods. Methods marked "inherited" come from BaseService; others are domain-specific implementations.

### GoalsSearchService
```python
class GoalsSearchService(BaseService[GoalsOperations, Goal]):
    _dto_class = GoalDTO
    _model_class = Goal
    _category_field = "domain"  # Goals use 'domain' for categorization
    _supports_user_progress = True  # Enable progress tracking
    _prerequisite_relationships = [REQUIRES_KNOWLEDGE, DEPENDS_ON_GOAL]
    _enables_relationships = [ENABLES_GOAL]

    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
    # get_by_category(), list_categories(), get_by_relationship(),
    # get_prerequisites(), get_enables(), get_user_progress(), get_user_curriculum()

    # Goal-specific methods (must implement)
    async def get_prioritized(self, user_context: UserContext, limit: int = 10) -> Result[list[Goal]]: ...
    async def get_due_soon(self, days_ahead: int = 7) -> Result[list[Goal]]: ...
    async def get_overdue(self, limit: int = 100) -> Result[list[Goal]]: ...
    async def get_by_timeframe(self, timeframe: GoalTimeframe) -> Result[list[Goal]]: ...
    async def get_needing_habits(self, user_context: UserContext) -> Result[list[Goal]]: ...
    async def get_blocked_by_knowledge(self, user_context: UserContext) -> Result[list[Goal]]: ...

    # Intelligent search (January 2026) - extracts timeframe/status keywords
    async def intelligent_search(self, query: str, user_uid: str | None, limit: int) -> Result[tuple[list[Goal], ParsedSearchQuery]]: ...
```

### HabitSearchService
```python
class HabitSearchService(BaseService[HabitsOperations, Habit]):
    _dto_class = HabitDTO
    _model_class = Habit
    _supports_user_progress = True  # Enable progress tracking
    _prerequisite_relationships = [REQUIRES_PREREQUISITE_HABIT]
    _enables_relationships = [ENABLES_HABIT]

    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
    # get_by_category(), list_categories(), get_by_relationship(),
    # get_prerequisites(), get_enables(), get_user_progress(), get_user_curriculum()

    # Habit-specific methods
    async def get_prioritized(self, user_context: UserContext, limit: int = 10) -> Result[list[Habit]]: ...
    async def get_by_frequency(self, frequency: HabitFrequency) -> Result[list[Habit]]: ...
    async def get_needing_attention(self, streak_threshold: int = 3) -> Result[list[Habit]]: ...
    async def get_at_risk(self, user_context: UserContext) -> Result[list[Habit]]: ...
    async def get_due_today(self, user_uid: str) -> Result[list[Habit]]: ...

    # Intelligent search (January 2026) - extracts frequency/streak keywords
    async def intelligent_search(self, query: str, user_uid: str | None, limit: int) -> Result[tuple[list[Habit], ParsedSearchQuery]]: ...
```

### EventsSearchService
```python
class EventsSearchService(BaseService[EventsOperations, Event]):
    _dto_class = EventDTO
    _model_class = Event
    _search_order_by = "event_date"  # Events ordered by event date
    _supports_user_progress = True  # Enable progress tracking
    _prerequisite_relationships = [REQUIRES_KNOWLEDGE]
    _enables_relationships = [REINFORCES_HABIT]

    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
    # get_by_category(), list_categories(), get_by_relationship(),
    # get_prerequisites(), get_enables(), get_user_progress(), get_user_curriculum()

    # Event-specific methods
    async def get_prioritized(self, user_context: UserContext, limit: int = 10) -> Result[list[Event]]: ...
    async def get_in_range(self, start: date, end: date) -> Result[list[Event]]: ...
    async def get_recurring(self) -> Result[list[Event]]: ...
    async def get_for_goal(self, goal_uid: str) -> Result[list[Event]]: ...
    async def get_conflicting(self, event_uid: str) -> Result[list[Event]]: ...

    # Intelligent search (January 2026) - extracts date/recurrence keywords
    async def intelligent_search(self, query: str, user_uid: str | None, limit: int) -> Result[tuple[list[Event], ParsedSearchQuery]]: ...
```

### ChoicesSearchService
```python
class ChoicesSearchService(BaseService[ChoicesOperations, Choice]):
    _dto_class = ChoiceDTO
    _model_class = Choice
    _supports_user_progress = True  # Enable progress tracking
    _prerequisite_relationships = [REQUIRES_KNOWLEDGE_FOR_DECISION]
    _enables_relationships = [AFFECTS_GOAL, OPENS_LEARNING_PATH]

    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
    # get_by_category(), list_categories(), get_by_relationship(),
    # get_prerequisites(), get_enables(), get_user_progress(), get_user_curriculum()

    # Choice-specific methods
    async def get_prioritized(self, user_context: UserContext, limit: int = 10) -> Result[list[Choice]]: ...
    async def get_pending(self, user_uid: str) -> Result[list[Choice]]: ...
    async def get_by_urgency(self, urgency: str) -> Result[list[Choice]]: ...
    async def get_affecting_goal(self, goal_uid: str) -> Result[list[Choice]]: ...
    async def get_needing_decision(self, deadline_days: int = 7) -> Result[list[Choice]]: ...

    # Intelligent search (January 2026) - extracts urgency/decision state keywords
    async def intelligent_search(self, query: str, user_uid: str | None, limit: int) -> Result[tuple[list[Choice], ParsedSearchQuery]]: ...
```

### TasksSearchService
```python
class TasksSearchService(BaseService[TasksOperations, Task]):
    _dto_class = TaskDTO
    _model_class = Task
    _supports_user_progress = True  # Enable progress tracking
    _prerequisite_relationships = [BLOCKED_BY, REQUIRES_TASK]
    _enables_relationships = [BLOCKS, ENABLES_TASK]

    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
    # get_by_category(), list_categories(), get_by_relationship(),
    # get_prerequisites(), get_enables(), get_user_progress(), get_user_curriculum()

    # Task-specific methods
    async def get_tasks_for_goal(self, goal_uid: str) -> Result[list[Task]]: ...
    async def get_tasks_for_habit(self, habit_uid: str) -> Result[list[Task]]: ...
    async def get_curriculum_tasks(self) -> Result[list[Task]]: ...
    async def get_learning_relevant_tasks(self, learning_position: LpPosition) -> Result[list[Task]]: ...

    # Intelligent search (January 2026) - extracts priority/status keywords
    async def intelligent_search(self, query: str, user_uid: str | None, limit: int) -> Result[tuple[list[Task], ParsedSearchQuery]]: ...
```

### PrinciplesSearchService (Custom Overrides)
```python
class PrinciplesSearchService(BaseService[PrinciplesOperations, Principle]):
    _dto_class = PrincipleDTO
    _model_class = Principle
    _search_fields = ["name", "statement", "description", "why_important"]
    _supports_user_progress = True  # Enable progress tracking
    _prerequisite_relationships = [GROUNDED_IN_KNOWLEDGE]
    _enables_relationships = [GUIDES_GOAL, GUIDES_CHOICE, INSPIRES_HABIT]

    # OVERRIDES inherited methods (Principles use different data model)
    async def get_by_status(self, status: str, ...) -> ...:  # Converts to is_active boolean
    async def get_by_domain(self, domain: Domain, ...) -> ...:  # Maps to PrincipleCategory
    async def get_by_category(self, category: PrincipleCategory | str, ...) -> ...:  # Typed for PrincipleCategory
    async def list_categories(self) -> ...:  # Returns PrincipleCategory enum values

    # Principle-specific methods
    async def get_prioritized(self, user_context: UserContext, limit: int = 10) -> Result[list[Principle]]: ...
    async def get_guiding_goals(self, principle_uid: str) -> Result[list[str]]: ...
    async def get_active_principles(self, user_uid: str) -> Result[list[Principle]]: ...

    # Intelligent search (January 2026) - extracts strength/category/state keywords
    async def intelligent_search(self, query: str, user_uid: str | None, limit: int) -> Result[tuple[list[Principle], ParsedSearchQuery]]: ...
```

## Service Composition

SearchServices are sub-services within the domain facade:

```python
class GoalsService(BaseService[GoalsOperations, Goal]):
    def __init__(self, backend: GoalsOperations, ...):
        super().__init__(backend, "goals")

        # Sub-services
        self.core = GoalCoreService(backend=backend, ...)
        self.search = GoalSearchService(backend=backend)  # SearchService
        self.progress = GoalProgressService(...)
        self.relationships = GoalRelationshipService(...)
        # ... other sub-services

    # Delegate search methods to search sub-service
    async def search_goals(self, query: str, limit: int = 50) -> Result[list[Goal]]:
        return await self.search.search(query, limit)

    async def get_goals_due_soon(self, days_ahead: int = 7) -> Result[list[Goal]]:
        return await self.search.get_due_soon(days_ahead)
```

## Integration with UserContext and Askesis

The SearchService pattern is fundamental to SKUEL's intelligence layer:

1. **UserContext Building**: Search services provide data that populates UserContext fields
2. **Askesis Recommendations**: Askesis uses search services to find relevant entities
3. **Cross-Domain Discovery**: Unified search interfaces enable cross-domain queries

```
User Request
     │
     ▼
┌─────────────┐
│   Askesis   │ ◄── Uses SearchServices to find relevant entities
└─────────────┘
     │
     ▼
┌─────────────┐
│ UserContext │ ◄── ~240 fields populated via SearchService queries
└─────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│              DomainSearchOperations[T]                  │
├─────────────────────────────────────────────────────────┤
│ TaskSearchService │ GoalSearchService │ HabitSearch... │
└─────────────────────────────────────────────────────────┘
```

## Implementation Guidelines

### 1. Naming Convention
- Service name: `{Entity}SearchService` (singular entity name)
- File name: `{entity}_search_service.py` (lowercase with underscores)

### 2. Inheritance
```python
class GoalSearchService(BaseService[GoalsOperations, Goal]):
    """Goal search and discovery operations."""

    def __init__(self, backend: GoalsOperations) -> None:
        super().__init__(backend, "goals.search")
```

### 3. Error Handling
Always use `Result[T]` pattern:
```python
async def search(self, query: str, limit: int = 50) -> Result[list[Goal]]:
    try:
        # Implementation
        return Result.ok(goals)
    except Exception as e:
        self.logger.error(f"Search failed: {e}")
        return Result.fail(Errors.database(operation="search", message=str(e)))
```

### 4. Logging
Use structured logging with appropriate levels:
```python
self.logger.debug(f"Found {len(results)} goals matching '{query}'")
self.logger.info(f"Prioritized {len(prioritized)} goals for user {user_uid}")
```

## Migration Path

When extracting search from CoreService to SearchService:

1. Create new `{entity}_search_service.py` file
2. Move search methods from CoreService to SearchService
3. Update domain facade to initialize SearchService
4. Update facade to delegate search calls to SearchService
5. Keep facade method signatures unchanged (backward compatible)

## Search Models

**For complete SearchRequest and SearchResponse documentation, see:** [SEARCH_MODELS.md](../reference/models/SEARCH_MODELS.md)

The `SearchRequest` model provides unified search across all domains with:
- Optional query text (can do filter-only search)
- Core facets (domain, sel_category, learning_level, etc.)
- Relationship-based filters (graph-aware search)
- Pagination support

The `SearchResponse` model returns:
- Polymorphic results (based on domain)
- Facet counts for UI filters
- Capacity warnings from UserContext
- Pagination metadata

## SearchRouter Integration (One Path Forward - January 2026)

All external search access now goes through **SearchRouter**. Domain SearchServices are invoked by SearchRouter:

```
External Callers:
├── /search routes      → SearchRouter.faceted_search()
├── /api/search/unified → SearchRouter.advanced_search()
└── GraphQL queries     → SearchRouter.faceted_search()

SearchRouter (uses _GRAPH_AWARE_DOMAINS):
├── Graph-Aware Domains → domain.search.graph_aware_faceted_search()
│   ├── Activity: tasks, goals, habits, events, choices, principles
│   └── Curriculum: ku (January 2026 - unified with Activity Domains)
└── Simple Search → domain.search.search()
    └── ls, lp, moc
```

**graph_aware_faceted_search()** is implemented by Activity Domain SearchServices + KuSearchService:
- User ownership filter for Activity Domains (OWNS relationship)
- NO ownership filter for KU (shared content)
- Property filters from SearchRequest
- **SearchRequest graph patterns** (`ready_to_learn`, `supports_goals`, etc.) - now applied to KU
- Graph pattern enrichment with domain-specific relationships
- `_graph_context` field with relationship summaries

**BaseService Configuration (January 2026):**
```python
# Activity Domains inherit from BaseService with these defaults
_graph_enrichment_patterns: ClassVar[list[tuple[str, str, str]]] = []
_user_ownership_relationship: ClassVar[str | None] = "OWNS"  # None for shared content
```

## Curriculum Domain Search Services (January 2026)

Curriculum domains (LS, LP, MOC) use **standalone search services** that don't inherit from BaseService:

### Why Standalone Pattern?

- Curriculum domains are **shared content** (no user ownership)
- Different search needs than Activity Domains
- Simpler dependency graph
- Following MocSearchService precedent

### LsSearchService

**Location:** `/core/services/ls/ls_search_service.py`

```python
class LsSearchService:
    """Standalone search service for Learning Steps."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def search(self, query: str, limit: int = 50) -> Result[list[Ls]]: ...
    async def search_filtered(self, filters: LsSearchFilters) -> Result[list[Ls]]: ...
    async def intelligent_search(self, query: str, limit: int) -> Result[tuple[list[Ls], ParsedSearchQuery]]: ...
    async def get_by_domain(self, domain: Domain, limit: int) -> Result[list[Ls]]: ...
    async def get_by_status(self, status: StepStatus, limit: int) -> Result[list[Ls]]: ...
    async def get_standalone_steps(self, limit: int) -> Result[list[Ls]]: ...
    async def get_for_learning_path(self, path_uid: str, limit: int) -> Result[list[Ls]]: ...
    async def get_prioritized(self, user_uid: str, context: UserContext, limit: int) -> Result[list[Ls]]: ...
```

**LsSearchFilters:**
- `domain`, `difficulty`, `status`, `priority`, `learning_path_uid`
- `is_standalone`, `is_completed`
- `has_tag`, `has_any_tags`

### LpSearchService

**Location:** `/core/services/lp/lp_search_service.py`

```python
class LpSearchService:
    """Standalone search service for Learning Paths."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def search(self, query: str, limit: int = 50) -> Result[list[Lp]]: ...
    async def search_filtered(self, filters: LpSearchFilters) -> Result[list[Lp]]: ...
    async def intelligent_search(self, query: str, limit: int) -> Result[tuple[list[Lp], ParsedSearchQuery]]: ...
    async def get_by_domain(self, domain: Domain, limit: int) -> Result[list[Lp]]: ...
    async def get_by_path_type(self, path_type: LpType, limit: int) -> Result[list[Lp]]: ...
    async def get_for_user(self, user_uid: str, limit: int) -> Result[list[Lp]]: ...
    async def get_aligned_with_goal(self, goal_uid: str, limit: int) -> Result[list[Lp]]: ...
    async def get_prioritized(self, user_uid: str, context: UserContext, limit: int) -> Result[list[Lp]]: ...
```

**LpSearchFilters:**
- `domain`, `path_type`, `difficulty`, `created_by`
- `min_steps`, `max_steps`
- `is_complete`, `has_outcomes`

### Service Wiring

Curriculum services expose search via `.search` property like Activity Domains:

```python
# LsService facade
class LsService:
    def __init__(self, driver, event_bus=None):
        self.core = LsCoreService(driver=driver, event_bus=event_bus)
        self.relationship = LsRelationshipService(driver=driver)
        self.search = LsSearchService(driver=driver)  # Search sub-service

# LpService facade
class LpService:
    def __init__(self, driver, ls_service, ...):
        self.core = LpCoreService(driver=driver, ...)
        self.search = LpSearchService(driver=driver)  # Search sub-service
        # ... other sub-services
```

## See Also

### Search Documentation

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **[SEARCH_SERVICE_METHODS.md](../reference/SEARCH_SERVICE_METHODS.md)** | **Method catalog** | Complete method reference for all 10 search services |
| **[SEARCH_MODELS.md](../reference/models/SEARCH_MODELS.md)** | **Model reference** | Complete SearchRequest/SearchResponse documentation |
| [SEARCH_ARCHITECTURE.md](../architecture/SEARCH_ARCHITECTURE.md) | Search architecture | SearchRouter + domain services overview |
| [search-one-path-forward.md](~/.claude/plans/search-one-path-forward.md) | Architecture plan | One Path Forward consolidation (January 2026) |

### Related Documentation

- `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` - Domain overview
- `/core/services/protocols/search_protocols.py` - Protocol definition
- `/core/services/base_service.py` - BaseService with generic filter methods
- `/core/services/search/config.py` - Centralized search field configuration
- `/core/models/search/search_router.py` - THE search orchestrator (One Path Forward)
- `/core/services/goals/goal_search_service.py` - Reference implementation (uses inherited methods)
- `/core/services/principles/principle_search_service.py` - Example of custom overrides
- `/core/services/ls/ls_search_service.py` - Learning Steps search (standalone pattern)
- `/core/services/lp/lp_search_service.py` - Learning Paths search (standalone pattern)
- `/core/services/moc/moc_search_service.py` - MOC search (standalone pattern template)

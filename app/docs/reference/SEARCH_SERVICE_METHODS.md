---
related_skills:
- skuel-search-architecture
---
# Search Service Method Reference
*Last updated: 2026-06-11*

Complete catalog of methods across all 9 domain search services. All services extend `BaseService[Backend, Model]` following the unified architecture (ADR-023).

---

## Quick Reference Matrix

**Skill:** [@skuel-search-architecture](../../.claude/skills/skuel-search-architecture/SKILL.md)

Legend: **I** = Inherited from BaseService | **O** = Override | **D** = Domain-specific

| Method | Tasks | Goals | Habits | Events | Choices | Principles | KU | PS | LP |
|--------|:-----:|:-----:|:------:|:------:|:-------:|:----------:|:--:|:--:|:--:|
| **Inherited (BaseService)** |
| `search()` | I | I | I | I | I | I | I | I | I |
| `get_by_status()` | I | I | I | I | I | O | I | I | I |
| `get_by_category()` | I | I | I | I | I | I | I | I | I |
| `list_categories()` | I | I | I | I | I | O | I | I | I |
| `get_by_relationship()` | I | I | I | I | I | I | I | I | I |
| `graph_aware_faceted_search()` | I | I | I | I | I | I | I | I | I |
| `search_by_tags()` | I | I | I | I | I | I | I | I | I |
| `get_prerequisites()` | I | I | I | I | I | I | I | I | I |
| `get_enables()` | I | I | I | I | I | I | I | I | I |
| `get_user_progress()` | I | I | I | I | I | I | I | I | I |
| **Protocol (DomainSearchOperations)** |
| `get_prioritized()` | D | D | D | D | D | D | D | D | D |
| `get_upcoming()` | I | I | O | I | I | O | - | - | - |
| `get_overdue()` | I | I | O | I | I | O | - | - | - |
| `get_active()` | I | I | O | I | I | O | - | - | - |
| **Domain-Specific** |
| `get_blocking_tasks()` | D | - | - | - | - | - | - | - | - |
| `get_blocked_tasks()` | D | - | - | - | - | - | - | - | - |
| `get_by_priority()` | D | D | - | - | - | - | - | - | - |
| `get_pending()` | D | - | - | - | D | - | - | - | - |
| `get_by_progress()` | - | D | - | - | - | - | - | - | - |
| `get_by_frequency()` | - | - | D | - | - | - | - | - | - |
| `get_by_streak_status()` | - | - | D | - | - | - | - | - | - |
| `get_by_date_range()` | - | - | - | D | - | - | - | - | - |
| `search_by_alias()` | - | - | - | - | - | - | D | - | - |
| `get_standalone_steps()` | - | - | - | - | - | - | - | D | - |
| `get_aligned_with_goal()` | - | - | - | - | - | - | - | - | D |

---

## Inherited Methods (from BaseService)

All search services inherit these methods from `BaseService[Backend, Model]`. Configure behavior via class attributes.

### Core Search Methods

#### `search(query: str, user_uid: UserUID | None, limit: int = 50) -> Result[list[Model]]`
Text search across configured `_search_fields`. Orders by `_search_order_by`.

```python
result = await tasks_search.search("urgent deadline", user_uid="user.123")
```

#### `graph_aware_faceted_search(request: SearchRequest) -> Result[SearchResponse]`
**THE unified search method.** Combines text search, graph traversal, and faceted filtering.

```python
request = SearchRequest(
    query_text="python",
    domain=Domain.KNOWLEDGE,
    ready_to_learn=True,   # relationship filters are first-class bool fields
    supports_goals=True,
    user_uid="user.123",
)
result = await ku_search.graph_aware_faceted_search(request, user_uid="user.123")
```

> Relationship filters are boolean fields on `SearchRequest` (not a `graph_patterns` list). The service captures the active set via `request.to_relationship_filters()` and the backend authors the Cypher below the boundary (ADR-044).

#### `search_by_tags(tags: list[str], match_all: bool = False, user_uid: UserUID | None = None) -> Result[list[Model]]`
Array field search with AND/OR semantics.

```python
# Find items with ANY of these tags (OR)
result = await ku_search.search_by_tags(["python", "ml"], match_all=False)

# Find items with ALL tags (AND)
result = await ku_search.search_by_tags(["python", "ml"], match_all=True)
```

### Filter Methods

#### `get_by_status(status: str, user_uid: UserUID | None = None) -> Result[list[Model]]`
Filter by status field. Activity domains use `EntityStatus` enum.

```python
result = await tasks_search.get_by_status("active", user_uid="user.123")
```

#### `get_for_user_filtered(user_uid: UserUID, status_filter: str = "all") -> Result[list[Model]]`
Fetch a user's entities with a domain-configured status filter. The filter
vocabulary lives in `DomainConfig.status_filters` (filter-name → extra
`find_by` kwargs); `"all"` or an unconfigured name applies no status
constraint. Domains without `status_filters` (Principles) always return
every entity for the user.

```python
result = await tasks_core.get_for_user_filtered("user.123", "active")
# Tasks' "active" is configured as status__not_in=["completed"]
```

#### `get_by_category(category: str, user_uid: UserUID | None = None) -> Result[list[Model]]`
Filter by the DomainConfig `category_field` (varies by domain — e.g. Goals `domain`, Habits `habit_category`).

```python
result = await principles_search.get_by_category("core_values", user_uid="user.123")
```

#### `list_categories(user_uid: UserUID | None = None) -> Result[list[str]]`
Get distinct values of the DomainConfig `category_field`.

```python
result = await habits_search.list_categories(user_uid="user.123")
# Returns: ["morning", "evening", "weekly", ...]
```

### Graph Traversal Methods

#### `get_by_relationship(related_uid: str, relationship: RelationshipName, direction: Direction) -> Result[list[Model]]`
Find entities connected via specific relationship.

```python
# Get tasks that fulfill a goal
result = await tasks_search.get_by_relationship(
    related_uid="goal.learn-python",
    relationship=RelationshipName.FULFILLS_GOAL,
    direction="outgoing"
)
```

#### `get_prerequisites(uid: str) -> Result[list[Model]]`
Get entities this depends on (via `_prerequisite_relationships`).

```python
result = await ku_search.get_prerequisites("ku.advanced-python")
# Returns: [KU(uid="ku.python-basics"), KU(uid="ku.functions"), ...]
```

#### `get_enables(uid: str) -> Result[list[Model]]`
Get entities this unlocks (via `_enables_relationships`).

```python
result = await ku_search.get_enables("ku.python-basics")
# Returns: [KU(uid="ku.oop"), KU(uid="ku.decorators"), ...]
```

---

## Class Attribute Configuration

Configure inherited behavior via class attributes:

```python
class GoalsSearchService(BaseService["GoalsOperations", Goal]):
    # Required
    _dto_class = GoalDTO
    _model_class = Goal

    # Search configuration
    _search_fields: ClassVar[list[str]] = ["title", "description"]
    _search_order_by: str = "created_at"

    # Categorization: category_field comes from DomainConfig (e.g. "domain",
    # "habit_category") — the raw _category_field class attribute was deleted

    # Content (for curriculum)
    _content_field: str = "content"

    # User ownership
    _user_ownership_relationship: ClassVar[str | None] = "OWNS"  # None for shared content

    # Graph traversal
    _prerequisite_relationships: ClassVar[list[str]] = ["REQUIRES"]
    _enables_relationships: ClassVar[list[str]] = ["ENABLES"]

    # Graph enrichment (relationship_type, target_label, context_key, direction)
    _graph_enrichment_patterns: ClassVar[list[tuple]] = [
        ("FULFILLS_GOAL", "Task", "contributing_tasks", "incoming"),
        ("ALIGNED_WITH_PRINCIPLE", "Principle", "guiding_principles", "outgoing"),
    ]
```

---

## Activity Domain Search Services

### TasksSearchService

**File:** `core/services/tasks/tasks_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description"]
category_field = "category"  # DomainConfig (default)
_graph_enrichment_patterns = [
    ("FULFILLS_GOAL", "Goal", "parent_goals", "outgoing"),
    ("APPLIES_KNOWLEDGE", "Ku", "applied_knowledge", "outgoing"),
    ("BLOCKED_BY", "Task", "blockers", "outgoing"),
    ("BLOCKS", "Task", "blocking", "incoming"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_blocking_tasks` | `(uid: str, user_uid: UserUID) -> Result[list[Task]]` | Tasks blocking this task |
| `get_blocked_tasks` | `(uid: str, user_uid: UserUID) -> Result[list[Task]]` | Tasks blocked by this task |
| `get_by_priority` | `(priority: Priority, user_uid: UserUID) -> Result[list[Task]]` | Filter by priority level |
| `get_pending` | `(user_uid: UserUID) -> Result[list[Task]]` | Tasks with pending status |
| `search_by_parent_goal` | `(goal_uid: str, user_uid: UserUID) -> Result[list[Task]]` | Tasks fulfilling a goal |
| `get_prioritized` | `(user_uid: UserUID, limit: int = 10) -> Result[list[Task]]` | Smart prioritization |

---

### GoalsSearchService

**File:** `core/services/goals/goals_search_service.py`

**Configuration** (via `create_activity_domain_config("goals", ...)` — registry-derived):
```python
search_fields = ("title", "description")
category_field = "domain"  # Goals use the 'domain' field for categorization
date_field = "target_date"
# graph_enrichment_patterns come from the relationship registry (GOAPS_CONFIG):
# REQUIRES_KNOWLEDGE → required_knowledge, GUIDED_BY_PRINCIPLE → aligned_principles,
# SUBGOAL_OF → parent_goal / sub_goals, SUPPORTS_GOAL → contributing_habits +
# essential/critical/optional_habits (essentiality-filtered), FULFILLS_GOAL →
# contributing_tasks / related_goals, SERVES_LIFE_PATH → life_path, ...
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_prioritized` | `(user_context: UserContext, limit: int = 10) -> Result[list[Goal]]` | Context-aware prioritization via `score_goal()` |

Everything else (`search()`, `get_by_status()`, `get_by_category()`,
`list_user_categories()`, `get_by_relationship()`, `get_upcoming()`, `get_overdue()`,
`get_active()`) is inherited from `BaseService` via `DomainConfig`. The former
goals-specific extensions (`get_by_timeframe`, `get_needing_habits`,
`get_blocked_by_knowledge`, `get_sub_goals`) were deleted in the 2026-06 dead-code
campaign — zero callers; live equivalents are `GoalsLearningService`
(`get_goals_needing_habits` / `get_goals_blocked_by_knowledge`), `PrerequisiteChecker`,
and the core-service hierarchy methods.

---

### HabitsSearchService

**File:** `core/services/habits/habits_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "cue", "routine", "reward"]
category_field = "habit_category"  # DomainConfig
_graph_enrichment_patterns = [
    ("SUPPORTS_GOAL", "Goal", "supported_goals", "outgoing"),
    ("REINFORCES_KNOWLEDGE", "Ku", "reinforced_knowledge", "outgoing"),
    ("INSPIRED_BY_PRINCIPLE", "Principle", "inspiring_principles", "outgoing"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_by_frequency` | `(frequency: str, user_uid: UserUID) -> Result[list[Habit]]` | Filter by frequency (daily/weekly/etc) |
| `get_by_streak_status` | `(min_streak: int, user_uid: UserUID) -> Result[list[Habit]]` | Filter by streak length |
| `get_habits_needing_attention` | `(user_uid: UserUID) -> Result[list[Habit]]` | Broken streaks or declining |
| `get_user_due_today` | `(user_uid: UserUID) -> Result[list[Habit]]` | Habits due today (frequency-window logic) |
| `get_habit_chain_candidates` | `(habit_uid: str, user_uid: UserUID) -> Result[list[Habit]]` | Potential habit stacking |
| `get_knowledge_reinforcement_opportunities` | `(user_uid: UserUID) -> Result[list[dict]]` | KU-habit connection opportunities |
| `get_prioritized` | `(user_uid: UserUID, limit: int = 10) -> Result[list[Habit]]` | Smart prioritization |

---

### EventsSearchService

**File:** `core/services/events/events_search_service.py`

**Configuration** (from `create_activity_domain_config(domain_name="events", ...)`):
```python
search_fields = ("title", "description")
category_field = "category"  # DomainConfig (default)
# graph_enrichment_patterns generated from EVENTS_CONFIG — key edges:
#   APPLIES_KNOWLEDGE → applied_knowledge, CONTRIBUTES_TO_GOAL → supported_goals,
#   REINFORCES_HABIT → reinforced_habits, CELEBRATES_GOAL → celebrated_goals,
#   EXECUTES_TASK → executed_tasks, CONFLICTS_WITH → conflicting_events, ...
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_prioritized` | `(user_context: UserContext, limit: int = 10) -> Result[list[Event]]` | Smart prioritization (next-2-weeks window) |
| `get_in_range` | `(start_date: date, end_date: date, user_uid, limit) -> Result[list[Event]]` | Events in date range |
| `get_recurring` | `(user_uid: UserUID, limit: int = 100) -> Result[list[Event]]` | Recurring events only |
| `get_for_goal` | `(goal_uid: str, user_uid) -> Result[list[Event]]` | Events supporting a goal |
| `get_conflicting` | `(event_uid: str) -> Result[list[Event]]` | Time-overlap conflicts (PLANNED — staged conflict surface) |
| `get_for_habit` | `(habit_uid: str, user_uid) -> Result[list[Event]]` | Events reinforcing a habit |
| `get_calendar_events` | `(user_uid, start_date, end_date, limit) -> Result[list[Event]]` | Calendar window query |

Deleted in the 2026-06 events dead-code campaign: `get_by_type` (superseded by
`find_events(filters={"event_type": ...})`) and `get_history` (superseded by the
status-filtered list path, `get_for_user_filtered`).

---

### ChoicesSearchService

**File:** `core/services/choices/choices_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "context"]
category_field = "category"  # DomainConfig (default)
_graph_enrichment_patterns = [
    ("AFFECTS_GOAL", "Goal", "affected_goals", "outgoing"),
    ("ALIGNED_WITH_PRINCIPLE", "Principle", "guiding_principles", "outgoing"),
    ("REQUIRES_KNOWLEDGE", "Ku", "required_knowledge", "outgoing"),
    ("IMPACTS_HABIT", "Habit", "impacted_habits", "outgoing"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_pending` | `(user_uid: UserUID) -> Result[list[Choice]]` | Undecided choices |
| `get_needing_decision` | `(user_uid: UserUID, days: int = 7) -> Result[list[Choice]]` | Choices with deadline approaching |
| `get_prioritized` | `(user_uid: UserUID, limit: int = 10) -> Result[list[Choice]]` | Smart prioritization |

---

### PrinciplesSearchService

**File:** `core/services/principles/principles_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "rationale"]
category_field = "principle_category"  # DomainConfig
_graph_enrichment_patterns = [
    ("GUIDES_GOAL", "Goal", "guided_goals", "outgoing"),
    ("INSPIRES_HABIT", "Habit", "inspired_habits", "outgoing"),
    ("GUIDES_CHOICE", "Choice", "guided_choices", "outgoing"),
    ("RELATED_TO", "Principle", "related_principles", "both"),
]
```

**Overridden Methods:**

| Method | Reason for Override |
|--------|---------------------|
| `get_by_status` | Principles use `is_active: bool` instead of `status: str` |
| `list_categories` | Custom category enumeration |

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_by_category` | `(category: str, user_uid: UserUID) -> Result[list[Principle]]` | Filter by category |
| `get_for_goal` | `(goal_uid: str, user_uid: UserUID) -> Result[list[Principle]]` | Principles aligned with goal |
| `get_for_habit` | `(habit_uid: str, user_uid: UserUID) -> Result[list[Principle]]` | Principles inspiring habit |
| `get_needing_review` | `(user_uid: UserUID, days: int = 90) -> Result[list[Principle]]` | Principles not reviewed recently (also drives the overridden `get_overdue`) |
| `get_related_principles` | `(principle_uid: str, user_uid: UserUID) -> Result[list[Principle]]` | Related principles |
| `get_prioritized` | `(user_uid: UserUID, limit: int = 10) -> Result[list[Principle]]` | Smart prioritization |

---

## Curriculum Domain Search Services

### KuSearchService

**File:** `core/services/ku/ku_search_service.py`

**Configuration (from runtime `create_curriculum_domain_config`):**
```python
search_fields = ("title", "description", "summary")
category_field = "nous"  # NOUS topic membership (array — `has` semantics)
# user_ownership_relationship = None (shared content)
# graph_enrichment_patterns come from the relationship registry (KU_CONFIG)
```

Topic filtering rides the inherited category machinery: `get_by_category("body")`
matches array membership via the `has` operator, and `list_all_categories()`
UNWINDs the `nous` arrays to per-topic values (the /search dropdown source via
`KuService.list_nous_topics()`).

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `search_by_alias` | `(alias: str, limit: int = 25) -> Result[list[Ku]]` | Match against Ku aliases |

> Chunk-level vector search lives on `Neo4jVectorSearchService.find_similar_chunks_by_text()`
> — see `docs/guides/ASKESIS_SEARCH_ARCHITECTURE.md`.

---

### PsSearchService

**File:** `core/services/ps/ps_search_service.py`

**Configuration (from runtime `create_curriculum_domain_config`):**
```python
search_fields = ("title", "intent", "description")
content_field = "description"
# user_ownership_relationship = None (shared content)
# graph_enrichment_patterns come from the relationship registry (PS config)
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_standalone_steps` | `(limit: int = 50) -> Result[list[PathStep]]` | Steps not in any path |
| `get_prioritized` | `(user_uid: UserUID, context: UserContext, limit: int = 20) -> Result[list[PathStep]]` | Ready-to-learn prioritization |

---

### LpSearchService

**File:** `core/services/lp/lp_search_service.py`

**Configuration (from runtime `create_curriculum_domain_config`):**
```python
search_fields = ("title", "description")  # LP: name→title, goal→description
content_field = "description"
# user_ownership_relationship = None (shared content)
# graph_enrichment_patterns come from the relationship registry (LP config)
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_aligned_with_goal` | `(goal_uid: str, limit: int = 50) -> Result[list[LearningPath]]` | Paths aligned with goal (staged, PLANNED) |
| `get_by_knowledge` | `(ku_uid: str, limit: int = 20) -> Result[list[LearningPath]]` | Paths teaching a Ku (staged, PLANNED) |
| `get_prioritized` | `(user_uid: UserUID, context: UserContext, limit: int = 20) -> Result[list[LearningPath]]` | Recommended paths |

---

## Common Queries Cookbook

### Find tasks blocking progress on a goal

```python
# Get all tasks for a goal, then find blockers
tasks_result = await tasks_search.search_by_parent_goal("goal.learn-python", "user.123")
if tasks_result.is_ok:
    for task in tasks_result.value:
        blockers = await tasks_search.get_blocking_tasks(task.uid, "user.123")
```

### Find knowledge gaps for a learning path

```python
# Get path steps, check user progress
steps_result = await lp_service.get_path_steps("lp:tech:python-mastery")
if steps_result.is_ok:
    for step in steps_result.value:
        for ku_uid in step.knowledge_uids:
            progress = await ku_search.get_user_progress(ku_uid, "user_mike")
            if progress.is_ok and progress.value["mastery_level"] < 0.8:
                print(f"Gap: {ku_uid}")
```

### Smart prioritization across domains

```python
# Get prioritized items from each domain
tasks = await tasks_search.get_prioritized("user.123", limit=5)
goals = await goals_search.get_prioritized("user.123", limit=3)
habits = await habits_search.get_prioritized("user.123", limit=5)
kus = await ku_search.get_prioritized("user.123", limit=5)

# Or use SearchRouter for unified search (wired in compose with explicit deps)
from core.orchestrator.search_router import SearchRouter
router = services.search_router
result = await router.faceted_search(SearchRequest(
    query="",
    domains=[EntityType.TASK, EntityType.GOAL, EntityType.CURRICULUM],
    user_uid="user.123",
    limit=10
))
```

### Graph-aware search with relationship filters

```python
# Find KUs whose prerequisites you've already mastered
request = SearchRequest(
    query_text="advanced",
    ready_to_learn=True,  # boolean relationship-filter field
    user_uid="user.123",
)
result = await ku_search.graph_aware_faceted_search(request, user_uid="user.123")
```

---

## See Also

- **Architecture:** `/docs/architecture/SEARCH_ARCHITECTURE.md`
- **Patterns:** `/docs/patterns/search_service_pattern.md`
- **Query Building:** `/docs/patterns/query_architecture.md`
- **ADR-023:** `/docs/decisions/ADR-023-curriculum-baseservice-migration.md`

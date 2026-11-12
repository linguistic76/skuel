---
related_skills:
- skuel-search-architecture
---
# Search Service Method Reference

**WARNING:** This file is AUTO-GENERATED. Do not edit manually.
**Regenerate:** `cd app && uv run python scripts/generate_search_method_catalog.py`
**Drift-guarded:** `tests/unit/scripts/test_generate_search_method_catalog.py`

Every search method of the 9 domain search services, read from the live classes. The inherited surface is the public methods of `SearchOperationsMixin`, `RelationshipOperationsMixin`, `TimeQueryMixin`; CRUD and the other `BaseService` mixins are in [BaseService Method Index](BASESERVICE_METHOD_INDEX.md).

How `SearchRouter` reaches these services, the relationship filters on `SearchRequest`, and graph enrichment: [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md).

---

## Quick Reference Matrix

**I** = inherited from the mixin · **O** = the service overrides a `BaseService` method · **D** = defined by the service alone · **-** = not on the service · **†** = declared by `DomainSearchOperations`

A method marked **Staged** below is registered in the bloat detector's PLANNED tier (`PLANNED_METHODS` in `scripts/detect_bloat.py`): built, and not yet reached by a production caller.

| Method | Tasks | Goals | Habits | Events | Choices | Principles | KU | PS | LP |
|--------|:---:|:---:|:----:|:----:|:-----:|:--------:|:-:|:-:|:-:|
| **SearchOperationsMixin** | | | | | | | | | |
| `count()` | I | I | I | I | I | I | I | I | I |
| `get_all_for_user()` | I | I | I | I | I | I | I | I | I |
| `get_by_category()` | I | I | I | I | I | O | I | I | I |
| `get_by_relationship()`† | I | I | I | I | I | I | I | I | I |
| `get_by_status()`† | I | I | I | I | I | O | I | I | I |
| `graph_aware_faceted_search()` | I | I | I | I | I | I | I | I | I |
| `list_all_categories()` | I | I | I | I | I | I | I | I | I |
| `list_recent_for_user()`† | I | I | I | I | I | I | I | I | I |
| `list_user_categories()` | I | I | I | I | I | I | I | I | I |
| `search()`† | I | I | I | I | I | I | I | I | I |
| `search_array_field()` | I | I | I | I | I | I | I | I | I |
| `search_by_tags()` | I | I | I | I | I | I | I | I | I |
| `search_connected_to()` | I | I | I | I | I | I | I | I | I |
| `search_for_user()`† | I | I | I | I | I | I | I | I | I |
| `tag_frequencies()` | I | I | I | I | I | I | I | I | I |
| **RelationshipOperationsMixin** | | | | | | | | | |
| `add_prerequisite()` | I | I | I | I | I | I | I | I | I |
| `add_relationship()` | I | I | I | I | I | I | I | I | I |
| `get_enables()` | I | I | I | I | I | I | I | I | I |
| `get_hierarchy()` | I | I | I | I | I | I | I | I | I |
| `get_prerequisites()` | I | I | I | I | I | I | I | I | I |
| `get_relationships()` | I | I | I | I | I | I | I | I | I |
| `traverse()` | I | I | I | I | I | I | I | I | I |
| **TimeQueryMixin** | | | | | | | | | |
| `get_active()`† | I | I | O | I | I | O | I | I | I |
| `get_overdue()`† | I | I | O | I | I | O | I | I | I |
| `get_upcoming()`† | I | I | O | I | I | O | I | I | I |
| `get_user_items_in_range()` | I | I | I | I | I | I | I | I | I |
| `get_user_items_in_range_base()` | I | I | I | I | I | I | I | I | I |
| **Defined by a service** | | | | | | | | | |
| `enrich_with_goal_links()` | D | - | D | - | - | - | - | - | - |
| `get_aligned_with_goal()` | - | - | - | - | - | - | - | - | D |
| `get_all_due_today()` | - | - | D | - | - | - | - | - | - |
| `get_at_risk()` | - | - | D | - | - | - | - | - | - |
| `get_blocked_by_prerequisites()` | D | - | - | - | - | - | - | - | - |
| `get_by_frequency()` | - | - | D | - | - | - | - | - | - |
| `get_by_knowledge()` | - | - | - | - | - | - | - | - | D |
| `get_calendar_events()` | - | - | - | D | - | - | - | - | - |
| `get_conflicting()` | - | - | - | D | - | - | - | - | - |
| `get_for_goal()` | - | - | - | - | - | D | - | - | - |
| `get_for_habit()` | - | - | - | D | - | - | - | - | - |
| `get_in_range()` | - | - | - | D | - | - | - | - | - |
| `get_needing_attention()` | - | - | D | - | - | - | - | - | - |
| `get_needing_decision()` | - | - | - | - | D | - | - | - | - |
| `get_needing_review()` | - | - | - | - | - | D | - | - | - |
| `get_pending()` | - | - | - | - | D | - | - | - | - |
| `get_prioritized()`† | D | D | D | D | D | D | - | D | D |
| `get_recurring()` | - | - | - | D | - | - | - | - | - |
| `get_related_principles()` | - | - | - | - | - | D | - | - | - |
| `get_standalone_steps()` | - | - | - | - | - | - | - | D | - |
| `get_tasks_for_goal()` | D | - | - | - | - | - | - | - | - |
| `get_tasks_for_habit()` | D | - | - | - | - | - | - | - | - |
| `get_tasks_for_path_step()` | D | - | - | - | - | - | - | - | - |
| `get_user_assigned_tasks()` | D | - | - | - | - | - | - | - | - |
| `get_user_due_today()` | - | - | D | - | - | - | - | - | - |
| `list_library()` | - | - | - | - | - | - | D | - | - |
| `nous_subtopic_pairs()` | - | - | - | - | - | - | D | D | - |
| `search_by_alias()` | - | - | - | - | - | - | D | - | - |

---

## Inherited Methods

### SearchOperationsMixin

**File:** `core/services/mixins/search_operations_mixin.py`

| Method | Signature | Summary |
|--------|-----------|---------|
| `count` | `(**filters: Any) -> Result[int]` | Count entities matching filters. |
| `get_all_for_user` | `(user_uid: UserUID) -> Result[builtins.list[T]]` | Fetch the user's entities of this domain, whatever their status. |
| `get_by_category` | `(category: str, user_uid: UserUID \| None = None, limit: int = 100) -> Result[builtins.list[T]]` | Filter entities by category field. |
| `get_by_relationship` | `(related_uid: str, relationship_type: RelationshipName, direction: Direction = 'outgoing', user_uid: UserUID \| None = None) -> Result[builtins.list[T]]` | Get entities connected via graph relationship. |
| `get_by_status` | `(status: EntityStatus \| str, limit: int = 100, user_uid: UserUID \| None = None) -> Result[builtins.list[T]]` | Filter entities by status field. |
| `graph_aware_faceted_search` | `(request: SearchRequest, user_uid: UserUID \| None) -> Result[builtins.list[dict[str, Any]]]` | Graph-aware faceted search - THE unified method for all domains. |
| `list_all_categories` | `() -> Result[builtins.list[str]]` | List all unique category values across all users. |
| `list_recent_for_user` | `(user_uid: UserUID, limit: int = 10, exclude: builtins.set[str] \| None = None) -> Result[builtins.list[T]]` | List a user's most-recently-updated entities, with optional exclusions. |
| `list_user_categories` | `(user_uid: UserUID) -> Result[builtins.list[str]]` | List unique category values for a specific user's entities. |
| `search` | `(query: str, limit: int = 50, user_uid: UserUID \| None = None) -> Result[builtins.list[T]]` | Text search across configured search fields. |
| `search_array_field` | `(field: str, value: str, limit: int = 50, user_uid: UserUID \| None = None) -> Result[builtins.list[T]]` | Search any array field for a value (generic array search). **Staged** (`PLANNED_METHODS`). |
| `search_by_tags` | `(tags: builtins.list[str], match_all: bool = False, limit: int = 50, user_uid: UserUID \| None = None) -> Result[builtins.list[T]]` | Search entities by tags (array field search). |
| `search_connected_to` | `(query: str, related_uid: str, relationship_type: RelationshipName, direction: Direction = 'outgoing', limit: int = 50, user_uid: UserUID \| None = None) -> Result[builtins.list[T]]` | Graph-aware search: text search + relationship traversal in ONE query. |
| `search_for_user` | `(query: str, user_uid: UserUID, limit: int = 10, exclude: builtins.set[str] \| None = None) -> Result[builtins.list[T]]` | User-scoped title/description search with optional UID exclusions. |
| `tag_frequencies` | `(user_uid: UserUID \| None = None) -> Result[dict[str, int]]` | Map each distinct tag on this domain's entities to its usage count. |

### RelationshipOperationsMixin

**File:** `core/services/mixins/relationship_operations_mixin.py`

| Method | Signature | Summary |
|--------|-----------|---------|
| `add_prerequisite` | `(entity_uid: EntityUID, prerequisite_uid: str, confidence: float = 1.0) -> Result[bool]` | Add a prerequisite relationship. **Staged** (`PLANNED_METHODS`). |
| `add_relationship` | `(from_uid: str, rel_type: RelationshipName, to_uid: str, properties: dict[str, Any] \| None = None) -> Result[bool]` | Add a relationship between two entities. |
| `get_enables` | `(uid: str, depth: int = 3) -> Result[builtins.list[T]]` | Get entities enabled by this entity. **Staged** (`PLANNED_METHODS`). |
| `get_hierarchy` | `(uid: str) -> Result[dict[str, Any]]` | Get hierarchical structure for this entity. |
| `get_prerequisites` | `(uid: str, depth: int = 3) -> Result[builtins.list[T]]` | Get prerequisite entities for this entity. **Staged** (`PLANNED_METHODS`). |
| `get_relationships` | `(uid: str, rel_type: RelationshipName \| None = None, direction: Direction = 'both') -> Result[builtins.list[RelationshipRow]]` | Get all relationships for an entity. |
| `traverse` | `(start_uid: str, rel_pattern: str, max_depth: int = 3, include_properties: bool = False) -> Result[builtins.list[TraversalNodeRow]]` | Traverse the graph following a relationship pattern. |

### TimeQueryMixin

**File:** `core/services/mixins/time_query_mixin.py`

| Method | Signature | Summary |
|--------|-----------|---------|
| `get_active` | `(user_uid: UserUID, limit: int = 100) -> Result[builtins.list[T]]` | Get user's active (non-terminal) entities. |
| `get_overdue` | `(user_uid: UserUID \| None = None, limit: int = 100) -> Result[builtins.list[T]]` | Get entities past their due date. |
| `get_upcoming` | `(days_ahead: int = 7, user_uid: UserUID \| None = None, limit: int = 100) -> Result[builtins.list[T]]` | Get entities upcoming within specified number of days. |
| `get_user_items_in_range` | `(user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False, date_field: str \| builtins.list[str] \| None = None) -> Result[builtins.list[T]]` | Get user's items in date range - unified implementation using class attributes. |
| `get_user_items_in_range_base` | `(user_uid: UserUID, start_date: date, end_date: date, date_field: str \| builtins.list[str], dto_class: type[DTOProtocol], model_class: type[T], exclude_statuses: builtins.list[str] \| None = None) -> Result[builtins.list[T]]` | Generic user items in date range query - DRY principle. |

---

## Domain Search Services

### TasksSearchService

**File:** `core/services/tasks/tasks_search_service.py`

- **Search fields:** `title`, `description` (ordered by `created_at`)
- **Category field:** `category`
- **Date field:** `due_date`
- **Ownership:** `OWNS` edge
- **Prerequisite edges:** `BLOCKED_BY`, `REQUIRES_TASK`
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `enrich_with_goal_links` | `(tasks: list[Task], active_goal_uids: list[str] \| None = None) -> list[Task]` | Populate each task's derived `contributes_to_goal_uid` from its CONTRIBUTES_TO_GOAL edges. |
| `get_blocked_by_prerequisites` | `(user_uid: UserUID) -> Result[list[Task]]` | Get tasks blocked by missing prerequisites. |
| `get_prioritized` | `(user_context: UserContext, limit: int = 10) -> Result[list[Task]]` | Get prioritized tasks using the unified cross-domain scorer. **Staged** (`PLANNED_METHODS`). |
| `get_tasks_for_goal` | `(goal_uid: str, user_uid: UserUID) -> Result[list[Task]]` | Get the user's tasks that contribute to a specific goal. |
| `get_tasks_for_habit` | `(habit_uid: str, user_uid: UserUID) -> Result[list[Task]]` | Get the user's tasks that reinforce a specific habit. |
| `get_tasks_for_path_step` | `(step_uid: str, user_uid: UserUID) -> Result[list[Task]]` | Get the user's tasks spawned from a specific path step. |
| `get_user_assigned_tasks` | `(user_uid: UserUID, include_completed: bool = False, limit: int = 100) -> Result[list[Task]]` | Get tasks assigned to user via graph traversal. **Staged** (`PLANNED_METHODS`). |

### GoalsSearchService

**File:** `core/services/goals/goals_search_service.py`

- **Search fields:** `title`, `description` (ordered by `created_at`)
- **Category field:** `domain`
- **Date field:** `target_date`
- **Ownership:** `OWNS` edge
- **Prerequisite edges:** `REQUIRES_KNOWLEDGE`, `DEPENDS_ON_GOAL`
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `get_prioritized` | `(user_context: UserContext, limit: int = 10) -> Result[list[Goal]]` | Get goals prioritized for the user's current context. **Staged** (`PLANNED_METHODS`). |

### HabitsSearchService

**File:** `core/services/habits/habits_search_service.py`

- **Search fields:** `title`, `description` (ordered by `created_at`)
- **Category field:** `habit_category`
- **Date field:** `created_at`
- **Ownership:** `OWNS` edge
- **Prerequisite edges:** `REQUIRES_PREREQUISITE_HABIT`
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `enrich_with_goal_links` | `(habits: list[Habit], active_goal_uids: list[str] \| None = None) -> list[Habit]` | Populate each habit's derived `supports_goal_uid` from its SUPPORTS_GOAL edge. |
| `get_active` | `(user_uid: UserUID, limit: int = 100) -> Result[list[Habit]]` | Get the user's alive habits — active AND paused. |
| `get_all_due_today` | `() -> Result[list[Habit]]` | Get all habits due today across all users (admin use). |
| `get_at_risk` | `(user_context: UserContext) -> Result[list[Habit]]` | Get the user's at-risk habits, those with the most streak to lose first. **Staged** (`PLANNED_METHODS`). |
| `get_by_frequency` | `(frequency: HabitFrequency, limit: int = 100) -> Result[list[Habit]]` | Get habits filtered by frequency. |
| `get_needing_attention` | `(user_uid: UserUID, streak_threshold: int = 3, limit: int = 50) -> Result[list[Habit]]` | Get the user's habits that need attention based on streak status. **Staged** (`PLANNED_METHODS`). |
| `get_overdue` | `(user_uid: UserUID \| None = None, limit: int = 100) -> Result[list[Habit]]` | Get habits that are overdue based on their frequency. |
| `get_prioritized` | `(user_context: UserContext, limit: int = 10) -> Result[list[Habit]]` | Get habits prioritized for the user's current context. **Staged** (`PLANNED_METHODS`). |
| `get_upcoming` | `(days_ahead: int = 7, user_uid: UserUID \| None = None, limit: int = 100) -> Result[list[Habit]]` | Get habits upcoming within specified number of days based on frequency. |
| `get_user_due_today` | `(user_uid: UserUID) -> Result[list[Habit]]` | Get habits due today for a specific user. |

### EventsSearchService

**File:** `core/services/events/events_search_service.py`

- **Search fields:** `title`, `description` (ordered by `event_date`)
- **Category field:** `category`
- **Date field:** `event_date`
- **Ownership:** `OWNS` edge
- **Prerequisite edges:** `REQUIRES_KNOWLEDGE`
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `get_calendar_events` | `(user_uid: UserUID, start_date: date \| None = None, end_date: date \| None = None, limit: int = 100) -> Result[list[Event]]` | Get events for calendar display. |
| `get_conflicting` | `(event_uid: str) -> Result[list[Event]]` | Get events that conflict with a given event. **Staged** (`PLANNED_METHODS`). |
| `get_for_habit` | `(habit_uid: str, user_uid: UserUID \| None = None) -> Result[list[Event]]` | Get events that reinforce a specific habit. |
| `get_in_range` | `(start_date: date, end_date: date, user_uid: UserUID \| None = None, limit: int = 100) -> Result[list[Event]]` | Get events within a date range. |
| `get_prioritized` | `(user_context: UserContext, limit: int = 10) -> Result[list[Event]]` | Get events prioritized for the user's current context. **Staged** (`PLANNED_METHODS`). |
| `get_recurring` | `(user_uid: UserUID \| None = None, limit: int = 100) -> Result[list[Event]]` | Get recurring events. |

### ChoicesSearchService

**File:** `core/services/choices/choices_search_service.py`

- **Search fields:** `title`, `description` (ordered by `created_at`)
- **Category field:** `category`
- **Date field:** `decision_deadline`
- **Ownership:** `OWNS` edge
- **Prerequisite edges:** `REQUIRES_KNOWLEDGE_FOR_DECISION`
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `get_needing_decision` | `(user_uid: UserUID, deadline_days: int = 7) -> Result[list[Choice]]` | Get the pending choices whose deadline falls within N days. |
| `get_pending` | `(user_uid: UserUID, limit: int = 100) -> Result[list[Choice]]` | Get the choices a user has yet to decide (`Choice.is_pending`). |
| `get_prioritized` | `(user_context: UserContext, limit: int = 10) -> Result[list[Choice]]` | Get choices prioritized for the user's current context. **Staged** (`PLANNED_METHODS`). |

### PrinciplesSearchService

**File:** `core/services/principles/principles_search_service.py`

- **Search fields:** `title`, `statement`, `description` (ordered by `created_at`)
- **Category field:** `principle_category`
- **Date field:** `created_at`
- **Ownership:** `OWNS` edge
- **Prerequisite edges:** `GROUNDED_IN_KNOWLEDGE`
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `get_active` | `(user_uid: UserUID, limit: int = 100) -> Result[list[Principle]]` | Get all active principles for a user. |
| `get_by_category` | `(category: PrincipleCategory \| str, user_uid: UserUID \| None = None, limit: int = 100) -> Result[list[Principle]]` | Get principles in a specific category. |
| `get_by_status` | `(status: EntityStatus \| str, limit: int = 100, user_uid: UserUID \| None = None) -> Result[list[Principle]]` | Filter principles by active/inactive status. |
| `get_for_goal` | `(goal_uid: str, limit: int = 10, user_uid: UserUID \| None = None) -> Result[list[Principle]]` | Get the principles that support a goal, whichever page made the link. |
| `get_needing_review` | `(user_uid: UserUID \| None = None, days_threshold: int = 90, limit: int = 20) -> Result[list[Principle]]` | Get principles that need alignment review. |
| `get_overdue` | `(user_uid: UserUID \| None = None, limit: int = 100) -> Result[list[Principle]]` | Get principles past their 90-day review threshold. |
| `get_prioritized` | `(user_context: UserContext, limit: int = 10) -> Result[list[Principle]]` | Get principles prioritized for the user's current context. **Staged** (`PLANNED_METHODS`). |
| `get_related_principles` | `(principle_uid: str, depth: int = 2, limit: int = 10) -> Result[list[Principle]]` | Get principles related to a given principle. |
| `get_upcoming` | `(days_ahead: int = 30, user_uid: UserUID \| None = None, limit: int = 100) -> Result[list[Principle]]` | Get principles needing review within specified number of days. |

### KuSearchService

**File:** `core/services/ku/ku_search_service.py`

- **Search fields:** `title`, `description` (ordered by `updated_at`)
- **Category field:** `nous`
- **Date field:** `created_at`
- **Ownership:** none (shared content)
- **Prerequisite edges:** none
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `list_library` | `(limit: int) -> Result[tuple[list[Ku], int]]` | The library's first `limit` Kus, oldest first, and its size — drafts are neither listed nor counted. |
| `nous_subtopic_pairs` | `() -> Result[list[NousSubtopicPair]]` | This Ku label's contribution of (nous, nous_subtopic) co-occurrence pairs. |
| `search_by_alias` | `(alias: str) -> Result[list[dict[str, Any]]]` | Search Kus by alias (alternative name). |

### PsSearchService

**File:** `core/services/ps/ps_search_service.py`

- **Search fields:** `title`, `intent`, `description` (ordered by `updated_at`)
- **Category field:** `nous`
- **Date field:** `created_at`
- **Ownership:** none (shared content)
- **Prerequisite edges:** `REQUIRES_STEP`, `REQUIRES_KNOWLEDGE`
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `get_prioritized` | `(user_uid: UserUID, context: UserContext, limit: int = 20) -> Result[list[PathStep]]` | Get PathSteps prioritized by user context. **Staged** (`PLANNED_METHODS`). |
| `get_standalone_steps` | `(limit: int = 50) -> Result[list[PathStep]]` | Get standalone PathSteps (not part of any learning path). **Staged** (`PLANNED_METHODS`). |
| `nous_subtopic_pairs` | `() -> Result[list[NousSubtopicPair]]` | This PathStep label's contribution of (nous, nous_subtopic) pairs. |

### LpSearchService

**File:** `core/services/lp/lp_search_service.py`

- **Search fields:** `title`, `description` (ordered by `updated_at`)
- **Category field:** `domain`
- **Date field:** `created_at`
- **Ownership:** none (shared content)
- **Prerequisite edges:** `REQUIRES_KNOWLEDGE`, `REQUIRES_STEP`
- **Graph enrichment (`_graph_enrichment_patterns`):** none — results carry no `_graph_context`

**Overridden and own methods** (everything else is inherited — see the matrix):

| Method | Signature | Summary |
|--------|-----------|---------|
| `get_aligned_with_goal` | `(goal_uid: str, limit: int = 50) -> Result[list[LearningPath]]` | Get Learning Paths aligned with a specific goal. **Staged** (`PLANNED_METHODS`). |
| `get_by_knowledge` | `(ku_uid: str, limit: int = 20) -> Result[list[LearningPath]]` | Find learning paths that teach this knowledge (via path steps). **Staged** (`PLANNED_METHODS`). |
| `get_prioritized` | `(user_uid: UserUID, context: UserContext, limit: int = 20) -> Result[list[LearningPath]]` | Get Learning Paths prioritized by user context. **Staged** (`PLANNED_METHODS`). |

---

## See Also

- [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) — SearchRouter, relationship filters, graph enrichment
- [Search Service Pattern](../patterns/search_service_pattern.md) — writing a search service
- [BaseService Method Index](BASESERVICE_METHOD_INDEX.md) — the rest of the BaseService surface
- [Search protocols](/core/ports/search_protocols.py) — `DomainSearchOperations` and the per-domain search protocols

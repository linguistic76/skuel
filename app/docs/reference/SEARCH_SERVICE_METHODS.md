---
related_skills:
- skuel-search-architecture
---
# Search Service Method Reference
*Last updated: 2026-01-06*

Complete catalog of methods across all 10 domain search services. All services extend `BaseService[Backend, Model]` following the unified architecture (ADR-023).

---

## Quick Reference Matrix

Legend: **I** = Inherited from BaseService | **O** = Override | **D** = Domain-specific

| Method | Tasks | Goals | Habits | Events | Choices | Principles | KU | LS | LP | MOC |
|--------|:-----:|:-----:|:------:|:------:|:-------:|:----------:|:--:|:--:|:--:|:---:|
| **Inherited (BaseService)** |
| `search()` | I | I | I | I | I | I | I | I | I | I |
| `get_by_status()` | I | I | I | I | I | O | I | I | I | I |
| `get_by_domain()` | I | I | I | I | I | O | I | I | I | I |
| `get_by_category()` | I | I | I | I | I | I | I | I | I | I |
| `list_categories()` | I | I | I | I | I | O | I | I | I | I |
| `get_by_relationship()` | I | I | I | I | I | I | I | I | I | I |
| `graph_aware_faceted_search()` | I | I | I | I | I | I | I | I | I | I |
| `search_by_tags()` | I | I | I | I | I | I | I | I | I | I |
| `get_prerequisites()` | I | I | I | I | I | I | I | I | I | I |
| `get_enables()` | I | I | I | I | I | I | I | I | I | I |
| `get_user_progress()` | I | I | I | I | I | I | I | I | I | I |
| **Protocol (DomainSearchOperations)** |
| `get_prioritized()` | D | D | D | D | D | D | D | D | D | D |
| `intelligent_search()` | - | D | D | D | - | - | - | D | D | D |
| **Domain-Specific** |
| `get_blocking_tasks()` | D | - | - | - | - | - | - | - | - | - |
| `get_blocked_tasks()` | D | - | - | - | - | - | - | - | - | - |
| `get_by_priority()` | D | D | - | - | - | - | - | - | - | - |
| `get_overdue()` | D | - | - | - | - | - | - | - | - | - |
| `get_due_soon()` | D | - | - | - | - | - | - | - | - | - |
| `get_pending()` | D | - | - | - | D | - | - | - | - | - |
| `get_by_progress()` | - | D | - | - | - | - | - | - | - | - |
| `get_active_*()` | - | D | D | - | - | D | - | - | - | - |
| `get_by_frequency()` | - | - | D | - | - | - | - | - | - | - |
| `get_by_streak_status()` | - | - | D | - | - | - | - | - | - | - |
| `get_upcoming()` | - | - | - | D | - | - | - | - | - | - |
| `get_by_date_range()` | - | - | - | D | - | - | - | - | - | - |
| `get_by_urgency()` | - | - | - | - | D | - | - | - | - | - |
| `get_by_strength()` | - | - | - | - | - | D | - | - | - | - |
| `search_chunks()` | - | - | - | - | - | - | D | - | - | - |
| `find_similar_content()` | - | - | - | - | - | - | D | - | - | - |
| `get_for_learning_path()` | - | - | - | - | - | - | - | D | - | - |
| `get_by_path_type()` | - | - | - | - | - | - | - | - | D | - |
| `get_templates()` | - | - | - | - | - | - | - | - | - | D |
| `get_by_visibility()` | - | - | - | - | - | - | - | - | - | D |

---

## Inherited Methods (from BaseService)

All search services inherit these methods from `BaseService[Backend, Model]`. Configure behavior via class attributes.

### Core Search Methods

#### `search(query: str, user_uid: str | None, limit: int = 50) -> Result[list[Model]]`
Text search across configured `_search_fields`. Orders by `_search_order_by`.

```python
result = await tasks_search.search("urgent deadline", user_uid="user.123")
```

#### `graph_aware_faceted_search(request: SearchRequest) -> Result[SearchResponse]`
**THE unified search method.** Combines text search, graph traversal, and faceted filtering.

```python
request = SearchRequest(
    query="python",
    filters={"domain": "tech"},
    graph_patterns=["ready_to_learn", "supports_goals"],
    user_uid="user.123"
)
result = await ku_search.graph_aware_faceted_search(request)
```

#### `search_by_tags(tags: list[str], match_all: bool = False, user_uid: str | None = None) -> Result[list[Model]]`
Array field search with AND/OR semantics.

```python
# Find items with ANY of these tags (OR)
result = await ku_search.search_by_tags(["python", "ml"], match_all=False)

# Find items with ALL tags (AND)
result = await ku_search.search_by_tags(["python", "ml"], match_all=True)
```

### Filter Methods

#### `get_by_status(status: str, user_uid: str | None = None) -> Result[list[Model]]`
Filter by status field. Activity domains use `ActivityStatus` enum.

```python
result = await tasks_search.get_by_status("active", user_uid="user.123")
```

#### `get_by_domain(domain: Domain, user_uid: str | None = None) -> Result[list[Model]]`
Filter by domain field.

```python
result = await goals_search.get_by_domain(Domain.HEALTH, user_uid="user.123")
```

#### `get_by_category(category: str, user_uid: str | None = None) -> Result[list[Model]]`
Filter by `_category_field` (varies by domain).

```python
result = await principles_search.get_by_category("core_values", user_uid="user.123")
```

#### `list_categories(user_uid: str | None = None) -> Result[list[str]]`
Get distinct values of `_category_field`.

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

#### `get_user_progress(uid: str, user_uid: str) -> Result[dict]`
Get user's progress/mastery for curriculum items (when `_supports_user_progress = True`).

```python
result = await ku_search.get_user_progress("ku.python-basics", "user.123")
# Returns: {"mastery_level": 0.8, "last_reviewed": "2026-01-05", ...}
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

    # Categorization
    _category_field: str = "domain"  # or "category", "type", etc.

    # Content (for curriculum)
    _content_field: str = "content"
    _mastery_threshold: float = 0.8

    # User ownership
    _user_ownership_relationship: ClassVar[str | None] = "OWNS"  # None for shared content
    _supports_user_progress: bool = False  # True for curriculum

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
_category_field = "category"
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
| `get_blocking_tasks` | `(uid: str, user_uid: str) -> Result[list[Task]]` | Tasks blocking this task |
| `get_blocked_tasks` | `(uid: str, user_uid: str) -> Result[list[Task]]` | Tasks blocked by this task |
| `get_by_priority` | `(priority: Priority, user_uid: str) -> Result[list[Task]]` | Filter by priority level |
| `get_overdue` | `(user_uid: str) -> Result[list[Task]]` | Tasks past due date |
| `get_due_soon` | `(user_uid: str, days: int = 7) -> Result[list[Task]]` | Tasks due within N days |
| `get_pending` | `(user_uid: str) -> Result[list[Task]]` | Tasks with pending status |
| `search_by_parent_goal` | `(goal_uid: str, user_uid: str) -> Result[list[Task]]` | Tasks fulfilling a goal |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Task]]` | Smart prioritization |

---

### GoalsSearchService

**File:** `core/services/goals/goals_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "success_criteria"]
_category_field = "domain"
_graph_enrichment_patterns = [
    ("FULFILLS_GOAL", "Task", "contributing_tasks", "incoming"),
    ("SUPPORTS_GOAL", "Habit", "supporting_habits", "incoming"),
    ("ALIGNED_WITH_PRINCIPLE", "Principle", "guiding_principles", "outgoing"),
    ("REQUIRES_KNOWLEDGE", "Ku", "required_knowledge", "outgoing"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_by_priority` | `(priority: Priority, user_uid: str) -> Result[list[Goal]]` | Filter by priority |
| `get_by_progress` | `(min_progress: float, max_progress: float, user_uid: str) -> Result[list[Goal]]` | Filter by progress range |
| `get_by_milestone_status` | `(status: str, user_uid: str) -> Result[list[Goal]]` | Filter by milestone status |
| `get_active_goals` | `(user_uid: str) -> Result[list[Goal]]` | Active goals only |
| `get_goals_needing_attention` | `(user_uid: str) -> Result[list[Goal]]` | Stalled or at-risk goals |
| `get_goals_with_tasks` | `(user_uid: str) -> Result[list[Goal]]` | Goals with linked tasks |
| `get_aligned_with_principle` | `(principle_uid: str, user_uid: str) -> Result[list[Goal]]` | Goals aligned with principle |
| `intelligent_search` | `(query: str, user_uid: str, context: dict) -> Result[list[Goal]]` | AI-enhanced search |
| `list_milestones` | `(goal_uid: str, user_uid: str) -> Result[list[dict]]` | Get goal milestones |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Goal]]` | Smart prioritization |

---

### HabitsSearchService

**File:** `core/services/habits/habit_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "cue", "routine", "reward"]
_category_field = "frequency"
_graph_enrichment_patterns = [
    ("SUPPORTS_GOAL", "Goal", "supported_goals", "outgoing"),
    ("REINFORCES_KNOWLEDGE", "Ku", "reinforced_knowledge", "outgoing"),
    ("INSPIRED_BY_PRINCIPLE", "Principle", "inspiring_principles", "outgoing"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_by_frequency` | `(frequency: str, user_uid: str) -> Result[list[Habit]]` | Filter by frequency (daily/weekly/etc) |
| `get_by_streak_status` | `(min_streak: int, user_uid: str) -> Result[list[Habit]]` | Filter by streak length |
| `get_active_habits` | `(user_uid: str) -> Result[list[Habit]]` | Active habits only |
| `get_habits_needing_attention` | `(user_uid: str) -> Result[list[Habit]]` | Broken streaks or declining |
| `get_reinforcing_knowledge` | `(ku_uid: str, user_uid: str) -> Result[list[Habit]]` | Habits reinforcing a KU |
| `get_supporting_goal` | `(goal_uid: str, user_uid: str) -> Result[list[Habit]]` | Habits supporting a goal |
| `intelligent_search` | `(query: str, user_uid: str, context: dict) -> Result[list[Habit]]` | AI-enhanced search |
| `get_habits_by_time_of_day` | `(time_of_day: str, user_uid: str) -> Result[list[Habit]]` | Morning/afternoon/evening habits |
| `get_habit_chain_candidates` | `(habit_uid: str, user_uid: str) -> Result[list[Habit]]` | Potential habit stacking |
| `get_knowledge_reinforcement_opportunities` | `(user_uid: str) -> Result[list[dict]]` | KU-habit connection opportunities |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Habit]]` | Smart prioritization |

---

### EventsSearchService

**File:** `core/services/events/events_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "location"]
_category_field = "event_type"
_graph_enrichment_patterns = [
    ("RELATED_TO_GOAL", "Goal", "related_goals", "outgoing"),
    ("APPLIES_KNOWLEDGE", "Ku", "applied_knowledge", "outgoing"),
    ("PRACTICE_FOR_HABIT", "Habit", "practiced_habits", "outgoing"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_upcoming` | `(user_uid: str, days: int = 7) -> Result[list[Event]]` | Events in next N days |
| `get_past` | `(user_uid: str, days: int = 30) -> Result[list[Event]]` | Events in past N days |
| `get_by_date_range` | `(start: date, end: date, user_uid: str) -> Result[list[Event]]` | Events in date range |
| `get_recurring` | `(user_uid: str) -> Result[list[Event]]` | Recurring events only |
| `get_by_event_type` | `(event_type: str, user_uid: str) -> Result[list[Event]]` | Filter by type |
| `get_related_to_goal` | `(goal_uid: str, user_uid: str) -> Result[list[Event]]` | Events related to goal |
| `intelligent_search` | `(query: str, user_uid: str, context: dict) -> Result[list[Event]]` | AI-enhanced search |
| `get_events_needing_prep` | `(user_uid: str, days: int = 3) -> Result[list[Event]]` | Upcoming events needing preparation |
| `get_calendar_view` | `(user_uid: str, month: int, year: int) -> Result[dict]` | Calendar-formatted view |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Event]]` | Smart prioritization |

---

### ChoicesSearchService

**File:** `core/services/choices/choices_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "context"]
_category_field = "category"
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
| `get_pending` | `(user_uid: str) -> Result[list[Choice]]` | Undecided choices |
| `get_by_urgency` | `(urgency: str, user_uid: str) -> Result[list[Choice]]` | Filter by urgency level |
| `get_affecting_goal` | `(goal_uid: str, user_uid: str) -> Result[list[Choice]]` | Choices affecting a goal |
| `get_needing_decision` | `(user_uid: str, days: int = 7) -> Result[list[Choice]]` | Choices with deadline approaching |
| `get_aligned_with_principle` | `(principle_uid: str, user_uid: str) -> Result[list[Choice]]` | Choices aligned with principle |
| `get_decided` | `(user_uid: str, days: int = 30) -> Result[list[Choice]]` | Recently decided choices |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Choice]]` | Smart prioritization |

---

### PrinciplesSearchService

**File:** `core/services/principles/principles_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "rationale"]
_category_field = "category"
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
| `get_by_domain` | Domain is `core_domain` field in Principles |
| `list_categories` | Custom category enumeration |

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_by_strength` | `(min_strength: float, user_uid: str) -> Result[list[Principle]]` | Filter by conviction strength |
| `get_by_category` | `(category: str, user_uid: str) -> Result[list[Principle]]` | Filter by category |
| `get_guiding_goals` | `(principle_uid: str, user_uid: str) -> Result[list[Goal]]` | Goals guided by principle |
| `get_inspiring_habits` | `(principle_uid: str, user_uid: str) -> Result[list[Habit]]` | Habits inspired by principle |
| `get_for_choice` | `(choice_uid: str, user_uid: str) -> Result[list[Principle]]` | Relevant principles for decision |
| `get_for_goal` | `(goal_uid: str, user_uid: str) -> Result[list[Principle]]` | Principles aligned with goal |
| `get_active_principles` | `(user_uid: str) -> Result[list[Principle]]` | Active principles only |
| `get_needing_review` | `(user_uid: str, days: int = 90) -> Result[list[Principle]]` | Principles not reviewed recently |
| `get_related_principles` | `(principle_uid: str, user_uid: str) -> Result[list[Principle]]` | Related principles |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Principle]]` | Smart prioritization |

---

## Curriculum Domain Search Services

### KuSearchService

**File:** `core/services/ku/ku_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "content", "tags"]
_category_field = "domain"
_content_field = "content"
_supports_user_progress = True
_user_ownership_relationship = None  # Shared content
_graph_enrichment_patterns = [
    ("REQUIRES_KNOWLEDGE", "Ku", "prerequisites", "outgoing"),
    ("ENABLES_LEARNING", "Ku", "enables_learning", "outgoing"),
    ("APPLIES_KNOWLEDGE", "Task", "applied_in_tasks", "incoming"),
    ("REINFORCES_KNOWLEDGE", "Habit", "reinforced_by_habits", "incoming"),
    ("PART_OF_LP", "LearningPath", "learning_paths", "outgoing"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `search_by_title_template` | `(template: str, domain: Domain) -> Result[list[Ku]]` | Pattern-based title search |
| `search_by_tags` | `(tags: list[str], match_all: bool = False) -> Result[list[Ku]]` | Tag-based search |
| `search_by_facets` | `(facets: dict) -> Result[list[Ku]]` | Multi-facet filtering |
| `search_chunks` | `(query: str, limit: int = 10) -> Result[list[dict]]` | Semantic chunk search |
| `search_chunks_with_facets` | `(query: str, facets: dict) -> Result[list[dict]]` | Chunk search with filters |
| `get_content_chunks` | `(ku_uid: str) -> Result[list[dict]]` | Get all chunks for a KU |
| `find_similar_content` | `(ku_uid: str, limit: int = 5) -> Result[list[Ku]]` | Semantic similarity search |
| `search_by_features` | `(features: dict) -> Result[list[Ku]]` | Feature-based search |
| `search_with_user_context` | `(query: str, user_uid: str) -> Result[list[Ku]]` | Personalized search |
| `search_with_semantic_intent` | `(intent: str, user_uid: str) -> Result[list[Ku]]` | Intent-based discovery |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Ku]]` | Ready-to-learn prioritization |

---

### LsSearchService

**File:** `core/services/ls/ls_search_service.py`

**Configuration:**
```python
_search_fields = ["title", "intent", "description"]
_category_field = "learning_type"
_supports_user_progress = True
_user_ownership_relationship = None  # Shared content
_graph_enrichment_patterns = [
    ("CONTAINS_KNOWLEDGE", "Ku", "knowledge_units", "outgoing"),
    ("HAS_STEP", "LearningPath", "parent_paths", "incoming"),
    ("REQUIRES_STEP", "LearningStep", "prerequisite_steps", "outgoing"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_for_learning_path` | `(lp_uid: str) -> Result[list[Ls]]` | Steps in a learning path |
| `get_standalone_steps` | `() -> Result[list[Ls]]` | Steps not in any path |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Ls]]` | Ready-to-learn prioritization |
| `intelligent_search` | `(query: str, user_uid: str, context: dict) -> Result[list[Ls]]` | AI-enhanced search |

---

### LpSearchService

**File:** `core/services/lp/lp_search_service.py`

**Configuration:**
```python
_search_fields = ["name", "goal", "description"]
_category_field = "domain"
_supports_user_progress = True
_user_ownership_relationship = None  # Shared content (can be user-created)
_graph_enrichment_patterns = [
    ("HAS_STEP", "LearningStep", "steps", "outgoing"),
    ("ALIGNED_WITH_GOAL", "Goal", "aligned_goals", "outgoing"),
    ("REQUIRES_KNOWLEDGE", "Ku", "prerequisite_knowledge", "outgoing"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_by_path_type` | `(path_type: str) -> Result[list[Lp]]` | Filter by path type |
| `list_by_creator` | `(creator_uid: str) -> Result[list[Lp]]` | Paths by creator |
| `get_aligned_with_goal` | `(goal_uid: str, user_uid: str) -> Result[list[Lp]]` | Paths aligned with goal |
| `get_with_steps` | `(lp_uid: str) -> Result[dict]` | Path with full step details |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Lp]]` | Recommended paths |
| `intelligent_search` | `(query: str, user_uid: str, context: dict) -> Result[list[Lp]]` | AI-enhanced search |

---

### MocNavigationService

**File:** `/core/services/moc/moc_navigation_service.py`

**Configuration:**
```python
_search_fields = ["title", "description", "purpose"]
_category_field = "domain"
_user_ownership_relationship = None  # Shared content (can be user-created)
_graph_enrichment_patterns = [
    ("CONTAINS_KNOWLEDGE", "Ku", "knowledge_units", "outgoing"),
    ("CONTAINS_PATH", "LearningPath", "learning_paths", "outgoing"),
    ("CONTAINS_PRINCIPLE", "Principle", "principles", "outgoing"),
    ("RELATED_TO_MOC", "Moc", "related_mocs", "both"),
]
```

**Domain-Specific Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_templates` | `() -> Result[list[Moc]]` | Template MOCs for copying |
| `list_by_creator` | `(creator_uid: str) -> Result[list[Moc]]` | MOCs by creator |
| `get_related_mocs` | `(moc_uid: str) -> Result[list[Moc]]` | Related MOCs |
| `get_by_visibility` | `(visibility: str) -> Result[list[Moc]]` | Filter by visibility |
| `get_prioritized` | `(user_uid: str, limit: int = 10) -> Result[list[Moc]]` | Recommended MOCs |
| `intelligent_search` | `(query: str, user_uid: str, context: dict) -> Result[list[Moc]]` | AI-enhanced search |

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
# Get path prerequisites, check user progress
path_result = await lp_search.get_with_steps("lp.python-mastery")
if path_result.is_ok:
    for step in path_result.value["steps"]:
        for ku_uid in step.primary_knowledge_uids:
            progress = await ku_search.get_user_progress(ku_uid, "user.123")
            if progress.is_ok and progress.value["mastery_level"] < 0.8:
                print(f"Gap: {ku_uid}")
```

### Find habits reinforcing knowledge you're learning

```python
# Get habits that reinforce a specific KU
habits_result = await habits_search.get_reinforcing_knowledge("ku.mindfulness", "user.123")
```

### Get principles relevant to a decision

```python
# Find principles that should guide a choice
principles_result = await principles_search.get_for_choice("choice.career-change", "user.123")
```

### Smart prioritization across domains

```python
# Get prioritized items from each domain
tasks = await tasks_search.get_prioritized("user.123", limit=5)
goals = await goals_search.get_prioritized("user.123", limit=3)
habits = await habits_search.get_prioritized("user.123", limit=5)
kus = await ku_search.get_prioritized("user.123", limit=5)

# Or use SearchRouter for unified search
from core.models.search.search_router import SearchRouter
router = SearchRouter(services)
result = await router.faceted_search(SearchRequest(
    query="",
    domains=[EntityType.TASK, EntityType.GOAL, EntityType.KU],
    user_uid="user.123",
    limit=10
))
```

### Graph-aware search with relationship filters

```python
# Find KUs connected to ones you've mastered
request = SearchRequest(
    query="advanced",
    graph_patterns=["ready_to_learn"],  # Has prerequisites mastered
    user_uid="user.123"
)
result = await ku_search.graph_aware_faceted_search(request)
```

---

## See Also

- **Architecture:** `/docs/architecture/SEARCH_ARCHITECTURE.md`
- **Patterns:** `/docs/patterns/search_service_pattern.md`
- **Query Building:** `/docs/patterns/query_architecture.md`
- **ADR-023:** `/docs/decisions/ADR-023-curriculum-baseservice-migration.md`

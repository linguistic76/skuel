# Sub-Service Responsibility Catalog

**Purpose:** Quick reference for understanding which sub-service handles which responsibilities across SKUEL's Activity Domain facades.

**Last Updated:** 2026-03-03

---

## Overview

SKUEL's Activity Domain services (Tasks, Goals, Habits, Events, Choices, Principles) use a **facade pattern** with 3-11 specialized sub-services per domain. This catalog maps responsibilities to sub-services so developers can quickly find the right service for their needs.

### Quick Navigation

- [Common Sub-Services](#common-sub-services) - Present in all Activity Domains
- [Domain-Specific Sub-Services](#domain-specific-sub-services) - Unique to certain domains
- [By Responsibility](#by-responsibility) - Find service by what you want to do
- [Access Patterns](#access-patterns) - How to import and use sub-services

---

## Common Sub-Services

These sub-services exist across **all 6 Activity Domains** (Tasks, Goals, Habits, Events, Choices, Principles):

### CoreService

**File:** `{domain}_core_service.py`
**Extends:** `BaseService[{Domain}Operations, {Domain}]`
**Protocol:** `{Domain}Operations`

**Responsibility:** CRUD operations and event publishing

**Key Methods:**
- `create()` - Create new entity
- `get()` - Get by UID
- `update()` - Update entity
- `delete()` - Delete entity
- `list()` - List with filters
- `get_user_{entities}()` - Get all entities for user

**When to use:**
- Creating, reading, updating, or deleting entities
- Basic queries without complex graph traversal
- Publishing domain events after state changes

**Dependencies:**
- `backend: {Domain}Operations` (e.g., `TasksOperations`, `GoalsOperations`)
- `event_bus: EventBus` (optional)
- Domain-specific services (e.g., `entity_inference_service` for TasksCoreService)

**Example:**
```python
from core.services.tasks import TasksCoreService

core = TasksCoreService(backend=backend, event_bus=event_bus)
result = await core.create_task(request, user_uid)
```

---

### SearchService

**File:** `{domain}_search_service.py`
**Extends:** `BaseService[{Domain}Operations, {Domain}]`
**Protocol:** `{Domain}SearchOperations`

**Responsibility:** Search, discovery, and filtering

**Key Methods:**
- `search()` - Full-text search
- `get_by_status()` - Filter by status
- `get_by_category()` - Filter by category/domain
- `list_categories()` - Get available categories
- `search_by_tags()` - Filter by tags
- Domain-specific queries (e.g., `get_tasks_for_goal()`, `get_habits_for_event()`)

**When to use:**
- Finding entities by text query
- Filtering by status, category, or tags
- Domain-specific relationship queries

**Configuration:**
Uses `DomainConfig` for search behavior:
- `search_fields` - Fields to search (default: title, description)
- `search_order_by` - Default sort field
- `category_field` - Field for categorization

**Example:**
```python
from core.services.tasks import TasksSearchService

search = TasksSearchService(backend=backend)
result = await search.search("meditation", limit=10)
tasks_result = await search.get_tasks_for_goal(goal_uid)
```

---

### IntelligenceService

**File:** `{domain}_intelligence_service.py`
**Extends:** `BaseAnalyticsService[{Domain}Operations, {Domain}]`
**Protocol:** `{Domain}IntelligenceOperations`

**Responsibility:** Pure Cypher analytics (NO AI/LLM dependencies)

**Key Methods:**
- `analyze_{domain}_metrics()` - Performance analytics
- `get_with_context()` - Graph context retrieval
- `generate_{domain}_insights()` - Pattern detection
- `calculate_learning_impact()` - Learning metrics

**When to use:**
- Cross-domain graph analysis
- Performance metrics and statistics
- Pattern detection and insights
- Graph traversal with context

**Important:** Intelligence services use BaseAnalyticsService (graph analytics), not BaseAIService (LLM features)

**Example:**
```python
from core.services.tasks import TasksIntelligenceService

intel = TasksIntelligenceService(
    backend=backend,
    graph_intelligence_service=graph_intel,
)
metrics_result = await intel.analyze_task_learning_metrics(user_uid)
```

---

### RelationshipsService (UnifiedRelationshipService)

**File:** `core/services/relationships/unified_relationship_service.py`
**Extends:** N/A (standalone service)
**Protocol:** `RelationshipOperations`

**Responsibility:** Cross-domain graph relationships

**Key Methods:**
- `link_to_knowledge()` - Link entity to KU
- `link_to_goal()` - Link entity to Goal
- `link_to_life_path()` - Link entity to LifePath
- `get_related_uids()` - Query relationships
- `get_with_context()` - Get entity with graph context
- `create_semantic_relationship()` - Create semantic links

**When to use:**
- Creating relationships between entities
- Querying cross-domain connections
- Semantic relationship management

**Configuration:** Uses `DomainRelationshipConfig` from registry (e.g., `TASKS_CONFIG`, `GOALS_CONFIG`)

**Example:**
```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

rels = UnifiedRelationshipService(backend=backend, config=TASKS_CONFIG)
result = await rels.link_to_knowledge(task_uid, ku_uid, knowledge_score_required=0.8)
```

---

## Domain-Specific Sub-Services

These sub-services exist in specific Activity Domains:

### ProgressService

**Domains:** Tasks, Habits, Goals
**File:** `{domain}_progress_service.py`
**Extends:** `BaseService[{Domain}Operations, {Domain}]`

**Responsibility:** Progress tracking, completion, and milestones

**Key Methods:**
- `complete_{domain}()` - Mark as complete
- `track_progress()` - Update progress percentage
- `get_completion_stats()` - Completion statistics
- Domain-specific: `check_prerequisites()` (Tasks), `track_streak()` (Habits)

**When to use:**
- Completing entities
- Tracking progress over time
- Calculating completion rates

**Example:**
```python
from core.services.tasks import TasksProgressService

progress = TasksProgressService(backend=backend, event_bus=event_bus)
result = await progress.complete_task_with_cascade(task_uid, user_context)
```

---

### SchedulingService

**Domains:** Tasks, Habits, Goals, Events
**File:** `{domain}_scheduling_service.py`
**Extends:** `BaseService[{Domain}Operations, {Domain}]`

**Responsibility:** Smart scheduling and capacity management

**Key Methods:**
- `schedule_{domain}()` - Schedule entity
- `get_capacity_for_date()` - Available capacity
- `suggest_optimal_time()` - Time recommendations
- `reschedule()` - Move to different time

**When to use:**
- Scheduling entities for future dates
- Capacity planning
- Time optimization

**Example:**
```python
from core.services.tasks import TasksSchedulingService

scheduling = TasksSchedulingService(backend=backend)
result = await scheduling.create_task_with_context(request, user_context)
```

---

### PlanningService

**Domains:** Tasks, Habits
**File:** `{domain}_planning_service.py`
**Extends:** `BaseService[{Domain}Operations, {Domain}]`

**Responsibility:** Context-aware planning and recommendations

**Key Methods:**
- `get_actionable_{entities}_for_user()` - Ready-to-work entities
- `get_{domain}_dependencies_for_user()` - Prerequisite chains
- `suggest_{entities}()` - Context-based recommendations

**When to use:**
- Daily planning ("what should I work on?")
- Prerequisite-aware task ordering
- Context-based suggestions

**Example:**
```python
from core.services.tasks import TasksPlanningService

planning = TasksPlanningService(backend=backend, relationship_service=rels)
result = await planning.get_actionable_tasks_for_user(user_uid, user_context)
```

---

### LearningService

**Domains:** Habits, Choices, Goals
**File:** `{domain}_learning_service.py`
**Extends:** `BaseService[{Domain}Operations, {Domain}]`

**Responsibility:** Learning path integration and knowledge connections

**Key Methods:**
- `link_to_learning_path()` - Connect to LP
- `get_learning_opportunities()` - Find learning connections
- `track_knowledge_application()` - Knowledge usage

**When to use:**
- Integrating domain entities with curriculum (KU/LS/LP)
- Tracking knowledge application
- Finding learning opportunities

---

### CompletionsService

**Domains:** Habits only
**File:** `habits_completion_service.py`
**Extends:** `BaseService[HabitsOperations, Habit]`

**Responsibility:** Habit completion tracking and streak management

**Key Methods:**
- `record_completion()` - Log habit completion
- `get_completion_history()` - Historical completions
- `calculate_streak()` - Current streak length

**When to use:**
- Recording daily habit completions
- Querying completion history
- Calculating streaks

---

### EventIntegrationService

**Domains:** Habits only
**File:** `habits_event_integration_service.py`
**Extends:** `BaseService[HabitsOperations, Habit]`

**Responsibility:** Integration between Habits and Events domains

**Key Methods:**
- `create_event_from_habit()` - Generate event from habit
- `link_habit_to_event()` - Connect habit to existing event
- `sync_habit_schedule_to_events()` - Sync to calendar

**When to use:**
- Creating calendar events from habits
- Syncing habit schedules to Events domain
- Cross-domain habit-event integration

---

### AchievementService

**Domains:** Habits only
**File:** `habits_achievement_service.py`
**Extends:** `BaseService[HabitsOperations, Habit]`

**Responsibility:** Achievement badges and milestone tracking

**Key Methods:**
- `check_achievements()` - Detect earned achievements
- `award_achievement()` - Grant achievement badge
- `get_user_achievements()` - List earned achievements

**When to use:**
- Gamification features
- Milestone celebrations
- Achievement tracking

---

### RecommendationService

**Domains:** Goals only
**File:** `goals_recommendation_service.py`
**Extends:** `BaseService[GoalsOperations, Goal]`

**Responsibility:** Goal recommendations and suggestions

**Key Methods:**
- `suggest_related_goals()` - Find similar goals
- `recommend_next_steps()` - Action recommendations
- `find_complementary_goals()` - Complementary goals

**When to use:**
- Goal discovery
- Finding related/complementary goals
- Next-step suggestions

---

### AIService (Optional)

**Domains:** Tasks, Goals, Habits (optional in others)
**File:** `{domain}_ai_service.py`
**Extends:** `BaseAIService`

**Responsibility:** LLM-powered features (embeddings, semantic search, generation)

**Key Methods:**
- `generate_embeddings()` - Create vector embeddings
- `semantic_search()` - Vector similarity search
- `suggest_knowledge_connections()` - AI-powered suggestions

**When to use:**
- Semantic search features
- AI-powered recommendations
- Content generation

**Important:** Optional service - app works without AI features

---

## By Responsibility

Quick lookup table for finding the right sub-service:

| Responsibility | Sub-Service | Domains |
|----------------|-------------|---------|
| **CRUD operations** | CoreService | All (6) |
| **Search/filtering** | SearchService | All (6) |
| **Graph analytics** | IntelligenceService | All (6) |
| **Cross-domain relationships** | RelationshipsService | All (6) |
| **Completion tracking** | ProgressService | Tasks, Habits, Goals |
| **Scheduling** | SchedulingService | Tasks, Habits, Goals, Events |
| **Context-aware planning** | PlanningService | Tasks, Habits |
| **Learning integration** | LearningService | Habits, Choices, Goals |
| **Habit-specific completions** | CompletionsService | Habits only |
| **Habit-event integration** | EventIntegrationService | Habits only |
| **Achievement badges** | AchievementService | Habits only |
| **Goal recommendations** | RecommendationService | Goals only |
| **AI/LLM features** | AIService | Tasks, Goals, Habits (optional) |

---

## Access Patterns

### Pattern 1: Via Facade (Recommended for Production)

**Use the facade** for production code - it provides auto-generated delegation methods:

```python
from core.services.tasks_service import TasksService

# TasksService auto-delegates to sub-services
tasks = TasksService(backend=backend, ...)
result = await tasks.create_task(request, user_uid)  # Delegates to core.create_task()
```

**When to use:**
- Production routes
- Application code
- Any code that needs multiple sub-services

**Benefits:**
- Clean API (50+ methods at facade level)
- Explicit delegation methods — MyPy-native, no parallel protocol file
- Single import point

---

### Pattern 2: Direct Sub-Service Import (Testing/Composition)

**Import sub-services directly** for testing or custom composition:

```python
from core.services.tasks import TasksCoreService, TasksSearchService

# Direct instantiation for testing
core = TasksCoreService(backend=mock_backend)
result = await core.create_task(request, user_uid)
```

**When to use:**
- Unit tests (mock individual sub-services)
- Custom service composition
- Fine-grained control

**Benefits:**
- Easier mocking in tests
- Explicit dependencies
- Fine-grained control

---

### Pattern 3: Factory Pattern (Internal Use)

**Use factory** inside facade `__init__` to create common sub-services:

```python
from core.utils.activity_domain_config import create_common_sub_services

common = create_common_sub_services(
    domain="tasks",
    backend=backend,
    graph_intel=graph_intelligence_service,
    event_bus=event_bus,
)

self.core = common.core
self.search = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence
```

**When to use:**
- Implementing new facade services
- Reducing boilerplate in `__init__`

**Benefits:**
- Eliminates ~80 lines of repetitive init code
- Consistent sub-service creation
- Centralized configuration

---

## Sub-Service Count by Domain

| Domain | Total Sub-Services | Common (4) | Domain-Specific |
|--------|-------------------|------------|-----------------|
| Tasks | 7 | 4 | 3 (progress, scheduling, planning) |
| Goals | 9 | 4 | 5 (progress, scheduling, learning, recommendation, + custom) |
| Habits | 11 | 4 | 7 (progress, scheduling, planning, learning, completions, events, achievements) |
| Events | 8 | 4 | 4 (progress, scheduling, + custom) |
| Choices | 7 | 4 | 3 (learning, + custom) |
| Principles | 3 | 3 | 0 (core, search, intelligence only) |

**Most Complex:** Habits (11 sub-services)
**Simplest:** Principles (3 sub-services)

---

## Decision Tree: Which Sub-Service Should I Use?

```
What do you want to do?
│
├─ Create/Read/Update/Delete an entity?
│  └─ Use: CoreService
│
├─ Search or filter entities?
│  └─ Use: SearchService
│
├─ Analyze performance or get insights?
│  └─ Use: IntelligenceService
│
├─ Create/query cross-domain relationships?
│  └─ Use: RelationshipsService (UnifiedRelationshipService)
│
├─ Complete an entity or track progress?
│  └─ Use: ProgressService
│
├─ Schedule for future date or optimize timing?
│  └─ Use: SchedulingService
│
├─ Get context-aware recommendations?
│  └─ Use: PlanningService
│
├─ Integrate with learning path (KU/LS/LP)?
│  └─ Use: LearningService
│
├─ [Habits only] Track completions and streaks?
│  └─ Use: CompletionsService
│
├─ [Habits only] Sync with Events domain?
│  └─ Use: EventIntegrationService
│
├─ [Habits only] Award achievement badges?
│  └─ Use: AchievementService
│
├─ [Goals only] Get goal recommendations?
│  └─ Use: RecommendationService
│
└─ [Optional] Use AI/LLM features?
   └─ Use: AIService
```

---

## Common Patterns

### Pattern: Complete Entity with Cascade

```python
# TasksProgressService
result = await tasks.progress.complete_task_with_cascade(
    task_uid,
    user_context,
    actual_minutes=30,
    quality_score=4,
)
```

**Cascade:**
1. Update Task status to COMPLETED
2. Update UserContext statistics
3. Check and unblock dependent tasks
4. Trigger knowledge generation (if configured)
5. Publish TaskCompleted event

---

### Pattern: Context-Aware Creation

```python
# TasksSchedulingService
result = await tasks.scheduling.create_task_with_context(
    request,
    user_context,
)
```

**Context-aware features:**
1. Prerequisite checking
2. Learning path integration
3. Capacity management
4. Optimal scheduling

---

### Pattern: Graph Analytics

```python
# TasksIntelligenceService
metrics_result = await tasks.intelligence.analyze_task_learning_metrics(user_uid)
```

**Pure Cypher analytics:**
- No AI/LLM dependencies
- Graph traversal for cross-domain insights
- Performance metrics
- Pattern detection

---

## See Also

- [BaseService Method Index](/docs/reference/BASESERVICE_METHOD_INDEX.md) - Complete method listing
- [Service Topology](/docs/architecture/SERVICE_TOPOLOGY.md) - Architecture diagrams
- [Quick Start Guide](/docs/guides/BASESERVICE_QUICK_START.md) - New developer onboarding
- [BaseService Implementation](/core/services/base_service.py) - Source code
- [Example Facade Service](/core/services/tasks_service.py) - Explicit delegation pattern
- [Activity Domain Config](/core/utils/activity_domain_config.py) - Factory pattern

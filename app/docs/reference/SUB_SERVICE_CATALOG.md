# Sub-Service Responsibility Catalog

**Purpose:** Quick reference for understanding which sub-service handles which responsibilities across SKUEL's Activity Domain facades.

**Last Updated:** 2026-03-03

---

## Overview

SKUEL's Activity Domain services (Tasks, Goals, Habits, Events, Choices, Principles) use a **facade pattern** with 3-13 specialized sub-services per domain. This catalog maps responsibilities to sub-services so developers can quickly find the right service for their needs.

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
- `create()` - Create new entity (calls `_post_create` hook)
- `get()` - Get by UID
- `update()` - Update entity (calls `_post_update` hook)
- `delete()` - Delete entity (calls `_post_delete` hook)
- `list()` - List with filters
- `get_user_{entities}()` - Get all entities for user

**Hooks (override in subclass):**
- `_validate_create()` / `_validate_update()` — sync, pre-operation validation
- `_post_create()` / `_post_update()` / `_post_delete()` — async, post-operation (event publishing)

**When to use:**
- Creating, reading, updating, or deleting entities
- Basic queries without complex graph traversal
- Publishing domain events after state changes (via post-hooks)

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
from core.services.tasks import TasksLearningMetricsService

learning_metrics = TasksLearningMetricsService(
    backend=backend,
    relationship_service=rels,
)
metrics_result = await learning_metrics.analyze_task_learning_metrics(user_uid)
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

**Configuration:** Uses `DomainRelationshipConfig` from registry (e.g., `TASKS_CONFIG`, `GOAPS_CONFIG`)

**Example:**
```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

rels = UnifiedRelationshipService(backend=backend, config=TASKS_CONFIG)
result = await rels.link_to_knowledge(task_uid, ku_uid, knowledge_score_required=0.8)
```

---

### ActivityKnowledgeIntelligenceService

**File:** `core/services/knowledge/activity_knowledge_intelligence_service.py`
**Extends:** `BaseAnalyticsService`

**Responsibility:** Domain-agnostic knowledge intelligence for all 6 Activity Domains (shared singleton). Implements `KnowledgeIntelligenceOperations` protocol (4 methods) — the shared half of the ISP split (March 2026).

**Key Methods:**
- `get_knowledge_suggestions()` - Knowledge suggestions from entity patterns
- `generate_knowledge_from_entities()` - Knowledge units from completed entities
- `get_knowledge_prerequisites()` - Knowledge prerequisites for any entity
- `get_learning_opportunities()` - Learning opportunities from entity patterns

**When to use:**
- Analyzing how activities connect to knowledge
- Finding knowledge gaps across all activity domains
- Generating knowledge unit proposals from patterns

**Dependencies:**
- Entity-level backend (`NeoLabel.ENTITY`) — queries across ALL 6 activity domains
- `GraphIntelligenceService` (graph traversal)

**Wiring:** Created once in `services_bootstrap.py`, injected into all 6 Activity Domain facades as `self.knowledge_intelligence`. NOT a per-domain instance — one shared singleton. Each facade delegates its 4 knowledge intelligence methods to this service.

**Access:** Via any Activity Domain facade — `service.get_knowledge_suggestions(user_uid)`

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
- `get_{domain}_dependencies_for_user()` - Prerequisite chains (Tasks supports transitive traversal via `include_transitive=True, max_depth=N`)
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

### EventHandlerService

**Domains:** Tasks, Goals, Habits, Events, Choices, Principles + Learning Loop
**Files:** `task_event_handler_service.py`, `goal_event_handler_service.py`, `habit_event_handler_service.py`, `events_event_handler_service.py`, `choice_event_handler_service.py`, `principles_event_handler_service.py`, `learning_loop_event_handler_service.py`

**Responsibility:** Event-driven reactive logic (fire-and-forget handlers) with insight persistence to InsightStore

All 6 Activity Domain event handlers and the Learning Loop handler accept an optional `insight_store` parameter. When provided, handlers persist `PersistedInsight` nodes to Neo4j at key decision points — making pattern analysis queryable rather than write-only logs.

**Insight Persistence by Domain:**

| Domain | InsightType | Trigger |
|--------|------------|---------|
| **Tasks** | `COMPLETION_PATTERN` | Overdue task completed |
| **Tasks** | `IMBALANCE_DETECTED` | Priority inflation >60% |
| **Tasks** | `PRINCIPLE_ALIGNMENT` | Completed task aligned with principles |
| **Goals** | `COMPLETION_PATTERN` | Goal abandoned (HIGH for near-miss) |
| **Goals** | `IMBALANCE_DETECTED` | Progress stall (delta <1%) |
| **Goals** | `COMPLETION_PATTERN` | Approaching milestone (25/50/75/100%) |
| **Events** | `IMBALANCE_DETECTED` | Chronic rescheduling (4+ in 30 days) |
| **Events** | `IMBALANCE_DETECTED` | Schedule overcommitted (13+ events/week) |
| **Habits** | `DIFFICULTY_PATTERN` | 3+ consecutive misses |
| **Habits** | `STREAK_PATTERN` | Streak milestones |
| **Choices** | `DECISION_PATTERN` | High-confidence principle-aligned decision |
| **Choices** | `PRINCIPLE_ALIGNMENT` | Complex decision without principle guidance |
| **Principles** | `PRINCIPLE_CONFLICT` | Conflict revealed between principles |
| **Learning Loop** | `LEARNING_PROGRESS` | Submission iteration 2+ for same exercise |
| **Learning Loop** | `COMPLETION_PATTERN` | Feedback turnaround anomaly (fast/slow vs EMA) |
| **Learning Loop** | `MASTERY_ACHIEVED` | Quick mastery (≤2 attempts, <48h) |
| **Learning Loop** | `LEARNING_PROGRESS` | Persistent learner (3+ attempts to mastery) |

**Key Methods (Tasks):**
- `handle_task_completed()` - Duration calibration, overdue detection, principle alignment
- `handle_task_priority_changed()` - Categorization, cascade impact, inflation detection
- `handle_tasks_bulk_completed()` - Batch pattern classification

**Key Methods (Learning Loop):**
- `handle_submission_created()` - Iteration counting and classification
- `handle_report_submitted()` - Feedback turnaround EMA calibration and anomaly detection
- `handle_submission_approved()` - Mastery velocity classification

**When to use:**
- Reacting to domain events with fire-and-forget logic
- Cross-domain insight generation from event context
- Pattern detection that doesn't need to block the original operation

**See:** [INSIGHT_ACTION_TRACKING.md](/docs/patterns/INSIGHT_ACTION_TRACKING.md)

**Example:**
```python
from core.services.tasks import TaskEventHandlerService

handler = TaskEventHandlerService(backend=backend, relationship_service=rels, insight_store=insight_store)
# Subscribed via event_bus in bootstrap — not called directly

# Learning Loop handler — wired directly (not part of a facade)
from core.services.submissions import LearningLoopEventHandlerService

handler = LearningLoopEventHandlerService(backend=submissions_backend, insight_store=insight_store)
# Subscribes to: SubmissionCreated, ReportSubmitted, SubmissionApproved
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
- Integrating domain entities with curriculum (KU/PS/LP)
- Tracking knowledge application
- Finding learning opportunities

---

### CompletionsService

**Domains:** Habits only
**File:** `habits_completion_service.py`
**Extends:** Standalone (does NOT extend BaseService — secondary entity pattern)

**Responsibility:** Habit completion tracking and streak management

**Key Methods:**
- `record_completion()` - Log habit completion
- `get_completion_history()` - Historical completions
- `calculate_streak()` - Current streak length
- `export_completion_history()` - Export as CSV/JSON (delegates formatting to `core/utils/completion_exporter.py`)

**When to use:**
- Recording daily habit completions
- Querying completion history
- Calculating streaks
- Exporting completion data

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

### EventHandlerService

**Domains:** Tasks, Goals, Habits, Events, Choices, Principles
**Files:** `task_event_handler_service.py`, `goal_event_handler_service.py`, `habit_event_handler_service.py`, `events_event_handler_service.py`, `choice_event_handler_service.py`, `principles_event_handler_service.py`

**Responsibility:** Event-driven reactive handlers (fire-and-forget)

**Key Methods (Goals):**
- `handle_goal_achieved()` - Recommendations, duration calibration, principle alignment
- `handle_goal_abandoned()` - Abandonment classification, structured logging
- `handle_goal_progress_updated()` - Stall detection, milestone proximity, trigger logging

**Key Methods (Events):**
- `handle_event_completed()` - Attendance time-of-day tracking, goal alignment
- `handle_event_rescheduled()` - Rescheduling pattern detection (rare/occasional/chronic)
- `handle_event_created()` - Scheduling density monitoring, overcommitment warnings

**Key Methods (Choices):**
- `handle_choice_outcome_recorded()` - Outcome quality analysis, principle alignment correlation
- `handle_choice_made()` - Decision pattern tracking, confidence analysis, insight persistence

**When to use:**
- Reacting to domain events
- Cross-domain insight generation
- Pattern detection and analytics logging

---

### AIService (Optional)

**Domains:** All 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) + PS and LP (Curriculum)
**File:** `{domain}_ai_service.py`
**Extends:** `BaseAIService`

**Responsibility:** LLM-powered features (embeddings, semantic search, generation)

**Key Methods:**
- `generate_embeddings()` - Create vector embeddings
- `semantic_search()` - Vector similarity search
- `suggest_knowledge_connections()` - AI-powered suggestions

**PS-specific methods (PsAIService):**
- `suggest_step_applications(ps_uid)` — LLM categorized by task/habit/goal/real-world. Returns `StepApplicationsResult`.
- `suggest_learning_sequence(ps_uid, max_suggestions=5)` — prerequisite/next-step recommendations. Returns `StepLearningSequenceResult`.
- `search_by_semantic_query(query_text, limit, min_score)` — two-tier semantic/keyword search.
- `explain_step(ps_uid, target_level)` — 6 target levels: beginner/intermediate/advanced/standard/brief/detailed.
- `suggest_practice_activities(ps_uid)` — JSON-based practice suggestions.
- TypedDicts: `StepApplicationsResult`, `StepLearningSequenceResult` (`core/ports/query_types.py`)

**When to use:**
- Semantic search features
- AI-powered recommendations
- Content generation

**Important:** Optional service - app works without AI features (`INTELLIGENCE_TIER=core` sets `.ai` to `None` on all facades)

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
| **Event-driven handlers** | EventHandlerService | Tasks, Goals, Habits, Events, Choices, Principles |
| **AI/LLM features** | AIService | All 6 Activity Domains + PS, LP (optional — FULL tier) |
| **LLM routing** | UnifiedLLMCaller | Journals, Reports (routes gpt*/claude* models) |
| **Instruction resolution** | InstructionResolver | Journals, Batch (custom > exercise > mode > default) |
| **Batch audio transcription** | BatchTranscriptionService | Journals batch (Tier 1: audio → txt) |
| **Batch LLM processing** | BatchProcessingService | Journals batch (Tier 2: txt → md) |

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
from core.services.activity_domain_config import create_common_sub_services

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

| Domain | Total Sub-Services | Common (4+1 shared) | Domain-Specific |
|--------|-------------------|------------|-----------------|
| Tasks | 11 | 5 | 6 (progress, scheduling, planning, productivity, learning_metrics, event_handler) |
| Goals | 9 | 5 | 4 (progress, scheduling, learning, event_handler) |
| Habits | 14 | 5 | 9 (progress, scheduling, planning, learning, completions, events, event_handler, patterns, goal_analytics) |
| Events | 10 | 5 | 5 (progress, scheduling, learning, habit_integration, event_handler) |
| Choices | 7 | 5 | 2 (learning, event_handler) |
| Principles | 10 | 5 | 5 (alignment, learning, reflection, planning, event_handler) |

**Common 5:** core, search, relationships, intelligence (created by factory) + knowledge_intelligence (shared singleton)
**Most Complex:** Habits (14 sub-services)
**Simplest:** Choices (7 sub-services)

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
├─ Integrate with learning path (KU/PS/LP)?
│  └─ Use: LearningService
│
├─ [Habits only] Track completions and streaks?
│  └─ Use: CompletionsService
│
├─ [Habits only] Sync with Events domain?
│  └─ Use: EventIntegrationService
│
├─ [Habits only] Award achievement badges (streak + aggregate)?
│  └─ Use: EventHandlerService (streak via HabitStreakMilestone, aggregate via HabitCompleted)
│
├─ [Goals only] React to goal events (achievements, abandonment)?
│  └─ Use: EventHandlerService
│
├─ [Choices only] React to choice events (outcomes, decisions)?
│  └─ Use: EventHandlerService
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
# TasksLearningMetricsService
metrics_result = await tasks.learning_metrics.analyze_task_learning_metrics(user_uid)
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
- [Activity Domain Config](/core/services/activity_domain_config.py) - Factory pattern

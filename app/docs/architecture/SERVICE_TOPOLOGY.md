# Service Architecture: File Organization & Topology

**Purpose:** File organization rules, import guidelines, and visual architecture diagrams for `/core/services/`.

**Last Updated:** 2026-04-10

---

## Table of Contents

- [File Organization](#file-organization)
- [Import Guidelines](#import-guidelines)
- [BaseService + Mixins Architecture](#baseservice--mixins-architecture)
- [Activity Domain Facade Pattern](#activity-domain-facade-pattern)
- [Sub-Service Communication](#sub-service-communication)
- [Data Flow Examples](#data-flow-examples)
- [Dependency Graphs](#dependency-graphs)
- [Factory Pattern Architecture](#factory-pattern-architecture)
- [Configuration Architecture](#configuration-architecture)
- [Summary](#summary)

---

## File Organization

> **Core Principle:** "Facade at root, implementation in folder"

### 1. DUAL-LOCATION Services

Services with **both** a root-level facade AND a subfolder of sub-services.

| Category | Services | Sub-service count |
|----------|----------|-------------------|
| Activity (6) | tasks, goals, habits, events, choices, principles | 7–13 per domain |
| Curriculum (3) | ku, lp, ls | 4–11 per domain |
| Cross-Cutting (4) | user, askesis, finance, lifepath | varies |

**Structure:**
```
/core/services/
  tasks_service.py          # Facade (public API)
  tasks/                    # Implementation folder
    __init__.py             # Re-exports sub-services
    tasks_core_service.py
    tasks_search_service.py
    tasks_intelligence_service.py
    tasks_progress_service.py
    tasks_scheduling_service.py
    tasks_planning_service.py
    tasks_ai_service.py
    task_relationships.py   # Relationship config (not a service)
```

**Rationale:** The facade provides a stable public API while internal implementation evolves freely. External code imports `TasksService`; sub-services are implementation details.

---

### 2. FOLDER-ONLY Services

Infrastructure modules with no root-level facade.

| Folder | Purpose |
|--------|---------|
| `relationships/` | UnifiedRelationshipService + 6 mixin files |
| `sharing/` | UnifiedSharingService (entity-agnostic sharing) |
| `search/` | Unified search across all domains |
| `user_entry/` | UserEntry domain (ADR-054) — submissions + journal pipeline: CRUD, processing, learning-loop reads |
| `report/` | Teacher/AI reports, activity reports, review queue |
| `output/` | InstructionResolver (unified instruction resolution) |
| `transcription/` | TranscriptionService + BatchTranscriptionService + BatchProcessingService |
| `mixins/` | 7 BaseService mixin files |
| `intelligence/` | Shared `_CoreIntelligenceMixin` (mechanism-B `get_with_context`) + analytics helpers |
| `infrastructure/` | Cross-cutting helpers — `PrerequisiteChecker` (readiness + `build_learning_requirements` lens — see `/docs/patterns/PREREQUISITE_CHECKER_PATTERN.md`), `LearningAlignmentBridge`, `SemanticRelationshipLinker` |
| `ingestion/` | UnifiedIngestionService |
| *(no `query/`)* | Query builders are **not** in `core/services/` — they live in `adapters/persistence/neo4j/query/` (`UnifiedQueryBuilder`, `cypher/` `build_*` functions) and `adapters/persistence/neo4j/query_builders/` (`QueryBuilder` + 5 sub-services) |
| `insight/` | Insight analytics |
| `dsl/` | Activity DSL parser & engine |
| `lateral_relationships/` | Lateral relationship graph queries |
| `groups/` | Group CRUD and membership |
| `exercises/` | Exercise CRUD and curriculum linking |
| `lp_intelligence/` | Learning path intelligence |
| `analytics/` | Domain analytics |
| `background/` | Background task workers |
| `notifications/` | Notification services |
| `cross_domain/` | `CrossDomainQueryService` — 9 single-Cypher cross-domain read methods returning frozen typed dataclasses. Takes only `QueryExecutor`. |

---

### 3. ROOT-ONLY Services

Standalone services without subfolders.

| Category | Services |
|----------|----------|
| **Base Classes** | `base_service.py`, `base_analytics_service.py`, `base_ai_service.py`, `base_planning_service.py` |
| **AI/LLM** | `llm_caller.py` (UnifiedLLMCaller), `llm_service.py`, `embeddings_service.py` (EmbeddingsService), `neo4j_vector_search_service.py`, `context_aware_ai_service.py` — all port-based; the vendor SDK clients live below the boundary in `adapters/external/llm/{openai,anthropic}_adapter.py` + `adapters/external/embeddings/{openai,huggingface}_adapter.py` behind the `create_chat_client()` + `create_embedding_client()` chokepoints (W1 / ADR-063, ADR-068) |
| **Analytics** | `analytics_service.py`, `cross_domain_analytics_service.py` |
| **Knowledge Analytics** | `knowledge/knowledge_pattern_analyzer.py` (generic 5-pattern engine), `tasks/task_knowledge_analyzer.py` (Task-specific, composes generic) |
| **Askesis Secondary** | `askesis_ai_service.py`, `askesis_citation_service.py` |
| **KU Generation Pipeline** | `entity_chunking_service.py`, `insight/insight_generation_service.py` (shell + 3 mixins, July 2026 decomposition), `entity_inference_service.py`, `ku_intelligence_service.py` |
| **Calendar** | `calendar_service.py`, `calendar_optimization_service.py` (shell + `calendar_optimization_strategies.py` mixin, July 2026 decomposition; models in `core/models/calendar_optimization.py`) |
| **Content** | `conversion_service.py`, `content_enrichment_service.py` |
| **User Secondary** | `user_progress_service.py`, `user_relationship_service.py` |
| **System** | `system_service.py`, `schema_service.py`, `performance_optimization_service.py` |
| **Visualization** | `core/services/visualization_service.py` (pure formatter — no domain deps) + `core/services/analytics/visualization_aggregation_service.py` (data fetching + aggregation — delegates formatting to VisualizationService) |
| **Config/Helpers** | `domain_config.py`, `query_builder.py`, `entity_timestamp_mixin.py` |

---

### When to Use Each Pattern

| Pattern | Use When |
|---------|----------|
| **DUAL** | Complex domain with multiple responsibilities; external API stability needed |
| **FOLDER-ONLY** | Infrastructure or processing module; no facade needed |
| **ROOT-ONLY** | Single-responsibility service; base class; config helper |

---

## Import Guidelines

### Domain Services (DUAL pattern)

**External code imports the facade:**
```python
# CORRECT — import from facade
from core.services.tasks_service import TasksService
from core.services.goals_service import GoalsService
```

**Sub-services can be imported directly when needed (e.g., tests):**
```python
# ALLOWED — direct import for specific testing or composition
from core.services.tasks import TasksCoreService
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
```

### Infrastructure (FOLDER-ONLY)

```python
from core.ports import BackendOperations, TasksOperations
from core.services.relationships import UnifiedRelationshipService
from core.services.search.search_router import SearchRouter
from core.services.sharing import UnifiedSharingService
```

### Utilities (ROOT-ONLY)

```python
from core.services.base_service import BaseService
from core.services.llm_service import LLMService
from core.services.knowledge.knowledge_pattern_analyzer import KnowledgePatternAnalyzer
from core.services.tasks.task_knowledge_analyzer import TaskKnowledgeAnalyzer
```

### Service Bootstrap

All services are composed in `/services_bootstrap/`. This package:
- Imports all facades and utilities
- Creates dependency graph
- Instantiates services with proper dependencies
- Exposes the `Services` dataclass with all service instances (~72 typed fields, zero `Any`)

---

## BaseService + Mixins Architecture

### Mixin Composition Hierarchy

```
BaseService[B: BackendOperations, T: DomainModelProtocol]
    │
    ├─ ConversionHelpersMixin      ← Foundation (no dependencies)
    │   └─ Methods: _to_domain_model(), _to_domain_models(), _validate_required_user_uid()
    │
    ├─ CrudOperationsMixin          ← Depends on ConversionHelpersMixin
    │   └─ Methods: create(), get(), update(), delete(), list()
    │                verify_ownership(), get_for_user(), update_for_user()
    │
    ├─ SearchOperationsMixin        ← Depends on ConversionHelpersMixin
    │   └─ Methods: search(), get_by_status(), get_by_category()
    │                search_by_tags(), get_by_relationship()
    │
    ├─ RelationshipOperationsMixin  ← Depends on ConversionHelpersMixin
    │   └─ Methods: add_relationship(), get_relationships(), traverse()
    │                get_prerequisites(), get_enables()
    │
    ├─ TimeQueryMixin               ← Depends on ConversionHelpersMixin
    │   └─ Methods: get_user_items_in_range(), get_upcoming(), get_overdue(), get_active()
    │
    └─ ContextOperationsMixin       ← Depends on CrudOperationsMixin
        └─ Methods: get_with_content(), get_with_context()
```

**File layout** (`/core/services/mixins/`):

```
mixins/
  conversion_helpers_mixin.py    (no dependencies)
  crud_operations_mixin.py       (uses conversion_helpers)
  search_operations_mixin.py     (uses conversion_helpers)
  relationship_operations_mixin.py (uses conversion_helpers)
  time_query_mixin.py            (uses conversion_helpers)
  context_operations_mixin.py    (uses crud_operations)
```

**Key Insight:** `ConversionHelpersMixin` is the foundation — 4 of 6 mixins depend on it directly.

---

## Activity Domain Facade Pattern

### Facade + Sub-Services Structure (Tasks Example)

```
TasksService (Facade)
├─ Inherits: BaseService[TasksOperations, Task]
├─ Provides: ~35 explicit async delegation methods
└─ Composes 10 sub-services:
    │
    ├─ self.core: TasksCoreService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: CRUD operations, event publishing
    │   └─ Methods: create_task(), get_task(), update_task(), delete_task()
    │
    ├─ self.search: TasksSearchService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: Search and discovery
    │   ├─ Config: _config = create_activity_domain_config(...)
    │   └─ Methods: search(), get_tasks_for_goal(), get_prioritized()
    │
    ├─ self.progress: TasksProgressService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: Progress tracking, completion
    │   └─ Methods: complete_task_with_cascade(), check_prerequisites()
    │
    ├─ self.scheduling: TasksSchedulingService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: Scheduling and capacity management
    │   └─ Methods: create_task_with_context(), suggest_learning_aligned_tasks()
    │
    ├─ self.planning: TasksPlanningService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: Context-aware recommendations
    │   └─ Methods: get_task_dependencies_for_user(), get_actionable_tasks_for_user(), get_learning_tasks_for_user()
    │
    ├─ self.relationships: UnifiedRelationshipService
    │   ├─ Extends: N/A (standalone service)
    │   ├─ Responsibility: Cross-domain relationships
    │   └─ Methods: create_relationship(key, …), get_related_uids(key, uid), get_with_context()
    │
    ├─ self.intelligence: TasksIntelligenceService
    │   ├─ Extends: BaseAnalyticsService[TasksOperations, Task] + 4 mixins
    │   ├─ Responsibility: Task-specific analytics (behavioral, performance, cross-domain context,
    │   │                  dual-track productivity via _DualTrackMixin)
    │   ├─ Methods: get_behavioral_insights(), get_performance_analytics(), get_domain_insights(),
    │   │           assess_productivity_dual_track() (ADR-030, #259)
    │   └─ NOTE: Knowledge methods extracted to ActivityKnowledgeIntelligenceService (March 2026).
    │           TasksProductivityService was shelved 2026-03-28 — dual-track lives in _dual_track_mixin.py
    │
    └─ self.event_handler: TaskEventHandlerService
        ├─ Extends: N/A (standalone service)
        ├─ Responsibility: Event-driven reactive handlers (fire-and-forget)
        └─ Methods: handle_task_completed(), handle_task_priority_changed(), handle_tasks_bulk_completed()
```

### All Activity Domains — Sub-Service Counts

```
Activity Domain Facades (6 total)
│
├─ TasksService     (9 sub-services + 1 facade mixin)
│   └─ core, search, progress, scheduling, planning, learning, intelligence,
│      event_handler, knowledge_intelligence
│   └─ mixins: _OrchestrationMixin
│
├─ GoalsService      (10 sub-services + 1 facade mixin)
│   └─ core, search, progress, scheduling, learning, planning, intelligence, event_handler, knowledge_intelligence, ai
│   └─ mixins: _OrchestrationMixin
│
├─ HabitsService    (13 sub-services + 3 facade mixins)  ← Most complex
│   └─ core, search, progress, scheduling, planning, learning, completions,
│      event_integration, event_handler, intelligence, knowledge_intelligence, ai, patterns
│   └─ mixins: _CompletionMixin, _EnrichmentMixin, _OrchestrationMixin
│
├─ EventsService     (10 sub-services)
│   └─ core, search, progress, scheduling, learning, habit_integration, event_handler, intelligence, knowledge_intelligence, ai
│
├─ ChoicesService    (7 sub-services + 2 facade mixins)
│   └─ core, search, learning, intelligence, event_handler, knowledge_intelligence, ai
│   └─ mixins: _OptionManagementMixin
│
└─ PrinciplesService (10 sub-services + 3 facade mixins)
    └─ core, search, alignment, learning, planning, reflection, intelligence, knowledge_intelligence, ai, event_handler
    └─ mixins: _EmbodimentMixin, _GravityMixin, _EnrichmentMixin
```

**Pattern:** All 6 domains share the same 7 common sub-services via factory: core, search, relationships,
intelligence (skippable via `skip={}`) + event_handler, learning, knowledge_intelligence
(always auto-wired). The shape is uniform — no domain opts out. `KnowledgeIntelligenceDelegationMixin` remains for the 4
delegation method shortcuts but is no longer the wiring path for `knowledge_intelligence`. Cross-domain reads spanning 2+ domain labels go through `CrossDomainQueryService` (`core/services/cross_domain/`), injected as a constructor dependency into facades that need it (Goals, Habits, Choices, Principles). Activity domain stat computation centralized in `core/utils/activity_stats.py` (April 2026).

The shared `knowledge_intelligence` wiring is the first production realization of the [Shared Signal pattern](../patterns/SHARED_SIGNAL_PATTERN.md) — one singleton producer, narrow protocol, delegation mixin on every Activity Domain facade.

**Shared Knowledge Intelligence (singleton):**
```
ActivityKnowledgeIntelligenceService (core/services/knowledge/)
├─ Extends: BaseAnalyticsService[Any, Entity]
├─ Backend: UniversalNeo4jBackend[Entity] with NeoLabel.ENTITY
│   └─ find_by(user_uid=...) matches the denormalized user_uid PROPERTY (not the :OWNS edge)
│      across all domains (shared entities lack user_uid and naturally filter out). The
│      property is kept aligned to the canonical (User)-[:OWNS]-> owner by the live write-paths
│      + the 2026-06 backfill (USER_UID_OWNS_BACKFILL_2026-06.md); :OWNS is authoritative.
├─ Responsibility: Domain-agnostic knowledge suggestions, prerequisites, learning opportunities
├─ Methods: get_knowledge_suggestions(), generate_knowledge_from_entities(),
│           get_knowledge_prerequisites(), get_learning_opportunities()
└─ Delegation: KnowledgeIntelligenceDelegationMixin (core/services/mixins/)
               — all 6 facades inherit this mixin instead of repeating delegation methods
```

**Learning Loop Intelligence:** `LearningLoopEventHandlerService` follows the same fire-and-forget pattern but is wired directly (not part of a facade). Subscribes to `UserEntryCreated`, `ReportSubmitted`, `UserEntryApproved`. Persists `LEARNING_PROGRESS`, `COMPLETION_PATTERN`, and `MASTERY_ACHIEVED` insights. File: `core/services/user_entry/learning_loop_handler.py`.

Its read-side peer is `LearningLoopQueryService` (file: `core/services/user_entry/learning_loop_query.py`), which exposes learning-loop reads that traverse Interaction/Exercise/Report edges — e.g. `get_submissions_for_path_step()` (delegating to `UserEntryBackend.get_entries_for_path_step()`). Keeping these reads here means the generic entity search `UserEntryService` inherits from `BaseService` stays free of learning-loop shape. New learning-loop reads land in the query service.

---

## Sub-Service Communication

### Internal Communication Flow

```
Route Layer
    │
    ▼
┌────────────────────────────────────────────────────────┐
│ TasksService (Facade)                                  │
│                                                         │
│  # Explicit delegation methods (February 2026)        │
│  async def create_task(self, *args, **kwargs):        │
│      return await self.core.create_task(*args, **kwargs) │
│                                                         │
│  # NOTE: there is deliberately no `async def search`   │
│  # here — `self.search` is the sub-service instance    │
│  # and shadows the name. Callers use SearchRouter, or  │
│  # `tasks_service.search.<domain_method>()`.           │
│                                                         │
│  async def complete_task(self, *args, **kwargs):      │
│      return await self.progress.complete_task(*args, **kwargs) │
└───────────┬────────────────────────────────────────────┘
            │
            ├─────────────────┬─────────────────┬──────────────────┐
            │                 │                 │                  │
            ▼                 ▼                 ▼                  ▼
    ┌───────────────┐ ┌──────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │ CoreService   │ │ SearchService│ │ ProgressService │ │ IntelligenceServ│
    │               │ │              │ │                 │ │                 │
    │ create_task() │ │ search()     │ │ complete_task() │ │ analyze_metrics()│
    └───────┬───────┘ └──────┬───────┘ └────────┬────────┘ └────────┬────────┘
            │                │                  │                   │
            └────────────────┴──────────────────┴───────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────────┐
                    │ UniversalNeo4jBackend[Task]                                │
                    │                                                             │
                    │  create(), get(), list(), find_by(), update(), delete()   │
                    └────────────────────────┬───────────────────────────────────┘
                                             │
                                             ▼
                                        Neo4j Database
```

**Key Observations:**

1. **Facade → Sub-Service** — Explicit one-line `async def` delegation methods (not dynamic)
2. **Sub-Service → Backend** — Direct calls to `UniversalNeo4jBackend`
3. **Sub-Service ↔ Sub-Service** — Occasional cross-service calls (e.g., progress calls relationships)
4. **Backend → Neo4j** — Single path to database

### When a caller may reach a sub-service

`facade.<sub>.<method>()` from a route, a UI module, an orchestrator or the composition
root is **allowed and is the documented API** — it is how the domain guides
(`docs/domains/*.md`), the curriculum/search/analytics skills and
`ADR-030` all show these operations being called. Prefer the facade method when one
exists; reach the sub-service when it does not. There is no facade-only rule, no lint
rule enforcing one, and none should be added:

- **`search()` cannot be a facade method.** `self.search` is the sub-service instance
  attribute and shadows the name (`tasks_service.py:343` — *"This shadows
  `BaseService.search()`, intentionally"*). `SearchRouter._get_search_service` depends on
  the attribute being non-callable.
- **Bound-method references are a declared contract, not drift.**
  `ActivityUIConfig.dual_track_assess` / `.list_categories` document
  `goals_service.intelligence.assess_progress_dual_track` and
  `goals_service.search.list_user_categories` **as their field values**
  (`adapters/inbound/activity_ui_factory.py:75-89`).
- **The composition root subscribes `handle_*` methods directly.** That is published
  architecture, not a bypass — see
  [LEARNING_PROGRESS_EVENT_CHAIN.md](LEARNING_PROGRESS_EVENT_CHAIN.md) § Bootstrap Wiring,
  and the same carve-out SKUEL021 already makes in prose.

Two things a caller must **not** do, both narrow and both already stated elsewhere:

- **Generic text search must go through `SearchRouter`**, never
  `domain_service.search.search()` from a route
  (`.claude/skills/skuel-search-architecture/PATTERNS.md`). Domain-*specific* search
  methods (`ps_service.search.get_standalone_steps()`) are called on the service directly.
- **Never reach the persistence backend through a service** —
  `facade.core.backend.<method>()` puts a caller past the hexagonal boundary
  (`UniversalNeo4jBackend`, ADR-044) with no service semantics in between. If a caller
  needs a batch read, the facade owns it: `PsService.get_steps_batch`,
  `KuService.get_kus_batch`.

### Cross-Service Dependencies (Tasks Example)

```
TasksCoreService        ← Depends on: entity_inference_service (optional), event_bus (optional)
TasksProgressService    ← Depends on: event_bus (optional)
TasksSchedulingService  ← Self-contained
TasksPlanningService    ← Depends on: relationship_service (UnifiedRelationshipService)
TasksSearchService      ← Self-contained (uses DomainConfig)
TasksIntelligenceService← Depends on: graph_intel, relationship_service, TaskKnowledgeAnalyzer (owned internally)
UnifiedRelationshipService ← Depends on: relationship_config (TASKS_CONFIG)
```

**Pattern:** Most sub-services are self-contained. Cross-service dependencies are explicit in `__init__`.

### Cross-Domain Post-Wiring (Circular Dependencies)

When a facade needs another domain's service, declare `None` in `__init__` and post-wire in `services_bootstrap/compose.py`:

```
HabitsService.__init__:  self.goals_service = None
                         self.goal_analytics.goals_service = None

services_bootstrap/compose.py:  habits.goals_service = goals       # facade-level
                                habits.goal_analytics.goals_service = goals  # sub-service-level
```

```

```
GoalsIntelligenceService.__init__:  self.habits_service = None

services_bootstrap/compose.py:  goals.intelligence.habits_service = habits  # sub-service-level
```

**Rule:** Routes never pass cross-domain services as parameters. Orchestration methods (e.g., `create_with_goal_links`) use `self.*_service` internally.

---

## Data Flow Examples

### Example 1: Create Task

```
1. HTTP Request
   POST /api/tasks/create
   Body: {title: "Learn BaseService", priority: "high"}
   │
   ▼
2. Route Handler
   @rt("/api/tasks/create")
   async def create_task_route(request, body: TaskCreateRequest):
       user_uid = require_authenticated_user(request)
       result = await services.tasks.create_task(body, user_uid)
       return {"task_uid": result.value.uid}
   │
   ▼
3. Facade Delegation
   TasksService.create_task()
       └─ Delegates to: self.core.create_task()
   │
   ▼
4. Core Service
   TasksCoreService.create_task()
       ├─ Validates request
       ├─ Infers knowledge (entity_inference_service)
       ├─ Converts to domain model (Task)
       ├─ Calls backend.create()
       └─ Publishes TaskCreated event
   │
   ▼
5. Backend
   UniversalNeo4jBackend[Task].create()
       ├─ Converts Task → Neo4j properties
       ├─ Generates Cypher CREATE query
       └─ Executes via driver
   │
   ▼
6. Neo4j Database
   CREATE (t:Entity:Task {uid: "task_learn-baseservice_abc123", ...})
   CREATE (u:User {uid: "user_mike"})-[:OWNS]->(t)
   │
   ▼
7. Response
   Result.ok(Task(uid="task_learn-baseservice_abc123", ...))
```

---

### Example 2: Complete Task with Cascade

```
1. HTTP Request
   POST /api/tasks/task_learn-baseservice_abc123/complete
   Body: {actual_minutes: 30, quality_score: 4}
   │
   ▼
2. Route Handler
   result = await services.tasks.complete_task_with_cascade(
       task_uid, user_context, actual_minutes, quality_score
   )
   │
   ▼
3. Facade (explicit delegation)
   TasksService.complete_task_with_cascade()
       └─ Delegates to: self.progress.complete_task_with_cascade()
   │
   ▼
4. Progress Service
   TasksProgressService.complete_task_with_cascade()
       ├─ Verifies ownership
       ├─ Updates Task status → COMPLETED
       ├─ Checks prerequisites → unblocks dependent tasks
       └─ Publishes: TaskCompleted event
   │
   ├─────────────────────┐
   │                     │
   ▼                     ▼
5a. Backend          5b. Event Bus
   update_task()         TaskCompleted
       │                     └─> Listeners:
       ▼                         - UserContextService (update stats)
   Neo4j UPDATE              - TaskKnowledgeAnalyzer (track mastery)
                             - TaskEventHandlerService
                                 (handle_task_completed →
                                  step 4: _trigger_knowledge_generation)
```

**Key Observations:**
- **Cascade handled by ProgressService** — updates UserContext, unblocks tasks, publishes events
- **Event-driven side effects** — listeners react to `TaskCompleted`

---

### Example 3: Search Tasks for Goal

```
1. GET /api/tasks/search?goal_uid=goal_health-2024_xyz
   │
   ▼
2. Route → services.tasks.get_tasks_for_goal(goal_uid)
   │
   ▼
3. Facade → self.search.get_tasks_for_goal(goal_uid)
   │
   ▼
4. TasksSearchService
   MATCH (t:Task)-[:FULFILLS_GOAL]->(g:Goal {uid: $goal_uid})
   WHERE (u:User {uid: $user_uid})-[:OWNS]->(t)
   RETURN t
   │
   ▼
5. Backend converts Neo4j records → list[Task]
```

---

## Dependency Graphs

### Service-Level Dependencies

```
Routes / Application Code
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ services_bootstrap/  (Services dataclass)                 │
│                                                           │
│  services.tasks    = TasksService(...)                   │
│  services.goals    = GoalsService(...)                    │
│  services.ku       = KuService(...)                      │
│  services.user     = UserService(...)                    │
│  services.sharing  = UnifiedSharingService(...)          │
│  ...                                                      │
└───────┬──────────────────────────────────────────────────┘
        │
        ├─────────────────┬──────────────────┬────────────────┐
        │                 │                  │                │
        ▼                 ▼                  ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
│TasksService  │  │GoalsService  │  │KuService    │  │UserService   │
└──────┬───────┘  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘
       │                 │                 │                │
       └────────────┬────┴─────────────────┴────────────────┘
                    │
                    ▼
        ┌────────────────────────────────┐
        │ Shared Infrastructure Services │
        │                                 │
        │  - UniversalNeo4jBackend       │
        │  - UnifiedRelationshipService  │
        │  - UnifiedSharingService       │
        │  - KnowledgePatternAnalyzer    │
        │  - EventBus                    │
        └────────────────────────────────┘
```

### Module-Level Dependencies

```
/core/services/
│
├─ base_service.py
│   └─ Uses: mixins/ (6 mixin files)
│
├─ mixins/
│   ├─ conversion_helpers_mixin.py    (no dependencies)
│   ├─ crud_operations_mixin.py       (uses conversion_helpers)
│   ├─ search_operations_mixin.py     (uses conversion_helpers)
│   ├─ relationship_operations_mixin.py (uses conversion_helpers)
│   ├─ time_query_mixin.py            (uses conversion_helpers)
│   └─ context_operations_mixin.py    (uses crud_operations)
│
├─ tasks/
│   ├─ tasks_core_service.py          (extends BaseService)
│   ├─ tasks_search_service.py        (extends BaseService)
│   ├─ tasks_progress_service.py      (extends BaseService)
│   ├─ tasks_scheduling_service.py    (extends BaseService)
│   ├─ tasks_planning_service.py      (extends BaseService)
│   ├─ tasks_intelligence_service.py  (extends BaseAnalyticsService)
│   └─ tasks_ai_service.py            (extends BaseAIService)
│
├─ tasks_service.py                   (facade — uses tasks/ sub-services)
│
├─ domain_config.py                   (DomainConfig dataclass + factory functions)
│
├─ relationships/                     (decomposed shell + 6 mixin files)
│   ├─ unified_relationship_service.py  (shell: constructor, generic CRUD, typed links)
│   ├─ _batch_operations_mixin.py       (N+1 elimination helpers)
│   ├─ _ordered_relationships_mixin.py  (curriculum hierarchy + edge metadata)
│   ├─ _intelligence_mixin.py           (graph intelligence, semantic, cross-domain context)
│   ├─ _life_path_mixin.py              (SERVES_LIFE_PATH)
│   ├─ planning_mixin.py                (generic UserContext-aware planning + scoring)
│   └─ _domain_planning_mixin.py        (6 Activity Domain-specific planning methods)
│
├─ sharing/
│   └─ unified_sharing_service.py     (entity-agnostic SHARES_WITH + SHARED_WITH_GROUP)
│
├─ user_entry/                            (ADR-054 — replaces submissions/ + journal/)
│   ├─ user_entry_service.py              (entry point — UserEntryService facade over UserEntryBackend)
│   ├─ assessment_service.py             (AssessmentService — reads a student's received teacher assessments)
│   ├─ user_entry_processing_service.py  (UserEntryProcessingService — transcription/LLM → UserEntry)
│   ├─ exercise_linker.py                (UserEntryExerciseLinker — links UserEntry to Exercise)
│   ├─ audience_resolver.py              (AudienceResolver — shared sharing/audience helper)
│   ├─ learning_loop_handler.py          (LearningLoopEventHandlerService — event-driven writes)
│   └─ learning_loop_query.py            (read-side: Interaction/Report traversals)
│
├─ output/
│   └─ instruction_resolver.py        (unified instruction resolution)
│
├─ transcription/
│   ├─ transcription_service.py       (single-file Deepgram transcription)
│   └─ batch_transcription_service.py (batch audio → txt)
│
└─ report/
    ├─ entry_report_service.py     (entry point — uses UnifiedLLMCaller)
    ├─ activity_report_service.py     (CRUD for ActivityReport — delegates to ActivityReportBackend)
    ├─ review_queue_service.py        (ReviewRequest node management)
    ├─ teacher_review_service.py      (delegates to UserEntryBackend, EntryReportBackend, ExerciseBackend, GroupBackend)
    ├─ progress_report_generator.py   (LLM → processed_content)
    └─ progress_schedule_service.py
```

---

## Factory Pattern Architecture

### create_common_sub_services() Flow

```
EventsService.__init__()
    │
    ▼
create_common_sub_services(
    domain="events",
    backend=backend,
    graph_intel=graph_intel,
    event_bus=event_bus,
    insight_store=insight_store,
    activity_knowledge_intelligence=activity_knowledge_intelligence,
    skip={"core", "intelligence"},  # optional — applies only to core/search/rels/intel
)
    │
    ▼
ACTIVITY_DOMAIN_CONFIGS["events"]  ← Registry lookup
    │
    ├─ core_class: "EventsCoreService"
    ├─ search_class: "EventsSearchService"
    ├─ intelligence_class: "EventsIntelligenceService"
    ├─ event_handler_class: "EventEventHandlerService"
    ├─ learning_class: "EventsLearningService"
    └─ relationship_config: EVENTS_CONFIG
    │
    ▼
Dynamic imports + instantiation (skipping names in skip set)
    │
    ├─ core = None  (skipped)
    ├─ search = EventsSearchService(backend=backend, ...)
    ├─ intel = None  (skipped)
    ├─ rels = UnifiedRelationshipService(backend=backend, config=EVENTS_CONFIG)
    ├─ event_handler = EventEventHandlerService(...)  (always built)
    ├─ learning = EventsLearningService(...)           (always built when class configured)
    └─ knowledge_intelligence = <passed-in singleton>  (always set)
    │
    ▼
CommonSubServices[EventsIntelligenceService]
    ├─ core: None
    ├─ search: EventsSearchService
    ├─ relationships: UnifiedRelationshipService
    ├─ intelligence: None
    ├─ event_handler: EventEventHandlerService
    ├─ learning: EventsLearningService
    └─ knowledge_intelligence: ActivityKnowledgeIntelligenceService
```

**Benefits:**
- Eliminates ~80 lines of boilerplate per facade
- Centralized configuration via `ACTIVITY_DOMAIN_CONFIGS` registry
- Generic type parameter for intelligence service
- `skip` parameter covers the first 4 (core/search/relationships/intelligence); event_handler, learning,
  and knowledge_intelligence are always auto-wired for every domain

---

## Configuration Architecture

### DomainConfig Flow

```
TasksSearchService
    │
    ├─ Class-level attribute
    │   _config = create_activity_domain_config(
    │       dto_class=TaskDTO,
    │       model_class=Task,
    │       domain_name="tasks",
    │       date_field="due_date",
    │       completed_statuses=("completed",),
    │   )
    │
    ▼
DomainConfig dataclass
    │
    ├─ dto_class: TaskDTO
    ├─ model_class: Task
    ├─ search_fields: ("title", "description")   ← Default from factory
    ├─ search_order_by: "created_at"             ← Default from factory
    ├─ category_field: "category"                ← Default from factory
    ├─ user_ownership_relationship: "OWNS"       ← Default from Activity factory
    ├─ date_field: "due_date"                    ← Provided
    ├─ completed_statuses: ("completed",)        ← Provided
    └─ ... (14+ more fields)
    │
    ▼
BaseService._get_config_value("search_fields")
    └─ Returns: ("title", "description")
       Used by: SearchOperationsMixin.search()
```

**Key Insight:** `DomainConfig` is THE single source of truth — replaces scattered per-class attributes.

---

## Summary

### Key Architectural Patterns

1. **Mixin Composition** — 7 focused mixins provide 100+ methods to `BaseService`
2. **Facade Pattern** — 1 facade per domain delegates to 7–14 specialized sub-services
3. **Explicit Delegation** — Facade services have explicit `async def` delegation methods (not dynamic generation)
4. **Factory Pattern** — `create_common_sub_services()` creates the same 7 sub-services for every Activity Domain from the registry: core/search/relationships/intelligence (skippable via `skip={}`) + event_handler, learning, knowledge_intelligence (always auto-wired). The shared shape is the contract for interconnectivity — see `.claude/skills/activity-domains/SKILL.md` § "Harmony Without Over-Generalization".
5. **Configuration Pattern** — `DomainConfig` dataclass is single source of truth
6. **Event-Driven** — Domain events published for side effects (analytics, achievements, etc.)

### Service Layers

```
Layer 1: BaseService (6 mixins)             ← Foundation (100+ methods)
Layer 2: Sub-Services (5–11 per domain)     ← Implementation (specialized)
Layer 3: Facades (1 per domain)             ← Public API (explicit delegation)
Layer 4: Routes (HTTP → Facades)            ← Interface (HTTP boundaries)
```

### Design Principles

- **Single Responsibility** — Each mixin/sub-service has ONE focused responsibility
- **Composition over Inheritance** — Facades compose sub-services, don't inherit from them
- **Explicit over Magic** — Explicit delegation methods, no dynamic generation
- **Configuration over Code** — `DomainConfig` replaces scattered class attributes
- **Fail-Fast** — All dependencies REQUIRED at init (no graceful degradation)

---

## See Also

- [Sub-Service Catalog](/docs/reference/SUB_SERVICE_CATALOG.md) — Which service does what
- [Method Index](/docs/reference/BASESERVICE_METHOD_INDEX.md) — Complete method listing
- [Quick Start Guide](/docs/guides/BASESERVICE_QUICK_START.md) — New developer onboarding
- [Service Consolidation Patterns](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md)
- [Entity Type Architecture](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md)
- [BaseService Source](/core/services/base_service.py)
- [Example Facade Source](/core/services/tasks_service.py)

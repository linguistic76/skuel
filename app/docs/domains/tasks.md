---
title: Tasks Domain
created: 2025-12-04
updated: 2026-09-05
status: current
category: domains
tags:
- tasks
- activity-domain
- domain
related_skills:
- activity-domains
---

# Tasks Domain

**Type:** Activity Domain (1 of 6)
**UID Prefix:** `task:`
**Entity Label:** `Task`
**Config:** `TASKS_CONFIG` (from `core.models.relationship_registry`)

## Purpose

**Skill:** [@activity-domains](../../.claude/skills/activity-domains/SKILL.md)

Tasks represent work items with dependencies, deadlines, and knowledge requirements. They are the primary unit of execution in SKUEL.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/task/task.py` |
| DTO | `/core/models/task/task_dto.py` |
| Request Models | `/core/models/task/task_request.py` |
| Relationships | `/core/services/tasks/task_relationships.py` |
| Core Service | `/core/services/tasks/tasks_core_service.py` |
| Search Service | `/core/services/tasks/tasks_search_service.py` |
| Progress Service | `/core/services/tasks/tasks_progress_service.py` |
| Scheduling Service | `/core/services/tasks/tasks_scheduling_service.py` |
| Intelligence Service | `/core/services/tasks/tasks_intelligence_service.py` (4 mixins, incl. `_dual_track_mixin.py` for ADR-030 productivity) |
| Event Handler Service | `/core/services/tasks/task_event_handler_service.py` |
| Facade | `/core/services/tasks_service.py` |
| Config | `TASKS_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/task_events.py` |
| UI Routes | `/adapters/inbound/tasks_ui.py` |
| View Components | `/ui/activities/tasks_views.py` |

## Domain Enums

| Enum | Import | Values | YAML Field |
|------|--------|--------|------------|
| `Priority` | `core.models.enums` | LOW, MEDIUM, HIGH, CRITICAL | `priority` |
| `EntityStatus` | `core.models.enums` | DRAFT, SCHEDULED, ACTIVE, PAUSED, BLOCKED, COMPLETED, CANCELLED, POSTPONED, FAILED | `status` |
| `RecurrencePattern` | `core.models.enums` | DAILY, WEEKLY, MONTHLY, etc. (10 values) | `recurrence_pattern` |
| `EnergyLevel` | `core.models.enums` | LOW, MEDIUM, HIGH, VARIABLE | — (scheduling) |

**See:** [Enum Architecture](../architecture/ENUM_ARCHITECTURE.md)

## Facade Pattern (February 2026)

`TasksService` uses explicit `async def` delegation methods:

```python
class TasksService(BaseService[TasksOperations, Task]):
    core: TasksCoreService
    search: TasksSearchService
    progress: TasksProgressService
    scheduling: TasksSchedulingService
    relationships: UnifiedRelationshipService
    intelligence: TasksIntelligenceService  # incl. _DualTrackMixin — assess_productivity_dual_track (ADR-030)
    knowledge_intelligence: ActivityKnowledgeIntelligenceService  # shared singleton
    event_handler: TaskEventHandlerService
    ai: TasksAIService | None  # FULL tier only

    # Explicit delegation — MyPy-native, no mixin needed
    async def get_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_task(*args, **kwargs)

    async def analyze_task_learning_metrics(self, *args: Any, **kwargs: Any) -> Any:
        return await self.intelligence.analyze_task_learning_metrics(*args, **kwargs)
```

**Note (January 2026)**: TasksAnalyticsService removed. KU analytics methods are now direct in TasksService. **Note (March 2026)**: `TasksProductivityService` was shelved 2026-03-28; dual-track productivity assessment (`assess_productivity_dual_track`, ADR-030) lives in `tasks/_dual_track_mixin.py`, mixed into `TasksIntelligenceService` and wired to `GET /self-checkin` in #259. Domain-agnostic knowledge intelligence (suggestions, prerequisites, learning opportunities) extracted to `ActivityKnowledgeIntelligenceService` (`core/services/knowledge/`) — shared across all 6 activity domains. **Note (April 2026)**: `TasksLearningMetricsService` retired — its two methods (`analyze_task_learning_metrics`, `generate_task_knowledge_insights`) folded back into `TasksIntelligenceService` via `_productivity_mixin`, where they sit alongside sibling analytics. The name created false parity with peer domains' `*LearningService` (which handle learning-path integration); removing it restores a consistent sub-service taxonomy across all 6 Activity Domains.

## Event Handler — Insight Persistence (March 2026)

`TaskEventHandlerService` handles fire-and-forget reactive logic and persists structured insights to `InsightStore`:

| Handler | Trigger | InsightType | Impact |
|---------|---------|------------|--------|
| `handle_task_completed` | `event.was_overdue` | `COMPLETION_PATTERN` | MEDIUM |
| `handle_task_priority_changed` | `inflation_ratio > 0.6` | `IMBALANCE_DETECTED` | HIGH |
| `handle_task_completed` | Principle alignment found | `PRINCIPLE_ALIGNMENT` | LOW |

Also handles: duration calibration (EMA on User node), cascade impact analysis, batch pattern classification, and **automatic knowledge generation** (`_trigger_knowledge_generation` — step 4 of `handle_task_completed`, runs when `ku_generation_service` is wired in).

**Constructor note:** `TasksService` constructs `TaskEventHandlerService` manually (not via the `create_common_sub_services()` factory) to pass `ku_generation_service`. This is the same pattern used for `core` and `intelligence`.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier (indexed) |
| `user_uid` | `str` | Owner user (indexed) |
| `title` | `str` | Task title |
| `description` | `str?` | Optional description |
| `due_date` | `date?` | When task is due (indexed) |
| `scheduled_date` | `date?` | When task is scheduled (indexed) |
| `completion_date` | `date?` | When task was completed |
| `duration_minutes` | `int` | Estimated duration (default: 30) |
| `actual_minutes` | `int?` | Actual time spent |
| `status` | `EntityStatus` | Draft, Active, Completed, etc. (indexed) |
| `priority` | `Priority` | Low, Medium, High, Urgent (indexed) |
| `project` | `str?` | Project grouping |
| `tags` | `tuple[str, ...]` | Tags for categorization |
| `parent_uid` | `str?` | Parent task UID. NOT a node property — an *edge carrier*: `RELATIONSHIP_SKIP_FIELDS` drops it and `TasksCoreService.create` writes `(parent)-[:HAS_SUBTASK]->(task)` from it, for both create doors |
| `fulfills_goal_uid` | `str?` | Goal this task fulfills. DUAL-WRITTEN: a real node column AND the `(task)-[:FULFILLS_GOAL]->(goal)` edge — both create doors (`TasksCoreService._write_link_edges`), the update path (`TasksService._sync_relationship_edges`), and the vault door, which stamps the column from `connections.fulfills_goal` (`core/services/ingestion/preparer.py`). Invariant: property == edge target. The edge is admitted like every other link (goal must exist, be the caller's, be a Goal); a refused edge clears the column so the two halves never disagree |
| `recurrence_pattern` | `RecurrencePattern?` | Daily, Weekly, etc. |

## Relationships

### Outgoing (Task → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `APPLIES_KNOWLEDGE` | Ku | Knowledge applied in this task |
| `prerequisite_knowledge` | `REQUIRES_KNOWLEDGE` | Ku | Knowledge required before starting |
| `principles` | `ALIGNED_WITH_PRINCIPLE` | Principle | Guiding principles |
| `enables` | `ENABLES_TASK` | Task | Tasks this enables |
| `triggers` | `TRIGGERS_ON_COMPLETION` | Task | Tasks triggered when complete |
| `unlocks_knowledge` | `UNLOCKS_KNOWLEDGE` | Ku | Knowledge unlocked by completion |
| `contributes_to_goal` | `CONTRIBUTES_TO_GOAL` | Goal | Goals this contributes to |
| `fulfills_goal` | `FULFILLS_GOAL` | Goal | Goal this fulfills — dual-written with the `fulfills_goal_uid` column (see Fields) |

**`TRIGGERS_ON_COMPLETION` schedules, it never reopens.** The completion cascade
(`TasksProgressService._trigger_task`) moves a dependent to `scheduled` only when that
dependent is not already in a terminal state (`EntityStatus.is_terminal()`). Reopening a
completed dependent through this path would strip its status while leaving `completion_date`
set, breaking the invariant that the stamp is non-null exactly when the task is completed.
Since ADR-087 the check is a condition the *write* evaluates
(`StatusWriteGuard(refuse_if_prior_in=TERMINAL)`), not a status read beforehand — a
dependent being completed concurrently is exactly what a read-then-write gate misses.

### Incoming (Other → Task)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `subtasks` | `HAS_CHILD` | Task | Child tasks |
| `prerequisite_tasks` | `DEPENDS_ON` | Task | Tasks that must complete first |
| `inferred_knowledge` | `INFERRED_KNOWLEDGE` | Ku | Inferred knowledge links |

### Bidirectional

- `DEPENDS_ON` - Task dependencies (both directions)

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `prerequisites` | Task | `DEPENDS_ON` |
| `dependents` | Task | `DEPENDS_ON` |
| `required_knowledge` | Ku | `REQUIRES_KNOWLEDGE` |
| `applied_knowledge` | Ku | `APPLIES_KNOWLEDGE` |
| `contributing_goals` | Goal | `CONTRIBUTES_TO_GOAL`, `FULFILLS_GOAL` |

## Query Intent

**Default:** `QueryIntent.PREREQUISITE`

| Context | Intent |
|---------|--------|
| `context` | `PREREQUISITE` |
| `dependencies` | `PREREQUISITE` |
| `impact` | `HIERARCHICAL` |
| `practice` | `PRACTICE` |

## MEGA-QUERY Sections

The MEGA-QUERY in `/core/services/user/user_context_queries.py` fetches:

- `active_task_uids` - Active task UIDs
- `completed_task_uids` - Completed task UIDs
- `overdue_task_uids` - Overdue task UIDs
- `today_task_uids` - Tasks due today
- `entities_rich["tasks"]` - Full task data with graph context

## Usage Examples

```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

# Create relationship service
tasks_rel = UnifiedRelationshipService(backend, graph_intel, TASKS_CONFIG)

# Get related knowledge
knowledge_uids = await tasks_rel.get_related_uids("knowledge", "task.123")

# Get task with full context
task, context = await tasks_rel.get_entity_with_context("task.123", depth=2)
```

## Search Methods

**Service:** `TasksSearchService` (`/core/services/tasks/tasks_search_service.py`)

### Inherited from BaseService

| Method | Description |
|--------|-------------|
| `search(query, user_uid)` | Text search across title, description |
| `get_by_status(status, user_uid)` | Filter by EntityStatus |
| `get_by_category(category, user_uid)` | Filter by category field |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_blocking_tasks(uid, user_uid)` | Tasks blocking this task |
| `get_blocked_tasks(uid, user_uid)` | Tasks blocked by this task |
| `get_by_priority(priority, user_uid)` | Filter by priority level |
| `get_upcoming(days_ahead=7, user_uid, limit=100)` | Tasks due within N days (inherited from `TimeQueryMixin`) |
| `get_overdue(user_uid, limit=100)` | Tasks past due date (inherited) |
| `get_active(user_uid, limit=100)` | Non-terminal tasks for a user (inherited) |
| `get_pending(user_uid)` | Tasks with pending status |
| `search_by_parent_goal(goal_uid, user_uid)` | Tasks fulfilling a goal |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](../reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`TasksIntelligenceService` provides task-specific behavioral and performance intelligence:

| Method | Description |
|--------|-------------|
| `get_with_context(uid)` | Task with full graph neighborhood |
| `get_behavioral_insights(user_uid)` | Task completion patterns analysis |
| `get_performance_analytics(user_uid)` | Completion rates, trends, duration calibration |
| `get_domain_insights(uid)` | Readiness (knowledge prerequisites) + path-aware cross-domain block |

**Shared knowledge intelligence** (suggestions, prerequisites, learning opportunities) provided by `ActivityKnowledgeIntelligenceService` (`core/services/knowledge/`) — serves all 6 activity domains.

**See:** [Intelligence Services Index](../intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## Events/Publishing

The Tasks domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `TaskCreated` | Task created | `task_uid`, `user_uid`, `title`, `priority`, `domain` |
| `TaskCompleted` | Task marked complete | `task_uid`, `user_uid`, `completion_time_seconds`, `was_overdue`, `is_repeat` |
| `TaskReopened` | Task moved back OUT of completed | `task_uid`, `user_uid` |
| `TaskUpdated` | Task modified | `task_uid`, `user_uid`, `updated_fields` |
| `TaskDeleted` | Task removed | `task_uid`, `user_uid`, `reason` |
| `TaskPriorityChanged` | Priority changed | `task_uid`, `user_uid`, `old_priority`, `new_priority` |
| `TasksBulkCompleted` | Batch completion | `task_uids` (rows actually written), `user_uid`, `count` |

**Event handling:** Other services subscribe to these events (e.g., UserContext invalidation, goal progress updates).

**Every door to COMPLETED publishes `TaskCompleted`.** Three publishers, one contract:
`complete_task_with_cascade` (the explicit-complete doors), the status chokepoint
`update_task` (`POST /api/tasks/{uid}/status`), and a per-row fan-out from
`complete_tasks_bulk`. The last two are transition-gated, so they publish exactly when the
write moved the task INTO completed and stay silent otherwise.

**`TasksBulkCompleted` is published alongside the per-row events, not instead of them** — it
carries the shape of the *batch* (size, time of day) for pattern classification. A consumer
that merely counts completions must read the per-row `TaskCompleted`, or it double-counts a
bulk call.

**`TaskCompleted.is_repeat`:** completing an already-completed task is legal and the cascade
deliberately re-runs on it (the repair path). The flag gates the part of a handler that
**accumulates** (an append, a stamp), never the part that **derives**. So a subscriber may read
it for one half of its work and ignore it for the other — principle alignment recomputes on
every complete but appends its insight only on a first, and `ProductivityAnalytics` — whose
handler now only records the completion *moment* — skips a repeat entirely. Only the
explicit-complete cascade ever sets it — the transition-gated publishers cannot be reached by a
repeat. See the `TaskCompleted` docstring in `core/events/task_events.py` for the full contract.

**`tasks_completed` is derived at read, not stored.** `GET /api/analytics/productivity` counts
the user's tasks currently in `completed` on the same traversal that counts the velocity window,
so the window is a subset of the total by construction and a completion arriving through a door
that publishes no task event (the vault `- [x]` upsert) is counted the moment it exists. The
`ProductivityAnalytics` node holds only `first_completion_at` / `last_completion_at`.

**`TaskReopened` is the mirror**, published from `update_task` alone on a transition OUT of
completed (Today's Undo posts the prior status through that chokepoint). It has no subscriber:
it existed so a stored count could fall, and a derived count falls on its own. It stays published
as the chokepoint's statement of the transition — one ADR-087 now detects exactly, from the status
the write itself returned rather than from a lock-free read beforehand.

✅ **RESOLVED 2026-08-24.** Reopening in SKUEL now un-checks the Obsidian line and strips the
`✅ date` — checkbox authority runs both directions outbound (ADR-070 Resolved Design Question 2,
amended). ⚠ The trigger is **not** this event: it is the outbound sync pass's STATE predicate
("not completed AND the line is still marked done"), because a reopen is only knowable after the
guarded write returns the prior, so it is a one-shot fact with no retry. The event is kept
published and deliberately **unsubscribed** — do not delete it in a bloat sweep, and do not give
it a subscriber. Case file (resolved): `docs/roadmap/done/reopen-vault-surface.md` § "`TaskReopened` Has
Zero Subscribers, and a Reopen Has No Vault Surface".

**Neither a reopen nor a repeat complete is a completion moment.** Both leave
`first_completion_at` / `last_completion_at` untouched: those stamps record when the user first
completed something and when they most recently did, and neither a reopen nor a re-post of
`completed` on an already-completed task is either.

**`completion_velocity` is a rate over a fixed trailing window** — tasks whose
`completion_date` falls inside the last `CompletionVelocityWindow.DAYS` calendar days, divided
by that window in weeks. It does not read the two stamps at all. It formerly divided the
lifetime count by the first→last span, a denominator that could only grow (so the metric could
only decay) and that collapsed to zero for a user with a single completion. A user with no
completions in the window reports `0.0`; the cumulative figures beside it are unaffected.

## Update Validation

Tasks carries **one** update business rule: the priority of an **overdue** task cannot be
lowered (`TasksCoreService._validate_update`). Raising it, or lowering it on a task that is
not overdue, is ordinary re-planning. "Overdue" is `Task.is_overdue()` — past `due_date` and
not completed.

`update_task` invokes the hook **explicitly**, the way `HabitsCoreService.update_habit` does.
The facade overrides `update` / `update_for_user` and routes both to `update_task`, so the
inherited CRUD hook never fires for Tasks — which is why this rule was dead code until
2026-08-23 (cascade-idempotency arc, correction #14).

**Terminal ≠ frozen.** A second rule refusing *every* change to a
completed/cancelled/archived task was declared here and never had a caller; it was deleted
rather than wired. Wiring it would have refused the repeat completion the cascade treats as a
repair path, refused the status re-post that reopens a task, and resurrected for Tasks the
achievement immutability deliberately removed for Goals (#1124). The one terminal-state gate
Tasks has is the completion cascade's own guard in `TasksProgressService._trigger_task`, which
declines to *reopen* a finished dependent — evaluated inside the write (ADR-087).

## UI Routes

Tasks has an active read-focused UI at `/tasks` with HTMX status toggle, priority/status filtering, and knowledge connections.

| Route | Method | Description |
|-------|--------|-------------|
| `/tasks` | GET | Read-focused task list with filtering |
| `/tasks/list-fragment` | GET | HTMX filtered list fragment |
| `/tasks/detail` | GET | Task detail page |
| `/tasks/create` | GET/POST | Create task form |
| `/tasks/edit` | GET/POST | Edit task form |
| `/tasks/subtasks` | GET | HTMX fragment: sub-task list for a parent task |
| `/tasks/subtasks/add` | POST | Create a sub-task inline; returns refreshed fragment |
| `/api/tasks/{uid}/status` | POST | HTMX status toggle (returns `TaskCard`) |
| `/api/tasks/children` | GET | JSON: direct sub-tasks of a parent |
| `/api/tasks/hierarchy` | GET | JSON: full hierarchy context (ancestors, siblings, children) |
| `/api/tasks/add-child` | POST | Add a sub-task relationship between two tasks |
| `/api/tasks/remove-child` | POST | Remove a sub-task relationship |

## Code Examples

### Create a Task

```python
from core.models.task.task_request import TaskCreateRequest
from core.models.enums import Priority

result = await tasks_service.create_task(
    TaskCreateRequest(
        title="Review PR #123",
        description="Review and approve the authentication PR",
        priority=Priority.HIGH,
        due_date=date.today() + timedelta(days=1),
        project="skuel-auth",
    ),
    user_uid=user_uid,
)
task = result.value
```

### Link Task to Goal

```python
result = await tasks_service.link_task_to_goal(
    task_uid=task.uid,
    goal_uid="goal.launch-auth-system",
    contribution_score=0.8,
)
```

### Get Tasks with Dependencies

```python
# Get tasks blocking this task
blocking = await tasks_service.search.get_blocking_tasks(task.uid, user_uid)

# Get tasks blocked by this task
blocked = await tasks_service.search.get_blocked_tasks(task.uid, user_uid)
```

## See Also

- [Goals Domain](goals.md) - Tasks fulfill goals
- [Knowledge (KU) Domain](ku.md) - Tasks apply/require knowledge
- [Principles Domain](principles.md) - Tasks align with principles

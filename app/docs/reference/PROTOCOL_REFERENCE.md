---
title: Protocol Reference Guide
updated: 2026-03-05
status: current
category: reference
tags: [protocol, reference]
related: [ADR-025, ADR-027]
---

# Protocol Reference Guide

**Last Updated:** February 8, 2026
**Purpose:** Complete reference for all Protocol interfaces in SKUEL codebase
**Location:** `/core/ports/` (service protocols) and `/core/models/protocols/` (domain model protocols)

---

## Table of Contents

1. [Core Data Protocols](#core-data-protocols)
2. [Pydantic Integration Protocols](#pydantic-integration-protocols)
3. [Backend Capability Protocols](#backend-capability-protocols)
4. [Facade Services — Explicit Delegation (February 2026)](#facade-services--explicit-delegation-february-2026)
5. [Route-Facing Service Protocols (February 2026)](#route-facing-service-protocols-february-2026)
6. [Knowledge Carrier Protocols (ADR-027)](#knowledge-carrier-protocols-adr-027)
7. [Usage Examples](#usage-examples)

---

## Protocol File Locations

| Category | Location | Purpose |
|----------|----------|---------|
| **Base Protocols** | `/core/ports/base_protocols.py` | Core types, backend operations |
| **Domain Protocols** | `/core/ports/domain_protocols.py` | Domain service operations |
| **Curriculum Protocols** | `/core/ports/curriculum_protocols.py` | KU, PS, LP, MOC operations |
| **Askesis Protocols** | `/core/ports/askesis_protocols.py` | Cross-cutting intelligence + CRUD |
| **Submission Protocols** | `/core/ports/submission_protocols.py` | Submission CRUD, processing, sharing, search |
| **Report Protocols** | `/core/ports/report_protocols.py` | Human + AI reports, progress reports, scheduling, teacher review |
| **Form Protocols** | `/core/ports/form_protocols.py` | Form backend ops (2) + route-level ISP (2) |
| **Group Protocols** | `/core/ports/group_protocols.py` | Group CRUD only |
| **Service Protocols** | `/core/ports/service_protocols.py` | Calendar, Viz, System, LifePath, Auth, Orchestration |
| **Search Protocols** | `/core/ports/search_protocols.py` | Search operations |
| **Infrastructure Protocols** | `/core/ports/infrastructure_protocols.py` | EventBus, Schema, User (3 ISP sub-protocols + 1 composed), Ingestion, Closeable |
| **Intelligence Protocols** | `/core/ports/intelligence_protocols.py` | Knowledge (shared) + Domain (per-service) + Composed |
| **Facade Services** | `/core/services/{domain}_service.py` | Concrete classes with explicit delegation methods |
| **Knowledge Carrier** | `/core/models/protocols/knowledge_carrier_protocol.py` | Knowledge integration |

---

## Core Data Protocols

### EnumLike
**Purpose:** Objects with a `.value` attribute (Enum members)

```python
from core.ports import EnumLike

@runtime_checkable
class EnumLike[V = str | int | float](Protocol):
    @property
    def value(self) -> V: ...
```

`value` is a **read-only property**, not a mutable attribute: `Enum.value` is a
descriptor, so a settable-attribute protocol never matched an enum statically.
The type parameter is what lets `get_enum_value` return the member's value type
rather than `Any`; bare `EnumLike` still narrows to `str | int | float`.

**Usage:**
```python
from core.models.enums import Priority

if isinstance(priority, EnumLike):
    db_value = priority.value  # "high", "medium", "low"
```

**Helper Function:**
```python
from core.ports import get_enum_value

# Handles both enums and plain values
value = get_enum_value(priority)  # Works for Priority.HIGH or "high"
```

---

### HasUID
**Purpose:** Objects with a unique identifier

```python
@runtime_checkable
class HasUID(Protocol):
    uid: str
```

**Usage:**
```python
if isinstance(obj, HasUID):
    print(f"Entity: {obj.uid}")
```

---

### HasToDict
**Purpose:** Objects that can convert to dictionary

```python
@runtime_checkable
class HasToDict(Protocol):
    def to_dict(self) -> dict[str, Any]: ...
```

**Helper Function:**
```python
from core.ports import to_dict

# Universal conversion - tries model_dump(), dict(), to_dict(), serialize()
data = to_dict(any_object)
```

---

## Pydantic Integration Protocols

### PydanticModel
**Purpose:** Pydantic v2 models with model_dump method

```python
@runtime_checkable
class PydanticModel(Protocol):
    def model_dump(self, **kwargs) -> dict[str, Any]: ...
```

---

### PydanticFieldInfo
**Purpose:** Pydantic v2 FieldInfo with metadata list

```python
@runtime_checkable
class PydanticFieldInfo(Protocol):
    description: str | None
    metadata: list[Any]  # List of constraint objects (annotated_types)
```

**Usage:**
```python
from pydantic import BaseModel

class MyModel(BaseModel):
    name: str = Field(description="User name")

field_info = MyModel.model_fields['name']
if isinstance(field_info, PydanticFieldInfo):
    print(field_info.description)  # "User name"
```

---

### Constraint Protocols (Pydantic v2 / annotated_types)

These protocols represent individual constraint objects from Pydantic's `metadata` list:

#### MinLenConstraint
```python
@runtime_checkable
class MinLenConstraint(Protocol):
    min_length: int
```

#### MaxLenConstraint
```python
@runtime_checkable
class MaxLenConstraint(Protocol):
    max_length: int
```

#### GeConstraint (Greater Than or Equal)
```python
@runtime_checkable
class GeConstraint(Protocol):
    ge: float
```

#### LeConstraint (Less Than or Equal)
```python
@runtime_checkable
class LeConstraint(Protocol):
    le: float
```

#### GtConstraint (Greater Than)
```python
@runtime_checkable
class GtConstraint(Protocol):
    gt: float
```

#### LtConstraint (Less Than)
```python
@runtime_checkable
class LtConstraint(Protocol):
    lt: float
```

**Usage Example:**
```python
from pydantic import BaseModel, Field
from core.ports import PydanticFieldInfo, MinLenConstraint, MaxLenConstraint

class User(BaseModel):
    username: str = Field(min_length=3, max_length=20)

field_info = User.model_fields['username']
if isinstance(field_info, PydanticFieldInfo):
    for constraint in field_info.metadata:
        if isinstance(constraint, MinLenConstraint):
            print(f"Minimum length: {constraint.min_length}")
        if isinstance(constraint, MaxLenConstraint):
            print(f"Maximum length: {constraint.max_length}")
```

---

## Backend Capability Protocols

These protocols define what operations a backend supports. Use `isinstance()` checks instead of `hasattr()`.

### UserContextOperations
**Purpose:** User context cache management for breaking circular dependencies
**Added:** October 14, 2025

```python
class UserContextOperations(Protocol):
    """User context operations for cache invalidation."""
    async def invalidate_context(self, user_uid: UserUID) -> None: ...
```

**Usage:**
```python
from core.ports import UserContextOperations

class TasksService:
    def __init__(
        self,
        backend: TasksOperations,
        context_service: Optional[UserContextOperations] = None
    ):
        self.context_service = context_service

    async def complete_task(self, task_uid: str, user_uid: UserUID):
        # ... task completion logic ...

        # Invalidate cache after state changes
        if self.context_service:
            await self.context_service.invalidate_context(user_uid)
```

**Why This Protocol Exists:**
This protocol breaks circular dependencies between services and UserContextService. Services depend on the protocol interface, not the concrete implementation, eliminating import cycles.

---

## Domain Operations Protocols

**Location:** `/core/ports/domain_protocols.py`
**Purpose:** Backend/persistence-layer interfaces for all entity types
**Core Principle:** "Results internally, exceptions at boundaries"

All domain operation protocols use `Result[T]` return types and define **persistence-layer operations only** — CRUD, graph queries, and relationship management. Service-level methods (state transitions, event publishing, orchestration) exist on facade services as explicit delegation methods but are **not** part of the backend protocol contract.

### Domain Backend Protocols

| Protocol | Domain | Category |
|----------|--------|----------|
| `TasksOperations` | Tasks | Activity |
| `GoalsOperations` | Goals | Activity |
| `HabitsOperations` | Habits | Activity |
| `EventsOperations` | Events | Activity |
| `ChoicesOperations` | Choices | Activity |
| `PrinciplesOperations` | Principles | Activity |
| `FinanceOperations` | Finance | Finance |
| `KuOperations` | Knowledge Units | Curriculum |
| `PsOperations` | Path Steps | Curriculum |
| `LpOperations` | Learning Paths | Curriculum |

**What domain protocols contain:**
- Persistence CRUD: `create_*`, `get_*_by_uid`, `update_*`, `delete_*` (via `BackendOperations[T]` base)
- Domain-specific queries: `get_user_tasks()`, `find_by_status()`, `list_by_user()`
- Graph relationship operations: `link_*_to_*()`, `create_user_*_relationship()`

**What domain protocols do NOT contain** (lives on facade services instead):
- State transitions: `complete_task()`, `complete_goal()`, `record_completion()`
- Orchestration methods: `get_decision_patterns()`, `calculate_principle_integrity()`
- Cross-domain context: `get_*_cross_domain_context()` (not on backend)

### Typed Backend Subclasses (February 2026)

For methods that don't match `UniversalNeo4jBackend.__getattr__` bridge patterns, typed subclasses provide explicit implementations:

```python
# adapters/persistence/neo4j/backends/activity_backends.py
class HabitsBackend(UniversalNeo4jBackend["Habit"]):
    """Adds get_habit, list_by_user, get_user_habits, archive_habit, link_habit_to_*"""

class GoalsBackend(UniversalNeo4jBackend["Goal"]):
    """Adds get_goal, get_user_goals, link_goal_to_*"""
```

Both are drop-in replacements — same constructor signature as `UniversalNeo4jBackend[T]`.

### Result[T] Return Pattern

```python
# Example: TasksOperations protocol (persistence ops only)
class TasksOperations(Protocol):
    async def get_task_by_uid(self, uid: str) -> Result[Task]:
        """Get task by UID - returns Result[Task], not Task directly."""
        ...

    async def create_task(self, task_data: dict | Task) -> Result[Task]:
        """Create task - returns Result[Task]."""
        ...

    async def update_task(self, uid: str, updates: dict) -> Result[Task]:
        """Update task - returns Result[Task]."""
        ...

    async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
        """Get all tasks for a user - domain-specific query."""
        ...
```

**Usage:**
```python
from core.ports import TasksOperations

async def process_task(service: TasksOperations, task_uid: str):
    result = await service.get_task_by_uid(task_uid)

    if result.is_error:
        # Handle error (NotFound, Database, etc.)
        return result.error

    task = result.value
    # Process task...
    return task
```

**See:** `/docs/patterns/ERROR_HANDLING.md` for complete Result[T] pattern documentation.
**See:** `/docs/patterns/protocol_architecture.md` for February 2026 protocol cleanup details.

---

## Facade Services — Explicit Delegation (February 2026)

**Status:** `facade_protocols.py` and `FacadeDelegationMixin` are **deleted**. Facade services now use explicit `async def` delegation methods.

### What Changed

Previously, `FacadeDelegationMixin` generated delegation methods dynamically from a `_delegations` dict. `facade_protocols.py` existed solely to make those dynamic methods visible to MyPy — a three-way sync burden (service class, `_delegations` dict, protocol class).

**Current approach:** All 9 facade services have explicit `async def` methods. MyPy sees them natively.

### Usage Pattern

Route files import the concrete service class directly:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.tasks_service import TasksService

async def analyze_tasks(tasks_service: "TasksService") -> dict:
    # MyPy sees all explicit methods on TasksService
    milestones = await tasks_service.get_task(uid)
    return {"task": milestones}
```

### Affected Services (9 Total)

| Service | Module |
|---------|--------|
| `TasksService` | `core.services.tasks_service` |
| `GoalsService` | `core.services.goals_service` |
| `HabitsService` | `core.services.habits_service` |
| `EventsService` | `core.services.events_service` |
| `ChoicesService` | `core.services.choices_service` |
| `PrinciplesService` | `core.services.principles_service` |
| `KuService` | `core.services.ku_service` |
| `LpService` | `core.services.lp_service` |
| `PsService` | `core.services.ps_service` |

**Note:** MOC uses `KuService` (MOC is KU-based).

---

## Route-Facing Service Protocols (February 2026)

**Purpose:** ISP-compliant protocols for services passed from the `Services` dataclass to route files
**Core Principle:** Each protocol captures ONLY the methods actually called from routes — not the full service API

These protocols replace `Any` types on the `Services` dataclass fields, giving route files type-safe contracts without coupling to concrete implementations.

### Four Protocol Files

| File | Protocols | Route Consumers |
|------|-----------|-----------------|
| `submission_protocols.py` | 3 protocols | `submissions_api.py`, `progress_report_api.py` |
| `sharing_protocols.py` | 1 protocol | `submissions_sharing_api.py` |
| `report_protocols.py` | 7 protocols | `exercises_api.py`, `progress_report_api.py`, `teaching_api.py` |
| `form_protocols.py` | 4 protocols | `form_templates_api.py`, `form_submissions_api.py` |
| `group_protocols.py` | 1 protocol | `groups_api.py` |
| `service_protocols.py` | 11 protocols | `orchestration_routes.py`, `calendar_api.py`, `visualization_api.py`, `system_api.py`, `lifepath_api.py`, `auth_ui.py`, `admin_api.py`, `lateral_routes.py` |

Plus `AskesisCoreOperations` added to existing `askesis_protocols.py`.

### Submission Protocols (3) — `submission_protocols.py`

Map to the **UserEntry** (submission) stage of the 4-phase educational loop (`Exercise → UserEntry → EntryReport → RevisedExercise`).

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `SubmissionOperations` | `submissions`, `submissions_core` | list_submissions, get_file_content, get_processed_file_content, update_processed_content, categorize, tags, bulk ops | `submissions_api.py` |
| `SubmissionProcessingOperations` | `submissions_processor` | 2 (process_submission, reprocess_submission) | `submissions_api.py` |
| `SubmissionSearchOperations` | `submissions_search` | 4 (search_submissions, get_report_statistics, get_recent_submissions, get_submissions_with_feedback_status) | consumed by `SubmissionsOrchestrator` — no direct route callers |

### Sharing Protocol (1) — `sharing_protocols.py`

Entity-agnostic sharing. `UnifiedSharingService` implements this protocol and works across all EntityTypes.

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `SharingOperations` | `sharing` | share, unshare, get_shared_with, get_shared_with_me, set_visibility, check_access, verify_shareable, share_with_group, unshare_from_group, get_groups_shared_with, get_shared_with_me_via_groups (11 methods) | `submissions_sharing_api.py` |

### Report Protocols (8) — `report_protocols.py`

Map to the **Report** stage of the educational loop. `processor_type` discriminates source: `HUMAN` (teacher/admin), `LLM` (AI via Exercise or on-demand), `AUTOMATIC` (scheduled).

ENTRY_REPORT entities are produced two ways, behind **separate route-facing protocols** (split 2026-05-30, PR #128): AI reports + typed reads via `EntryReportOperations` (`EntryReportService`); teacher-authored HUMAN feedback via `TeacherReviewOperations` (`TeacherReviewService.submit_report`, submission-anchored). `AssessmentOperations` (`AssessmentService`) is the paired *read* of a student's received assessments (not a producer). `EntryReportService` additionally uses the **backend-level** `EntryReportBackendOperations` to type its `self.backend`. Typed reads return `list[EntryReport]` end-to-end (no TypedDict projection); persisted nodes carry `:Entity:EntryReport` dual labels.

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `EntryReportOperations` (service) | `entry_report` | generate_report(`UserEntry`, `Exercise`) → `EntryReport` `LLM`, list_for_submission → `list[EntryReport]` (both HUMAN + LLM, discriminated by `processor_type`) | `exercises_api.py`, `teaching_api.py`, `teaching_ui.py`, `user_entry_ui.py` |
| `AssessmentOperations` (service) | `user_entry_assessment` | get_assessments_for_student → `list[EntryReport]` (reads student `OWNS` — the visibility anchor, C1 feedback-loop UX arc). Teacher-authored HUMAN feedback is *written* by `TeacherReviewOperations` (submission-anchored); this is its paired read | `entry_reports_ui.py` via `UserEntryOrchestrator` |
| `EntryReportBackendOperations` (backend) | `EntryReportService.backend` (typed `self.backend`) | list_for_submission, get_reports_for_student_exercise, get_reports_by_teacher (all → `list[EntryReport]` via `from_neo4j_node`), get_linked_ku_and_student (mastery-loop scalar projection) | — (backend-only) |
| `ProgressReportOperations` | `progress_report_generator` | 1 (generate → `ACTIVITY_REPORT` entity, `LLM` or `AUTOMATIC`) | `progress_report_api.py` |
| `ProgressScheduleOperations` | `progress_schedule` | 4 (create_schedule, get_user_schedule, update_schedule, deactivate_schedule) | `progress_report_api.py` |
| `ActivityReportOperations` | `activity_report` | 6 (create_snapshot, submit_report → `ACTIVITY_REPORT` `HUMAN`, get_history, annotate → `AnnotationResult`, get_annotation → `AnnotationState`, get_privacy_summary → `PrivacySummary`) | `progress_report_api.py` |
| `ReviewQueueOperations` | `review_queue` | 2 (request_review → `ReviewRequestResult`, get_pending_reviews → `list[PendingReviewItem]`) | `progress_report_api.py` |
| `ReportRelationshipOperations` | `report_relationships` | 5 (get_pending_submissions, get_unsubmitted_exercises, get_report_summary → `ReportSummary`, get_learning_loop_chain → `LearningLoopChain`, get_submission_chain → `SubmissionChain`) | context intelligence |
| `TeacherReviewOperations` | `teacher_review` | 13 (review queue → `list[ReviewQueueItem]`, submission detail → `SubmissionDetailResult`, feedback history, submit/request/approve, exercises, students, dashboard → `TeacherDashboardStats`, classes → `list[GroupMemberProgress]`) | `teaching_api.py` |

**Why HUMAN and AI reports are SEPARATE protocols (PR #128):**
`EntryReportService.generate_report()` creates AI (`processor_type=LLM`) `ENTRY_REPORT` entities; teacher-authored HUMAN reports are created by `TeacherReviewService.submit_report()` — both linked to the submission via `REPORT_FOR`, but **no single class implements both**. The AI + read methods used to share one `EntryReportOperations` protocol with the teacher-assessment methods, which was an impl-lie: `compose.py` injected `EntryReportService` (which lacks the assessment methods) where the bundled protocol was expected, masking a reachable `AttributeError` in `ProfileOrchestrator`. Splitting into `EntryReportOperations` (AI + reads) and `AssessmentOperations` (a student's received-assessment read) makes each protocol match its single implementing service — the conformance is now checked by mypy `arg-type` at the wiring root. `generate_report` accepts typed params: `entry: UserEntry`, `exercise: Exercise` (not `Any`); `list_for_submission` remains the unified typed read for both sources.

**Note on `AssignmentOperations`:** `AssignmentOperations` remains in `curriculum_protocols.py` — Assignments are curriculum entities (Exercise scope=assigned), not reports.

### Form Protocols (4) — `form_protocols.py`

Two-tier protocols for the general-purpose form system.

**Backend-level** (typed `self.backend` in services, extend `BackendOperations[T]`; import directly from `core.ports.form_protocols`, not re-exported from `core.ports`):

| Protocol | Consumer | Methods |
|----------|----------|---------|
| `FormTemplateBackendOperations` | `FormTemplateService.__init__` | BackendOperations[FormTemplate] + `link_to_path_step`, `unlink_from_path_step`, `get_forms_for_path_step` |
| `FormSubmissionBackendOperations` | `FormSubmissionService.__init__` | BackendOperations[FormSubmission] + `create_with_relationships`, `list_by_user`, `get_submissions_for_template` |

**Route-level** (typed service in routes):

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `FormTemplateOperations` | `form_template_service` | 7 (create, get, list, update, delete, link/unlink path_step) | `form_templates_api.py` |
| `FormSubmissionOperations` | `form_submission_service` | 5 (submit, get, list_mine, delete, share) | `form_submissions_api.py` |

### Group Protocol (1) — `group_protocols.py`

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `GroupOperations` | `group_service` | 9 (create, get, list_teacher, list_user, update, delete, add/remove member, get_members) | `groups_api.py` |

**Note:** `TeacherReviewOperations` lives in `report_protocols.py` (Phase 4 Report infrastructure), not `group_protocols.py`.

### Cross-Cutting Service Protocols (9)

| Protocol | Services Field | Methods | Route Consumer |
|----------|---------------|---------|----------------|
| `CalendarServiceOperations` | `calendar` | 4 async (get_calendar_view, get_item, reschedule_item, record_habit_occurrence) | `calendar_api.py`, `calendar_ui.py` |
| `VisualizationOperations` | `visualization` | 6 async (4 Chart.js + 2 Gantt) | `visualization_api.py` |
| `SystemServiceOperations` | `system_service` | 11 (5 async health + 6 sync management) | `system_api.py` |
| `CrossDomainAnalyticsOperations` | `cross_domain_analytics` | 6 async (learning_velocity, spending_patterns, mood, productivity, habit_consistency, get_combined_dashboard) | `analytics_api.py` |
| `LifePathOperations` | `lifepath` | 3 async + `.alignment` sub-service | `lifepath_api.py` |
| `GraphAuthOperations` | `graph_auth` | 7 async (sign_up, sign_in, sign_out, reset_password_email, reset_password_with_token, admin_reset_token, validate_session_uid) | `auth_ui.py`, `admin_api.py` |
| `GoalTaskGeneratorOperations` | `goal_task_generator` | 3 (generate_tasks_for_goal, generate_tasks_for_all_goals, generate_next_critical_tasks) | `orchestration_routes.py` |
| `HabitEventSchedulerOperations` | `habit_event_scheduler` | 1 (schedule_events_for_habit) | `orchestration_routes.py` |
| `AskesisCoreOperations` | `askesis_core` | 5 (get_or_create, create, get, update, record_conversation) | `askesis_api.py` |

### Nested Protocol Pattern: LifePathOperations

LifePathService exposes a `.alignment` sub-service. The protocol models this with a nested protocol:

```python
@runtime_checkable
class LifePathAlignmentOperations(Protocol):
    async def calculate_alignment(self, context: UserContext) -> Result[LifePathAlignmentResult]: ...

@runtime_checkable
class LifePathOperations(Protocol):
    alignment: LifePathAlignmentOperations  # Sub-service access

    async def get_full_status(self, user_uid: UserUID) -> Result[dict[str, Any]]: ...
    async def capture_and_recommend(self, user_uid: UserUID, vision_statement: str) -> Result[dict[str, Any]]: ...
    async def designate_and_calculate(self, user_uid: UserUID, life_path_uid: str) -> Result[dict[str, Any]]: ...
    async def get_alignment(self, user_uid: UserUID) -> Result[dict[str, Any]]: ...
```

Routes access it as `lifepath_service.get_alignment(user_uid)`. The facade builds UserContext internally and delegates to `alignment.calculate_alignment(context)`.

### Vendor-Payload Pattern: VisualizationOperations

The protocol is **async-only, 8 methods**. The sync `format_*` formatters live on
`VisualizationService` and are deliberately *not* protocol members — the protocol's own
docstring says so ("Pure formatting lives in VisualizationService and is not part of this
protocol"), and calling one through the protocol is a MyPy `attr-defined` error.

Each method returns a **vendor wire type** from `core/ports/query_types.py`, not a bare
`dict`. `skuel.js`'s `chartVis` hands the deserialized payload straight to
`new Chart(ctx, config)`, so the TypedDict is the only thing checking the key names —
build these literals, never `cast()` a dict into them (SoC arc #11).

```python
@runtime_checkable
class VisualizationOperations(Protocol):
    async def get_completion_chart_data(self, user_uid: UserUID, period: str) -> Result[ChartJsConfig]: ...
    async def get_streak_chart_data(self, user_uid: UserUID) -> Result[ChartJsConfig]: ...
    async def get_tasks_gantt_data(self, user_uid: UserUID, project: str | None = None) -> Result[GanttConfig]: ...
```

### Usage in Route Files

```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.sharing_protocols import SharingOperations
    from core.ports.submission_protocols import SubmissionOperations

def create_submissions_sharing_api_routes(
    _app: Any,
    rt: Any,
    sharing_service: "SharingOperations",
    core_service: "SubmissionOperations | None" = None,
) -> list[Any]:
    # MyPy verifies .share(), .check_access() etc. exist
    ...
```

### Services Dataclass Wiring

Every field on the `Services` dataclass is typed — zero `Any` fields remain. Two strategies:

```python
# services_bootstrap.py
@dataclass
class Services:
    # Route-facing: ISP protocols (19 fields)
    reports: SubmissionOperations | None = None          # was ReportsSubmissionOperations
    report_feedback: EntryReportOperations | None = None    # was ReportsFeedbackOperations
    calendar: CalendarServiceOperations | None = None
    graph_auth: GraphAuthOperations | None = None

    # Internal: concrete classes via TYPE_CHECKING (~53 fields)
    tasks_intelligence: "TasksIntelligenceService | None" = None
    lateral: "LateralRelationshipOperations | None" = None  # Protocol-typed (Feb 2026)
    neo4j_driver: "AsyncDriver | None" = None
```

---

## Intelligence Protocols (ISP Split — March 2026)

**Location:** `/core/ports/intelligence_protocols.py`
**Purpose:** Separate shared knowledge intelligence from domain-specific behavioral intelligence.

### KnowledgeIntelligenceOperations (4 methods — shared)

```python
@runtime_checkable
class KnowledgeIntelligenceOperations(Protocol):
    async def get_knowledge_suggestions(self, user_uid: UserUID, entity_uid: EntityUID | None = None) -> Result[KnowledgeSuggestionsResult]: ...
    async def get_knowledge_prerequisites(self, entity_uid: EntityUID) -> Result[KnowledgePrerequisitesResult]: ...
    async def generate_knowledge_from_entities(self, user_uid: UserUID, period_days: int = 30) -> Result[KnowledgeGenerationResult]: ...
    async def get_learning_opportunities(self, user_uid: UserUID) -> Result[LearningOpportunitiesResult]: ...
```

**Implementor:** `ActivityKnowledgeIntelligenceService` (one shared singleton for all 6 Activity Domains)

### DomainIntelligenceOperations (7 methods — per-domain)

```python
@runtime_checkable
class DomainIntelligenceOperations(Protocol):
    async def find_similar_content(self, uid: str, limit: int = 5) -> Result[list[str]]: ...
    async def search_by_features(self, features: dict[str, Any], limit: int = 25) -> Result[list[str]]: ...
    async def get_learning_velocity(self, user_uid: UserUID, period_days: int = 90) -> Result[LearningVelocityMetrics]: ...
    async def get_behavioral_insights(self, user_uid: UserUID, period_days: int = 90) -> Result[BehavioralInsightsResult]: ...
    async def get_performance_analytics(self, user_uid: UserUID, period_days: int = 30) -> Result[PerformanceAnalyticsResult]: ...
    async def get_cross_domain_opportunities(self, user_uid: UserUID, entity_uid: EntityUID | None = None) -> Result[CrossDomainOpportunitiesResult]: ...
    async def get_ai_insights(self, user_uid: UserUID, entity_uid: EntityUID | None = None, query: str | None = None) -> Result[AIInsightsResult]: ...
```

**Implementors:** 6 per-domain intelligence services (TasksIntelligenceService, GoalsIntelligenceService, etc.)

### IntelligenceOperations (composed — backward compatibility)

```python
@runtime_checkable
class IntelligenceOperations(KnowledgeIntelligenceOperations, DomainIntelligenceOperations, Protocol): ...
```

**Usage:** Route factories use the composed protocol. Services that only need knowledge intelligence depend on `KnowledgeIntelligenceOperations`.

---

## Usage Examples

### Example 1: Enum Value Extraction

```python
# WRONG - using hasattr()
from core.models.enums import Priority

task_priority = Priority.HIGH
priority_str = task_priority.value if hasattr(task_priority, 'value') else "medium"

# RIGHT - using get_enum_value()
from core.ports import get_enum_value

priority_str = get_enum_value(task_priority)  # "high"
```

---

### Example 2: Service Capability Checking

```python
# WRONG - using hasattr()
if hasattr(search_service, 'graph_aware_faceted_search'):
    return await search_service.graph_aware_faceted_search(request, user_uid)

# RIGHT - using isinstance() with a @runtime_checkable Protocol
from core.ports.search_protocols import SupportsGraphAwareSearch

if isinstance(search_service, SupportsGraphAwareSearch):
    return await search_service.graph_aware_faceted_search(
        request=request,
        user_uid=user_uid,
    )
return None
```

This is the live pattern, not an illustration: `SearchRouter` resolves the service
with `isinstance` (`core/orchestrator/search_router.py:1152`) and calls
`graph_aware_faceted_search(request=..., user_uid=...)` at `:1187`. The protocol's
own docstring (`core/ports/search_protocols.py:723-725`) carries the same example —
**diff against it rather than paraphrasing it.**

> **Note.** A generic capability tier (`SupportsCount`, `SupportsSearch`,
> `SupportsPathfinding`, `SupportsHealthCheck`, `SupportsInsights`,
> `SupportsRelatedSearch`, `SupportsSearchWithFilters`) once lived in
> `core/ports/base_protocols.py` and was documented here. It was deleted — zero
> imports, zero annotations and zero `isinstance` checks tree-wide. Capability
> protocols are still the right answer to `hasattr`; write them where the
> capability is domain-specific, as `search_protocols.py` does.

---

### Example 3: Facade Service Type Hints (February 2026)

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.tasks_service import TasksService

async def analyze_task_knowledge(
    tasks_service: "TasksService",
    task_uid: str
) -> dict:
    # MyPy sees all explicit methods on TasksService
    result = await tasks_service.get_task(task_uid)
    if result.is_error:
        return {}

    impact = await tasks_service.analyze_task_knowledge_impact(task_uid)
    return impact.value if impact.is_ok else {}
```

---

## Migration Checklist

When replacing `hasattr()` with Protocols:

- [ ] **Identify the pattern:** Is it enum extraction, backend capability, Pydantic field?
- [ ] **Choose the right Protocol:** See table below
- [ ] **Import the Protocol:** `from core.ports import ProtocolName`
- [ ] **Replace hasattr() with isinstance():** `isinstance(obj, Protocol)`
- [ ] **Consider fail-fast:** Per CLAUDE.md, prefer letting errors surface
- [ ] **Test:** Ensure behavioral equivalence

---

## Protocol Lookup Table

Quick reference for common hasattr() patterns:

| hasattr() Pattern | Replace With | Location |
|------------------|--------------|----------|
| `hasattr(enum, 'value')` | `get_enum_value(enum)` | `core.ports` |
| `hasattr(svc, 'graph_aware_faceted_search')` | `isinstance(svc, SupportsGraphAwareSearch)` | `core.ports.search_protocols` |
| `hasattr(svc, 'search_by_tags')` | `isinstance(svc, SupportsTagSearch)` | `core.ports.search_protocols` |
| `hasattr(field_info, 'metadata')` | `isinstance(field_info, PydanticFieldInfo)` | `core.ports` |
| `hasattr(constraint, 'min_length')` | `isinstance(constraint, MinLenConstraint)` | `core.ports` |
| `hasattr(pydantic_model, 'field')` | Just access `model.field` (always defined) | N/A |
| `hasattr(entity, 'knowledge_relevance')` | `isinstance(entity, KnowledgeCarrier)` | `core.models.protocols` |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Checking Static Enums
```python
from core.models.enums import Domain

# WRONG - Domain enum is static, this check is meaningless
knowledge = get_nodes(Domain.KNOWLEDGE) if hasattr(Domain, 'KNOWLEDGE') else []

# RIGHT - Just use it
knowledge = get_nodes(Domain.KNOWLEDGE)
```

### Anti-Pattern 2: Checking Pydantic Model Fields
```python
class Request(BaseModel):
    status: Optional[str] = None

request = Request()

# WRONG - Field is always defined on Pydantic models
if hasattr(request, 'status') and request.status:
    # ...

# RIGHT - Field exists, just check if it's not None
if request.status:
    # ...
```

### Anti-Pattern 3: Defensive Backend Checking
```python
# WRONG - Graceful degradation (violates CLAUDE.md)
if hasattr(backend, 'advanced_search'):
    results = await backend.advanced_search(query)
else:
    results = await backend.basic_search(query)

# RIGHT - Fail fast, fix the backend
results = await backend.advanced_search(query)  # Let it fail if not implemented
```

---

## Protocol Design Guidelines

When creating new Protocols:

1. **Name clearly:** `HasFoo`, `SupportsFoo`, `FooLike`
2. **Use @runtime_checkable:** Enables `isinstance()` checks
3. **Define minimal interface:** Only what's needed for the check
4. **Document purpose:** Explain when/why to use
5. **Add to this reference:** Keep documentation current

---

## Related Documentation

- `/docs/patterns/protocol_architecture.md` - Protocol architecture and best practices (includes Phase 5: Route-Facing ISP Protocols)
- `/docs/patterns/BACKEND_OPERATIONS_ISP.md` - BackendOperations protocol hierarchy
- `/docs/guides/PROTOCOL_IMPLEMENTATION_GUIDE.md` - How to implement protocols
- `/docs/decisions/ADR-025-service-consolidation-patterns.md` - Facade protocols context
- `/docs/decisions/ADR-027-knowledge-carrier-protocol.md` - KnowledgeCarrier context
- `CLAUDE.md` - Architectural principles (Three Typing Strategies for Services dataclass)

---

## Conclusion

Protocols provide type-safe, explicit interfaces that replace hasattr() duck typing. They improve:

- **Type Safety:** MyPy can verify Protocol compliance
- **IDE Support:** Autocomplete works correctly
- **Maintainability:** Clear contracts vs implicit checks
- **Performance:** isinstance() is faster than hasattr()
- **Debugging:** Explicit errors vs silent failures

Always prefer Protocols over hasattr() in new code, and migrate existing code per the migration plan.
